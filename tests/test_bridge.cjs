/* Contract test, not a substitute for Zotero integration. */
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.dirname(__dirname),token='x'.repeat(40),prefs={},collections=[],items=[];let imports=0;
class Collection {constructor(){this.id=collections.length+1;this.key='COLL000'+this.id;} async saveTx(){collections.push(this);}}
class Item {constructor(type){this.type=type;this.id=items.length+1;this.key='ITEM000'+this.id;this.fields={};this.cols=[];}
 setField(k,v){this.fields[k]=v;} getField(k){return this.fields[k]||'';} setCreators(v){this.creators=v;} addToCollection(c){if(!this.cols.includes(c))this.cols.push(c);} removeFromCollection(c){this.cols=this.cols.filter(x=>x!==c);} addTag(){} getCollections(){return this.cols;}isRegularItem(){return this.type==='journalArticle';}setNote(v){this.note=v;}getNote(){return this.note;}getNotes(){return items.filter(x=>x.type==='note'&&x.parentID===this.id).map(x=>x.id);}getAttachments(){return items.filter(x=>x.type==='attachment'&&x.parentID===this.id).map(x=>x.id);}async save(){if(!items.includes(this))items.push(this);}async getFilePathAsync(){return this.path;}}
class Search {constructor(){this.conditions=[];}addCondition(...a){this.conditions.push(a);}async search(){return items.filter(x=>x.isRegularItem()&&this.conditions.every(([k,op,v])=>k==='deleted'||x.getField(k)===v)).map(x=>x.id);}}
const Z={initializationPromise:Promise.resolve(),version:'MOCK',Server:{Endpoints:{}},Prefs:{get:k=>prefs[k],set:(k,v)=>prefs[k]=v},Libraries:{userLibraryID:1},Users:{getCurrentUserID:()=>123},URI:{getItemURI:x=>'http://zotero.org/users/123/items/'+x.key},Collection,Item,Search,Collections:{getByLibraryAndKey:(l,k)=>collections.find(x=>x.key===k)},Items:{getAsync:async ids=>ids.map(id=>items.find(x=>x.id===id)),getByLibraryAndKey:(l,k)=>items.find(x=>x.key===k)},DB:{executeTransaction:async f=>f()},File:{pathToFile:p=>({path:p,leafName:path.basename(p),fileSize:20,normalize(){},contains(f){return f.path.startsWith('/allowed/')},isFile:()=>true})},Attachments:{importFromFile:async o=>{imports++;const a=new Item('attachment');a.parentID=o.parentItemID;a.path=o.file;a.setField('title',o.title);await a.save();return a;}}};
const context=vm.createContext({Zotero:Z,fetch:async()=>({json:async()=>({token,allowedRoot:'/allowed'})}),IOUtils:{read:async()=>Buffer.from('%PDF-'),exists:async()=>true},TextDecoder});
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
context.shutdown();assert(!Z.Server.Endpoints['/lit2zotero/v1']);checks++;
console.log(JSON.stringify({mock_bridge_checks:checks,passed:true,real_zotero:false}));})().catch(e=>{console.error(e);process.exit(1);});
