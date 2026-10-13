/* One native Zotero 9/10 bridge, multiple isolated workspace clients. */
var LitBridge;
var LitBridgePaths=[];
function install() {}
function uninstall() {}
async function startup({rootURI}) {
 await Zotero.initializationPromise;
 if(Zotero.Server.Endpoints['/lit2zotero/v1'])throw Error('Another Lit2Zotero bridge owns this endpoint; disable old workspace forks first');
 if(typeof ChromeUtils!=='undefined') {
  const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
  const self=await AddonManager.getAddonByID('lit2zotero@local.invalid');
  if(self)self.applyBackgroundUpdates=AddonManager.AUTOUPDATE_DISABLE;
 }
 const settings=await (await fetch(rootURI+'settings.json')).json();
 if(settings.schema_version!==1||!settings.registryPath)throw Error('Rebuild bridge with shared registry');
 async function authenticate(token) {
  const registry=JSON.parse(new TextDecoder().decode(await IOUtils.read(settings.registryPath)));
  if(registry.schema_version!==1||!Array.isArray(registry.clients))throw Error('Invalid client registry');
  const matches=registry.clients.filter(c=>typeof c.token==='string'&&c.token.length>=32&&c.token===token);
  if(matches.length!==1)return null;
  const c=matches[0];
  if(!/^[0-9a-f-]{36}$/.test(c.workspace_id||'')||!c.allowedRoot)throw Error('Invalid workspace configuration');
  return c;
 }
 let queue=Promise.resolve();
 const clean=x=>String(x||'').trim();
 const collectionName=x=>{
  if(typeof x!=='string'||/[\x00-\x1f\x7f]/.test(x)||!x.trim()||x.trim().length>160)throw Error('Collection name must be 1-160 characters without control characters');
  return x.trim();
 };
 const normal=x=>clean(x).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}_]/gu,'');
 const doi=x=>clean(x).replace(/^https?:\/\/(dx\.)?doi.org\//i,'').toLowerCase();
 const escape=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 const namespace=c=>c.prefNamespace||'lit2zotero';
 const mappings=c=>JSON.parse(Zotero.Prefs.get(namespace(c)+'.projects',true)||'{}');
 async function scope(d,config) {
  const key=mappings(config)[d.project_id];
  if (!key || key!==d.collection_key) throw Error('Collection not registered to project');
  const c=Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID,key);
  if (!c || c.deleted) throw Error('Managed collection unavailable');return c;
 }
 function itemResult(item) {return {key:item.key,uri:Zotero.URI.getItemURI(item),library_id:Zotero.Users.getCurrentUserID()||'local',title:item.getField('title')};}
 async function readingCollections(d,parent,config) {
  const maps=JSON.parse(Zotero.Prefs.get(namespace(config)+'.readingCollections',true)||'{}');
  const own=maps[d.project_id]||{};const result={};
  for(const [kind,name] of [['required','需要PDF'],['not_required','不需要PDF']]) {
   let child=own[kind]?Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID,own[kind]):null;
   if(own[kind]&&(!child||child.deleted||child.parentID!==parent.id))throw Error('Managed reading collection missing or moved');
   if(!child) {
    child=new Zotero.Collection();child.libraryID=parent.libraryID;child.name=name;child.parentID=parent.id;await child.saveTx();
    own[kind]=child.key;maps[d.project_id]=own;Zotero.Prefs.set(namespace(config)+'.readingCollections',JSON.stringify(maps),true);
   }
   result[kind]=child;
  }
  return result;
 }
 async function execute(d,config) {
  if(d.op==='health')return {version:'0.3.1',zotero:Zotero.version,workspace_id:config.workspace_id,operations:['collection','rename-collection','free-collection-names','reading-collections','flatten-reading-collections','upsert','attach','multi-workspace']};
  if (!/^[0-9a-f-]{36}$/.test(d.project_id||'')) throw Error('Invalid project ID');
  const owners=JSON.parse(Zotero.Prefs.get('lit2zotero.projectOwners',true)||'{}');
  if(owners[d.project_id]&&owners[d.project_id]!==config.workspace_id)throw Error('Project belongs to another workspace');
  if(!owners[d.project_id]) {
   if(mappings(config)[d.project_id]&&!(config.legacyProjectIds||[]).includes(d.project_id))throw Error('Legacy project requires reviewed workspace registration');
   if(!mappings(config)[d.project_id]&&d.op!=='collection')throw Error('Project must be registered first');
   if(d.op==='collection')collectionName(d.name);
   owners[d.project_id]=config.workspace_id;Zotero.Prefs.set('lit2zotero.projectOwners',JSON.stringify(owners),true);
  }
  if(d.op==='collection') {
   const name=collectionName(d.name);
   const map=mappings(config);
   if(map[d.project_id]) {const c=Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID,map[d.project_id]);if(!c||c.deleted)throw Error('Existing collection missing');return {key:c.key,name:c.name};}
   const c=new Zotero.Collection();c.libraryID=Zotero.Libraries.userLibraryID;c.name=name;await c.saveTx();map[d.project_id]=c.key;Zotero.Prefs.set(namespace(config)+'.projects',JSON.stringify(map),true);return {key:c.key,name:c.name};
  }
  const c=await scope(d,config);
  if(d.op==='rename-collection') {
   const name=collectionName(d.name);
   if(typeof d.apply!=='boolean')throw Error('Explicit preview/apply required');
   const result={key:c.key,old_name:c.name,new_name:name,apply:d.apply};
   if(d.apply&&c.name!==name){c.name=name;await c.saveTx();}
   return result;
  }
  if(d.op==='flatten-reading-collections') {
   if(typeof d.apply!=='boolean')throw Error('Explicit preview/apply required');
   const pref=namespace(config)+'.readingCollections';
   const maps=JSON.parse(Zotero.Prefs.get(pref,true)||'{}'),own=maps[d.project_id]||{};
   const children=[];
   for(const [kind,name] of [['required','需要PDF'],['not_required','不需要PDF']]) {
    if(!own[kind])continue;
    const child=Zotero.Collections.getByLibraryAndKey(c.libraryID,own[kind]);
    if(!child||child.deleted||child.parentID!==c.id||child.name!==name)throw Error('Managed child missing, renamed or moved; manual review required');
    await child.loadDataType('childCollections');await child.loadDataType('childItems');
    if(child.getChildCollections(true,true).length)throw Error('Nested collections require manual review');
    children.push(child);
   }
   const result={apply:d.apply,parent_key:c.key,removed_collection_keys:children.map(x=>x.key),items_preserved:true};
   if(!d.apply)return result;
   await Zotero.DB.executeTransaction(async()=>{
    for(const child of children) {
     for(const item of await Zotero.Items.getAsync(child.getChildItems(true,true))) {
      item.addToCollection(c.id);await item.save();
     }
     // Remove only the verified generated shell, NEVER its items/notes/PDFs.
     await child.erase({deleteItems:false});
    }
   });
   delete maps[d.project_id];Zotero.Prefs.set(pref,JSON.stringify(maps),true);
   return result;
  }
  if(d.op==='reading-collections') {
   const groups=await readingCollections(d,c,config);
   return Object.fromEntries(Object.entries(groups).map(([kind,x])=>[kind,{key:x.key,name:x.name,parent_key:c.key}]));
  }
  if(d.op==='upsert') {
   if(d.pdf_requirement!==undefined&&!['required','not_required'].includes(d.pdf_requirement))throw Error('Invalid PDF requirement');
   const groups=d.pdf_requirement!==undefined?await readingCollections(d,c,config):null;
   const m=d.metadata;
   if(!m||m.itemType!=='journalArticle'||!clean(m.title)||!Array.isArray(m.creators))throw Error('Invalid metadata');
   if(!/^P[a-f0-9]{12}$/.test(d.paper_id||''))throw Error('Invalid paper ID');
   const s=new Zotero.Search();s.libraryID=Zotero.Libraries.userLibraryID;s.addCondition('deleted','false');
   s.addCondition(m.DOI?'DOI':'title','is',m.DOI||m.title);
   let found=(await Zotero.Items.getAsync(await s.search())).filter(x=>x.isRegularItem());
   if(d.preferred_key){found=found.filter(x=>x.key===d.preferred_key);if(!found.length)throw Error('Reviewed binding no longer matches');}
   if(found.length>1)throw Error('Multiple local items match identifier');
   let item=found[0];
   if(item && (normal(item.getField('title'))!==normal(m.title) || (m.DOI && doi(item.getField('DOI'))!==doi(m.DOI))))throw Error('Local identity conflict');
   await Zotero.DB.executeTransaction(async()=>{
    if(!item) {
     item=new Zotero.Item('journalArticle');item.libraryID=Zotero.Libraries.userLibraryID;
     for(const k of ['title','date','DOI','abstractNote','publicationTitle','url','volume','issue','pages','extra'])if(m[k])item.setField(k,m[k]);
     item.setCreators(m.creators);
    }
    item.addToCollection(c.id);
    if(groups) {
     item.addToCollection(groups[d.pdf_requirement].id);
     item.removeFromCollection(groups[d.pdf_requirement==='required'?'not_required':'required'].id);
    }
    item.addTag('lit2z:included');await item.save();
    const marker='Lit2Zotero '+d.project_id;
    let note=(await Zotero.Items.getAsync(item.getNotes())).find(n=>n.getNote().includes(marker));
    if(!note){note=new Zotero.Item('note');note.libraryID=item.libraryID;note.parentID=item.id;}
    note.setNote('<p>'+marker+'</p><pre>'+escape(d.note||'')+'</pre>');await note.save();
   });
   return itemResult(item);
  }
  if(d.op==='attach') {
   const item=Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID,d.item_key);
   if(!item||!item.getCollections().includes(c.id))throw Error('Parent outside managed collection');
   const path=clean(d.path);const file=Zotero.File.pathToFile(path);file.normalize();
   const root=Zotero.File.pathToFile(config.allowedRoot);root.normalize();
   if(!root.contains(file,true)||!file.isFile()||!file.path.toLowerCase().endsWith('.pdf'))throw Error('PDF outside allowed directory');
   if(file.fileSize>60*1024*1024)throw Error('PDF size limit');
   const raw=await IOUtils.read(file.path,{maxBytes:5});if(new TextDecoder().decode(raw)!=='%PDF-')throw Error('Not a PDF');
   const filename=file.leafName;
   for(const a of await Zotero.Items.getAsync(item.getAttachments())) {
    if(a.getField('title')==='Lit2Zotero '+filename){const p=await a.getFilePathAsync();if(p&&await IOUtils.exists(p))return {key:a.key,exists:true};throw Error('Existing managed attachment file missing');}
   }
   const a=await Zotero.Attachments.importFromFile({file:file.path,parentItemID:item.id,title:'Lit2Zotero '+filename});
   const stored=await a.getFilePathAsync();if(!stored||!await IOUtils.exists(stored))throw Error('Attachment import not readable');
   return {key:a.key,exists:false};
  }
  throw Error('Unsupported operation');
 }
 function Endpoint(){}
 Endpoint.prototype={supportedMethods:['POST'],supportedDataTypes:['application/json'],permitBookmarklet:false,
  init:async function(req){
   const h=Object.fromEntries(Object.entries(req.headers||{}).map(([k,v])=>[k.toLowerCase(),v]));
   if('origin' in h || 'referer' in h)return [403,'application/json',JSON.stringify({ok:false,error:'Unauthorized'})];
   let config;
   try {config=await authenticate(h['x-lit2zotero-token']);}
   catch(e){return [503,'application/json',JSON.stringify({ok:false,error:'Bridge registry unavailable or invalid'})];}
   if(!config)return [403,'application/json',JSON.stringify({ok:false,error:'Unauthorized'})];
   if(!req.data||typeof req.data!=='object'||Array.isArray(req.data))return [400,'application/json',JSON.stringify({ok:false,error:'Expected an object'})];
   if(JSON.stringify(req.data).length>200000)return [413,'application/json',JSON.stringify({ok:false,error:'Payload too large'})];
   const job=queue.then(()=>execute(req.data,config));queue=job.catch(()=>{});
   try{return [200,'application/json',JSON.stringify({ok:true,result:await job})];}
   catch(e){return [400,'application/json',JSON.stringify({ok:false,error:e.message})];}
  }};
 const registry=JSON.parse(new TextDecoder().decode(await IOUtils.read(settings.registryPath)));
 if(registry.schema_version!==1||!Array.isArray(registry.clients))throw Error('Invalid client registry');
 const paths=[...new Set(['/lit2zotero/v1',...registry.clients.map(c=>c.endpoint||'/lit2zotero/v1')])];
 if(paths.some(p=>!/^\/lit2zotero(?:-[a-z0-9_-]+)?\/v1$/.test(p)))throw Error('Invalid legacy endpoint');
 if(paths.some(p=>Zotero.Server.Endpoints[p]))throw Error('Another Lit2Zotero bridge registered during startup; disable legacy forks');
 LitBridge=Endpoint;LitBridgePaths=paths;for(const p of paths)Zotero.Server.Endpoints[p]=Endpoint;
}
function shutdown(){for(const p of LitBridgePaths)if(LitBridge&&Zotero.Server.Endpoints[p]===LitBridge)delete Zotero.Server.Endpoints[p];LitBridge=null;LitBridgePaths=[];}
