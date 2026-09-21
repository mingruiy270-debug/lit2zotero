/* Native Zotero 9 bridge. The external caller never computes a file digest. */
var LitBridge;
function install() {}
function uninstall() {}
async function startup({rootURI}) {
 await Zotero.initializationPromise;
 if(typeof ChromeUtils!=='undefined') {
  const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
  const self=await AddonManager.getAddonByID('lit2zotero@local.invalid');
  if(self)self.applyBackgroundUpdates=AddonManager.AUTOUPDATE_DISABLE;
 }
 const config=await (await fetch(rootURI+'settings.json')).json();
 if (!config.token || config.token.length<32) throw Error('Missing local bridge configuration');
 let queue=Promise.resolve();
 const clean=x=>String(x||'').trim();
 const normal=x=>clean(x).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}_]/gu,'');
 const doi=x=>clean(x).replace(/^https?:\/\/(dx\.)?doi.org\//i,'').toLowerCase();
 const escape=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 const mappings=()=>JSON.parse(Zotero.Prefs.get('lit2zotero.projects',true)||'{}');
 async function scope(d) {
  const key=mappings()[d.project_id];
  if (!key || key!==d.collection_key) throw Error('Collection not registered to project');
  const c=Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID,key);
  if (!c || c.deleted) throw Error('Managed collection unavailable');return c;
 }
 function itemResult(item) {return {key:item.key,uri:Zotero.URI.getItemURI(item),library_id:Zotero.Users.getCurrentUserID()||'local',title:item.getField('title')};}
 async function execute(d) {
  if(d.op==='health')return {version:'0.1.1',zotero:Zotero.version,operations:['collection','upsert','attach']};
  if (!/^[0-9a-f-]{36}$/.test(d.project_id||'')) throw Error('Invalid project ID');
  if(d.op==='collection') {
   if(!clean(d.name).startsWith('Lit2Zotero · ')||d.name.length>160)throw Error('Use the Lit2Zotero · collection prefix');
   const map=mappings();
   if(map[d.project_id]) {const c=Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID,map[d.project_id]);if(!c||c.deleted)throw Error('Existing collection missing');return {key:c.key,name:c.name};}
   const c=new Zotero.Collection();c.libraryID=Zotero.Libraries.userLibraryID;c.name=d.name;await c.saveTx();map[d.project_id]=c.key;Zotero.Prefs.set('lit2zotero.projects',JSON.stringify(map),true);return {key:c.key,name:c.name};
  }
  const c=await scope(d);
  if(d.op==='upsert') {
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
    item.addToCollection(c.id);item.addTag('lit2z:included');await item.save();
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
   if(h['x-lit2zotero-token']!==config.token || h.origin || h.referer)return [403,'application/json',JSON.stringify({ok:false,error:'Unauthorized'})];
   if(JSON.stringify(req.data).length>200000)return [413,'application/json',JSON.stringify({ok:false,error:'Payload too large'})];
   const job=queue.then(()=>execute(req.data));queue=job.catch(()=>{});
   try{return [200,'application/json',JSON.stringify({ok:true,result:await job})];}
   catch(e){return [400,'application/json',JSON.stringify({ok:false,error:e.message})];}
  }};
 LitBridge=Endpoint;Zotero.Server.Endpoints['/lit2zotero/v1']=Endpoint;
}
function shutdown(){delete Zotero.Server.Endpoints['/lit2zotero/v1'];LitBridge=null;}
