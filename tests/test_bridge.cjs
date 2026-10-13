/* Contract test, not a substitute for Zotero integration. */
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.dirname(__dirname),token='x'.repeat(40),prefs={},collections=[],items=[];let imports=0;
class Collection {constructor(){this.id=collections.length+1;this.key='COLL000'+this.id;} async saveTx(){collections.push(this);}async loadDataType(){}getChildCollections(ids){const cs=collections.filter(x=>x.parentID===this.id&&!x.erased);return ids?cs.map(x=>x.id):cs;}getChildItems(ids){const xs=items.filter(x=>x.cols.includes(this.id));return ids?xs.map(x=>x.id):xs;}async erase(options){assert.equal(options.deleteItems,false);this.erased=true;for(const i of items)i.removeFromCollection(this.id);}}
class Item {constructor(type){this.type=type;this.id=items.length+1;this.key='ITEM000'+this.id;this.fields={};this.cols=[];}
 setField(k,v){this.fields[k]=v;} getField(k){return this.fields[k]||'';} setCreators(v){this.creators=v;} addToCollection(c){if(!this.cols.includes(c))this.cols.push(c);} removeFromCollection(c){this.cols=this.cols.filter(x=>x!==c);} addTag(){} getCollections(){return this.cols;}isRegularItem(){return this.type==='journalArticle';}setNote(v){this.note=v;}getNote(){return this.note;}getNotes(){return items.filter(x=>x.type==='note'&&x.parentID===this.id).map(x=>x.id);}getAttachments(){return items.filter(x=>x.type==='attachment'&&x.parentID===this.id).map(x=>x.id);}async save(){if(!items.includes(this))items.push(this);}async getFilePathAsync(){return this.path;}}
class Search {constructor(){this.conditions=[];}addCondition(...a){this.conditions.push(a);}async search(){return items.filter(x=>x.isRegularItem()&&this.conditions.every(([k,op,v])=>k==='deleted'||x.getField(k)===v)).map(x=>x.id);}}
const Z={initializationPromise:Promise.resolve(),version:'MOCK',Server:{Endpoints:{}},Prefs:{get:k=>prefs[k],set:(k,v)=>prefs[k]=v},Libraries:{userLibraryID:1},Users:{getCurrentUserID:()=>123},URI:{getItemURI:x=>'http://zotero.org/users/123/items/'+x.key},Collection,Item,Search,Collections:{getByLibraryAndKey:(l,k)=>collections.find(x=>x.key===k&&!x.erased)},Items:{getAsync:async ids=>ids.map(id=>items.find(x=>x.id===id)),getByLibraryAndKey:(l,k)=>items.find(x=>x.key===k)},DB:{executeTransaction:async f=>f()},File:{pathToFile:p=>({path:p,leafName:path.basename(p),fileSize:20,normalize(){},contains(f){return f.path.startsWith('/allowed/')},isFile:()=>true})},Attachments:{importFromFile:async o=>{imports++;const a=new Item('attachment');a.parentID=o.parentItemID;a.path=o.file;a.setField('title',o.title);await a.save();return a;}}};
const client={token,allowedRoot:'/allowed',workspace_id:'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',legacyProjectIds:[]};
const registry={schema_version:1,clients:[client,{token:'z'.repeat(40),allowedRoot:'/legacy',workspace_id:'cccccccc-cccc-4ccc-cccc-cccccccccccc',prefNamespace:'lit2zotero.ggq',endpoint:'/lit2zotero-ggq/v1',legacyProjectIds:['eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee']}]};
const makeContext=()=>vm.createContext({Zotero:Z,fetch:async()=>({json:async()=>({schema_version:1,registryPath:'/registry.json'})}),IOUtils:{read:async p=>Buffer.from(p==='/registry.json'?JSON.stringify(registry):'%PDF-'),exists:async()=>true},TextDecoder});
const context=makeContext();
vm.runInContext(fs.readFileSync(path.join(root,'bridge/bootstrap.js'),'utf8'),context);
(async()=>{await context.startup({rootURI:'file:///test/'});const endpoint=new Z.Server.Endpoints['/lit2zotero/v1']();let checks=0;
async function call(data,headers={}){const r=await endpoint.init({headers:{'X-Lit2Zotero-Token':token,...headers},data});return {status:r[0],body:JSON.parse(r[2])};}
assert.equal((await call({op:'health'},{Origin:'http://evil.example'})).status,403);checks++;
assert.equal((await call({op:'health'},{'X-Lit2Zotero-Token':'bad'})).status,403);checks++;
const project_id='12345678-1234-1234-1234-123456789012';let c=await call({op:'collection',project_id,name:'Lit2Zotero · test'});assert(c.body.ok);checks++;
const key=c.body.result.key;await call({op:'collection',project_id,name:'Lit2Zotero · test'});assert.equal(collections.length,1);checks++;
let d={op:'upsert',project_id,collection_key:key,paper_id:'P123456789abc',metadata:{itemType:'journalArticle',title:'Verified test paper',DOI:'10.1234/test',creators:[]},note:'<script>not executable</script>'};let r=await call(d);assert(r.body.ok);const item_key=r.body.result.key;checks++;
await call(d);assert.equal(items.filter(x=>x.isRegularItem()).length,1);assert.equal(items.filter(x=>x.type==='note').length,1);checks++;
assert(items.find(x=>x.type==='note').note.includes('&lt;script&gt;'));checks++;
assert.equal((await call({...d,collection_key:'OTHER'})).status,400);checks++;
assert.equal((await call({op:'attach',project_id,collection_key:key,item_key,path:'/outside/secret.pdf'})).status,400);checks++;
const a={op:'attach',project_id,collection_key:key,item_key,path:'/allowed/paper.pdf'};assert((await call(a)).body.ok);await call(a);assert.equal(imports,1);checks++;
const grouped=await call({op:'reading-collections',project_id,collection_key:key});assert(grouped.body.ok);assert.equal(collections.length,3);checks++;
await call({op:'reading-collections',project_id,collection_key:key});assert.equal(collections.length,3);checks++;
const current=items.find(x=>x.key===item_key);current.addToCollection(999);
assert((await call({...d,pdf_requirement:'required'})).body.ok);const required=collections.find(x=>x.name==='需要PDF'),optional=collections.find(x=>x.name==='不需要PDF');assert(current.cols.includes(required.id));assert(!current.cols.includes(optional.id));checks++;
assert((await call({...d,pdf_requirement:'not_required'})).body.ok);assert(!current.cols.includes(required.id));assert(current.cols.includes(optional.id));assert(current.cols.includes(999));assert(current.cols.includes(collections[0].id));checks++;
assert.equal((await call({...d,pdf_requirement:'unknown'})).status,400);checks++;
assert.equal((await call({op:'eval',project_id,collection_key:key,code:'bad'})).status,400);checks++;
assert(Z.Server.Endpoints['/lit2zotero-ggq/v1']);checks++;
prefs['lit2zotero.ggq.projects']=JSON.stringify({'eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee':key});
const legacy=await call({op:'collection',project_id:'eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee',name:'Lit2Zotero · legacy'},{'X-Lit2Zotero-Token':'z'.repeat(40)});
assert.equal(legacy.body.result.key,key);assert.equal(collections.length,3);checks++;
const second={token:'y'.repeat(40),allowedRoot:'/second',workspace_id:'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb',legacyProjectIds:[]};
registry.clients.push(second);
assert((await call({op:'health'},{'X-Lit2Zotero-Token':second.token})).body.ok);checks++;
assert.equal((await call({...d},{'X-Lit2Zotero-Token':second.token})).status,400);checks++;
assert.equal((await call({op:'collection',project_id,name:'Lit2Zotero · hijack'},{'X-Lit2Zotero-Token':second.token})).status,400);checks++;
registry.clients.pop();assert.equal((await call({op:'health'},{'X-Lit2Zotero-Token':second.token})).status,403);checks++;
registry.clients.push({...client});assert.equal((await call({op:'health'})).status,403);registry.clients.pop();checks++;
assert.equal((await call(null)).status,400);checks++;
assert.equal((await call({op:'health'},{Origin:''})).status,403);checks++;
const flatten={op:'flatten-reading-collections',project_id,collection_key:key,apply:false};
assert.equal((await call({...flatten,collection_key:'OTHER'})).status,400);checks++;
const preview=await call(flatten);assert(preview.body.ok);assert.equal(preview.body.result.removed_collection_keys.length,2);assert(!required.erased);checks++;
required.name='user renamed';assert.equal((await call({...flatten,apply:true})).status,400);required.name='需要PDF';checks++;
const nested=new Collection();nested.parentID=required.id;await nested.saveTx();assert.equal((await call({...flatten,apply:true})).status,400);nested.erased=true;checks++;
const childOnly=new Item('journalArticle');childOnly.addToCollection(required.id);await childOnly.save();const before=items.length;
assert((await call({...flatten,apply:true})).body.ok);assert.equal(items.length,before);assert(current.cols.includes(999));assert(current.cols.includes(collections[0].id));assert(childOnly.cols.includes(collections[0].id));assert(required.erased&&optional.erased);assert.equal(imports,1);checks++;
assert((await call({...flatten,apply:true})).body.ok);assert.equal(items.length,before);checks++;
assert((await call(d)).body.ok);assert.equal(collections.filter(x=>!x.erased).length,1);checks++;
const fork=makeContext();vm.runInContext(fs.readFileSync(path.join(root,'bridge/bootstrap.js'),'utf8'),fork);
await assert.rejects(()=>fork.startup({rootURI:'file:///test/'}),/Another Lit2Zotero/);fork.shutdown();assert(Z.Server.Endpoints['/lit2zotero/v1']);checks++;
const owned=Z.Server.Endpoints['/lit2zotero/v1'];const foreign=function(){};
Z.Server.Endpoints['/lit2zotero/v1']=foreign;context.shutdown();assert.equal(Z.Server.Endpoints['/lit2zotero/v1'],foreign);checks++;
delete Z.Server.Endpoints['/lit2zotero/v1'];await context.startup({rootURI:'file:///test/'});context.shutdown();assert(!Z.Server.Endpoints['/lit2zotero/v1']);checks++;
console.log(JSON.stringify({mock_bridge_checks:checks,passed:true,real_zotero:false}));})().catch(e=>{console.error(e);process.exit(1);});
