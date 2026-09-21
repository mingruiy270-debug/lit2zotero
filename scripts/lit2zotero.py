"""Literature acquisition and controlled Zotero handoff. No automated relevance decisions."""
from __future__ import annotations
import argparse, csv, html, io, ipaddress, json, os, re, socket, sys, time, uuid, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote
import requests

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0'

class ContractError(ValueError): pass

def now(): return datetime.now(timezone.utc).isoformat()
def norm(s): return ' '.join(str(s).casefold().split())
def title_key(s):return re.sub(r'[^\w]','',unicodedata.normalize('NFKC',s).casefold())
def doi(s):
    s = re.sub(r'^(?:https?://(?:dx\.)?doi.org/|doi:\s*)', '', str(s or '').strip(), flags=re.I)
    if s and not re.fullmatch(r'10\.\d{4,9}/\S+', s): raise ContractError('Invalid DOI')
    return s.casefold()
def atomic(p, data):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    try: t.write_text(data, encoding='utf-8'); os.replace(t,p)
    finally:
        if t.exists(): t.unlink()
def write_json(p, x): atomic(p,json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def public_url(url):
    u=urlparse(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password: raise ContractError('Public HTTPS URL required')
    for a in socket.getaddrinfo(u.hostname,u.port or 443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(a[4][0]).is_global: raise ContractError('Private destination rejected')
    return url
def http(url, params=None, redirects=0):
    if redirects>5:raise ContractError('Redirect limit')
    public_url(url)
    for attempt in range(3):
        r=requests.get(url,params=params,timeout=(15,35),headers={'User-Agent':'Lit2Zotero/0.1 scholarly-reference-preparation'},allow_redirects=False,stream=True)
        if r.is_redirect:
            target=requests.compat.urljoin(r.url,r.headers['Location']);r.close();return http(public_url(target),redirects=redirects+1)
        if r.status_code in (429,502,503,504) and attempt<2:r.close();time.sleep(attempt+1);continue
        try:
            r.raise_for_status();data=bytearray()
            for chunk in r.iter_content(65536):
                data.extend(chunk)
                if len(data)>60*1024*1024:raise ContractError('HTTP response exceeds 60 MB')
            r._content=bytes(data);r._content_consumed=True;return r
        finally:r.close()
def strip_xml(s): return html.unescape(re.sub('<[^>]+>',' ',s or '')).strip()

class Project:
    def __init__(self,p):
        self.path=Path(p).resolve()
        if not self.path.is_relative_to(ROOT):raise ContractError('Projects must remain inside this skill workspace')
        self.config=load(self.path/'project.json')
        self.claims=load(self.path/'claims.json')
        if len({x['claim_id'] for x in self.claims})!=len(self.claims): raise ContractError('Duplicate claim IDs')
        q=self.path/'papers.jsonl'; self._snapshot=q.read_text(encoding='utf8') if q.exists() else '';self.papers=[json.loads(x) for x in self._snapshot.splitlines() if x.strip()]
    def save(self):
        q=self.path/'papers.jsonl';current=q.read_text(encoding='utf8') if q.exists() else ''
        if current!=self._snapshot:raise ContractError('Project changed in another process; reload before retry')
        new=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in self.papers);atomic(q,new);self._snapshot=new
    def event(self,kind,**details):
        with (self.path/'events.jsonl').open('a',encoding='utf8') as h: h.write(json.dumps(dict(time=now(),kind=kind,**details),ensure_ascii=False)+'\n')
    def get(self,id):
        matches=[x for x in self.papers if x['paper_id']==id]
        if len(matches)!=1: raise ContractError('Unknown/duplicate paper_id')
        return matches[0]
    def add(self,p):
        p['doi']=doi(p.get('doi')); p['title']=html.unescape(p['title']).strip()
        if not p['title']: raise ContractError('Missing title')
        same=[x for x in self.papers if (p['doi'] and x.get('doi')==p['doi']) or (p.get('pmid') and x.get('pmid')==p['pmid'])]
        if same:
            x=same[0]
            if title_key(x['title'])!=title_key(p['title']): raise ContractError('Same identifier with conflicting title')
            x.setdefault('sources',[]).extend(z for z in p.get('sources',[]) if z not in x['sources']); return x
        p.update(paper_id='P'+uuid.uuid4().hex[:12],decision='defer',reading_status='unread',evidence=[],zotero=None)
        p['identity_status']='title_collision' if any(norm(x['title'])==norm(p['title']) for x in self.papers) else 'verified_metadata'
        self.papers.append(p); return p

def epmc_record(r):
    authors=[]
    for a in r.get('authorList',{}).get('author',[]):
        authors.append({'creatorType':'author','lastName':a.get('lastName') or a.get('collectiveName') or a.get('fullName',''),'firstName':a.get('firstName','')})
    j=r.get('journalInfo',{}); journal=j.get('journal',{})
    links=r.get('fullTextUrlList',{}).get('fullTextUrl',[])
    return dict(title=r.get('title',''),doi=r.get('doi',''),pmid=r.get('id') if r.get('source')=='MED' else None,pmcid=r.get('pmcid'),authors=authors,year=r.get('pubYear',''),date=r.get('firstPublicationDate') or r.get('pubYear',''),journal=journal.get('title',''),volume=j.get('volume',''),issue=j.get('issue',''),pages=r.get('pageInfo',''),abstract=r.get('abstractText',''),abstract_source='Europe PMC core',oa=r.get('isOpenAccess')=='Y',urls=links,sources=[{'provider':'Europe PMC','id':r.get('id'),'source':r.get('source'),'retrieved_at':now()}],notice_status='not_checked')
def discover(project, query, provider='epmc', pages=1):
    count=0; cursor='*'; exhausted=False;conflicts=[]
    def ingest(record):
        try:project.add(record)
        except ContractError as e:
            conflicts.append(dict(doi=record.get('doi'),title=record.get('title'),reason=str(e)))
            project.event('identity_conflict',provider=provider,record=record,reason=str(e))
    for page in range(pages):
        if provider=='epmc':
            obj=http('https://www.ebi.ac.uk/europepmc/webservices/rest/search',dict(query=query,format='json',resultType='core',pageSize=25,cursorMark=cursor)).json()
            batch=obj.get('resultList',{}).get('result',[]); nxt=obj.get('nextCursorMark'); total=obj.get('hitCount')
            for r in batch: ingest(epmc_record(r)); count+=1
            exhausted=not batch or not nxt or nxt==cursor or count>=int(total or 0); cursor=nxt
        elif provider=='crossref':
            obj=http('https://api.crossref.org/works',dict(query=query,rows=25,offset=page*25)).json()['message'];batch=obj['items'];total=obj['total-results']
            for r in batch:
                year=str((r.get('issued',{}).get('date-parts') or [['']])[0][0]);ingest(dict(title=(r.get('title') or [''])[0],doi=r.get('DOI',''),authors=[dict(creatorType='author',lastName=a.get('family') or a.get('name',''),firstName=a.get('given','')) for a in r.get('author',[])],year=year,date=year,journal=(r.get('container-title') or [''])[0],abstract=strip_xml(r.get('abstract')),abstract_source='Crossref',oa=None,urls=[],sources=[dict(provider='Crossref',url=r.get('URL'),retrieved_at=now())],notice_status='not_checked',publication_type=r.get('type')));count+=1
            exhausted=count>=total or not batch
        else: raise ContractError('Unknown provider')
        project.save()
        if exhausted: break
    project.event('search',query=query,provider=provider,fetched=count,exhausted=exhausted,next_cursor=cursor if provider=='epmc' else None)
    return dict(fetched=count,total_candidates=len(project.papers),exhausted=exhausted,conflicts=conflicts)

def decide(project, decisions):
    proposed=json.loads(json.dumps(project.papers)); index={p['paper_id']:p for p in proposed};seen=set()
    for d in decisions:
        if d.get('decision_maker')!='host_agent' or not d.get('reason','').strip(): raise ContractError('Host agent decision and reason required')
        if d['paper_id'] in seen: raise ContractError('Duplicate decision');
        seen.add(d['paper_id']);p=index[d['paper_id']]
        if d['decision'] not in ('include','exclude','defer'): raise ContractError('Invalid decision')
        if p['identity_status']!='verified_metadata' and d['decision']=='include': raise ContractError('Resolve identity conflict first')
        ev=d.get('evidence',[])
        if d['decision']=='include' and not ev: raise ContractError('Included paper needs a claim')
        for e in ev:
            claim=next((c for c in project.claims if c['claim_id']==e.get('claim_id')),None)
            if not claim: raise ContractError('Unknown claim')
            if e.get('relation') not in ('supports','qualifies','contrasts','context_only','unresolved'): raise ContractError('Invalid evidence relation')
            if e.get('required_depth') not in ('abstract','fulltext'): raise ContractError('Invalid reading requirement')
            if claim.get('required_depth')=='fulltext' and e['required_depth']!='fulltext': raise ContractError('Cannot lower claim reading requirement')
            if not e.get('reason'): raise ContractError('Claim-specific rationale required')
        p.update(decision=d['decision'],decision_reason=d['reason'],decision_maker='host_agent',evidence=ev)
        if d.get('abstract_read'):
            if not p.get('abstract'): raise ContractError('No abstract to read')
            if p.get('reading_status')!='fulltext_read':p['reading_status']='abstract_read'
    project.papers=proposed; project.save();project.event('agent_decisions',decisions=decisions)

def validate_pdf(path,paper):
    import pymupdf
    path=Path(path)
    with path.open('rb') as handle: signature=handle.read(5)
    if path.stat().st_size>60*1024*1024 or signature!=b'%PDF-': raise ContractError('Invalid PDF or size limit')
    with pymupdf.open(path) as d:
        if d.needs_pass or not len(d):raise ContractError('Encrypted/empty PDF')
        pages=[p.get_text() for p in d];head=norm(' '.join(pages[:2]));title=norm(paper['title']);ident=paper.get('doi','')
        words=[w for w in re.findall(r'\w+',title) if len(w)>3]
        matched=bool(ident and ident in head) or (len(words)>=4 and sum(w in head for w in words)/len(words)>=.85)
        if not matched:raise ContractError('PDF identity unconfirmed; title/DOI absent from first pages')
        if 'supplement' in head[:250] and ident not in head:raise ContractError('Possible supplement instead of main paper')
        return pages
def attach_local(project,id,path):
    import shutil
    p=project.get(id);pages=validate_pdf(path,p); dest=project.path/'pdf'/f'{id}.pdf';dest.parent.mkdir(exist_ok=True)
    if Path(path).resolve()!=dest.resolve():shutil.copyfile(path,dest)
    text='\n\n'.join(f'=== PDF PAGE {i+1} ===\n'+t for i,t in enumerate(pages));atomic(project.path/'fulltext'/f'{id}.txt',text)
    p['pdf']=str(dest);p['pdf_pages']=len(pages);p['access_status']='pdf_verified';p['reading_status']='fulltext_available_not_read';project.save();project.event('pdf_verified',paper_id=id,pages=len(pages));return {'paper_id':id,'pages':len(pages)}
def resolve(project,id):
    p=project.get(id)
    if p['decision']!='include' or not any(e['required_depth']=='fulltext' for e in p['evidence']):return {'status':'not_required'}
    links=[x.get('url') for x in p.get('urls',[]) if x.get('documentStyle','').lower()=='pdf' and x.get('availabilityCode','').upper() in ('OA','F') and x.get('url')]
    if p.get('doi'):
        try:
            params={};key=os.getenv('OPENALEX_API_KEY')
            if key:params['api_key']=key
            o=http('https://api.openalex.org/works/https://doi.org/'+quote(p['doi'],safe=''),params).json()
            for x in ([o.get('best_oa_location')]+o.get('locations',[])):
                if x and x.get('is_oa') and x.get('pdf_url'):links.append(x['pdf_url'])
        except (requests.RequestException,ValueError) as e:project.event('oa_lookup_failed',paper_id=id,error=type(e).__name__)
    failures=[]
    for url in list(dict.fromkeys(links))[:5]:
        part=project.path/'pdf'/f'{id}.part';part.parent.mkdir(exist_ok=True)
        try:
            r=http(url)
            if len(r.content)>60*1024*1024:raise ContractError('PDF size limit')
            part.write_bytes(r.content);result=attach_local(project,id,part);p['download_url']=url;project.save();return result
        except (requests.RequestException,ValueError,RuntimeError) as e:failures.append(dict(url=url,error=type(e).__name__,reason=str(e)[:200]))
        finally:
            if part.exists():part.unlink()
    p['access_status']='manual_pdf_needed' if links or p.get('oa') else 'abstract_only_no_oa_found';p['download_failures']=failures;project.save();return {'paper_id':id,'status':p['access_status'],'doi':p.get('doi'),'title':p['title'],'failures':failures}
def record_read(project,record):
    p=project.get(record['paper_id'])
    if record.get('decision_maker')!='host_agent' or not record.get('summary'):raise ContractError('Agent reading summary required')
    pages=validate_pdf(p['pdf'],p)
    if not record.get('locators'):raise ContractError('At least one actual locator required')
    for x in record['locators']:
        i=x['pdf_page']-1
        if not 0<=i<len(pages) or not x.get('excerpt') or norm(x['excerpt']) not in norm(pages[i]):raise ContractError('Locator/excerpt not found in PDF')
    p['reading_status']='fulltext_read';p['reading_record']=record;project.save();project.event('agent_read',record=record)

class Zotero:
    def __init__(self,base,token=None):
        u=urlparse(base)
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or u.path:raise ContractError('Zotero must be a loopback origin')
        self.base=base.rstrip('/');self.session=requests.Session();self.session.trust_env=False
        self.session.headers.update({'Zotero-Allowed-Request':'true','Zotero-API-Version':'3'})
        if token:self.session.headers['X-Lit2Zotero-Token']=token
    def read(self,path):
        r=self.session.get(self.base+path,timeout=15);r.raise_for_status();r.encoding='utf-8';return r
    def bridge(self,op,**args):
        r=self.session.post(self.base+'/lit2zotero/v1',json=dict(op=op,**args),timeout=90);r.raise_for_status();r.encoding='utf-8';o=r.json()
        if not o.get('ok'):raise ContractError(o.get('error','Bridge failure'))
        return o['result']
class ExistingWriter(Zotero):
    """Compatibility with the installed zotero-write-endpoint. Metadata only."""
    def post(self,op,payload):
        r=self.session.post(self.base+'/zotero-write/'+op,json=payload,timeout=45);r.raise_for_status();r.encoding='utf-8';x=r.json()
        if x.get('error'):raise ContractError(x['error'])
        return x
    def bridge(self,op,**a):
        state=ROOT/'private/existing-collections.json';mapping=load(state) if state.exists() else {};project=a.get('project_id');identity=self.base+'|'+str(project)
        if op=='collection':
            name=a['name']+' ['+project[:8]+']'
            if not name.startswith('Lit2Zotero · '):raise ContractError('Managed collection prefix required')
            matches=[];start=0
            while True:
                part=self.read('/api/users/0/collections?limit=100&start='+str(start)).json();matches.extend(c for c in part if c['data']['name']==name)
                if len(part)<100:break
                start+=len(part)
            if len(matches)>1:raise ContractError('Ambiguous managed collection')
            c=matches[0]['data'] if matches else self.post('create-collection',dict(name=name))
            mapping[identity]=c['key'];write_json(state,mapping);return c
        if mapping.get(identity)!=a.get('collection_key'):raise ContractError('Unbound collection')
        if op=='attach':raise ContractError('Installed legacy plugin is metadata-only; install the scoped native bridge for PDF imports')
        if op!='upsert':raise ContractError('Unsupported operation')
        m=a['metadata'];q={'doi':m['DOI']} if m.get('DOI') else {'title':m['title']}
        found=self.post('search',dict(**q,limit=100))['items'];found=[x for x in found if x['itemType'] not in ('note','attachment') and ((m.get('DOI') and doi(x.get('DOI'))==doi(m['DOI'])) or norm(x['title'])==norm(m['title']))]
        if a.get('preferred_key'):found=[x for x in found if x['key']==a['preferred_key']]
        if a.get('preferred_key') and not found:raise ContractError('Reviewed binding no longer matches')
        if len(found)>1:raise ContractError('Ambiguous existing Zotero identity')
        if found:
            key=found[0]['key'];d=self.read('/api/users/0/items/'+key).json()['data']
            if title_key(d['title'])!=title_key(m['title']):raise ContractError('Existing title conflicts with identifier')
            if a['collection_key'] not in d.get('collections',[]):self.post('item-update',dict(items=[dict(key=key,collections=d.get('collections',[])+[a['collection_key']])]))
        else:key=self.post('create-items',dict(collections=[a['collection_key']],items=[m]))['created'][0]
        children=self.read('/api/users/0/items/'+key+'/children?limit=100').json();marker='Lit2Zotero '+project
        # The legacy endpoint cannot safely update notes; preserve one managed initial note.
        if not any(marker in x['data'].get('note','') for x in children):self.post('create-items',dict(items=[dict(itemType='note',parentItem=key,note='<p>'+marker+'</p><pre>'+html.escape(a['note'])+'</pre>')]))
        x=self.read('/api/users/0/items/'+key).json();library=x['library'];uri=x.get('links',{}).get('alternate',{}).get('href')
        if library['type']!='user' or not uri:raise ContractError('No supported personal-library URI')
        uri=uri.replace('https://www.zotero.org/','http://zotero.org/')
        return dict(key=key,uri=uri,library_id=library['id'])
def client(project):
    base=project.config.get('zotero_base','http://127.0.0.1:23119')
    if project.config.get('backend')=='existing':return ExistingWriter(base)
    c=load(ROOT/'private/bridge.json');return Zotero(base,c['token'])
def metadata(p):
    d=dict(itemType='journalArticle',title=p['title'],creators=p['authors'],date=p.get('date',''),DOI=p.get('doi',''),abstractNote=p.get('abstract',''),publicationTitle=p.get('journal',''),url='https://doi.org/'+p['doi'] if p.get('doi') else 'https://europepmc.org/article/MED/'+str(p.get('pmid','')))
    for k in ('volume','issue','pages'):
        if p.get(k):d[k]=str(p[k])
    d['extra']='\n'.join(k.upper()+': '+str(p[k]) for k in ('pmid','pmcid') if p.get(k));return d
def sync(project,apply=False):
    selected=[p for p in project.papers if p['decision']=='include']
    if not apply:return {'apply':False,'papers':[dict(paper_id=p['paper_id'],title=p['title']) for p in selected],'collection':project.config['collection_name']}
    z=client(project);root=z.bridge('collection',name=project.config['collection_name'],project_id=project.config['project_id']);project.config['collection_key']=root['key'];write_json(project.path/'project.json',project.config)
    results=[]
    for p in selected:
        try:
            if p['identity_status']!='verified_metadata':raise ContractError('Unresolved identity')
            result=z.bridge('upsert',collection_key=root['key'],project_id=project.config['project_id'],paper_id=p['paper_id'],preferred_key=p.get('preferred_zotero_key'),metadata=metadata(p),note=json.dumps(dict(reason=p['decision_reason'],evidence=p['evidence'],reading_status=p['reading_status']),ensure_ascii=False))
            saved=z.read('/api/users/0/items/'+result['key']).json();d=saved['data']
            if title_key(d['title'])!=title_key(p['title']) or (p.get('doi') and doi(d.get('DOI'))!=p['doi']):raise ContractError('Zotero readback identity mismatch')
            if root['key'] not in d.get('collections',[]):raise ContractError('Collection readback mismatch')
            p['zotero']=dict(item_key=result['key'],item_uri=result['uri'],library_id=result['library_id'],library_type='user',title=d['title'],verified_at=now());p['sync_status']='metadata_verified';project.save()
            if p.get('pdf'):
                a=z.bridge('attach',collection_key=root['key'],project_id=project.config['project_id'],item_key=result['key'],path=p['pdf']);p['zotero']['attachment_key']=a['key'];p['sync_status']='attachment_verified'
            project.save();results.append(dict(paper_id=p['paper_id'],status=p['sync_status']))
        except (requests.RequestException,ValueError,KeyError) as e:
            p['sync_status']='partial_or_failed';project.save();results.append(dict(paper_id=p['paper_id'],status='failed',error=str(e)[:250]))
    project.event('sync',results=results);return results
def handoff(project):
    z=client(project);rows=[]
    for p in project.papers:
        if p['decision']!='include':continue
        binding=p.get('zotero');technical=False;reason='not_synced'
        if binding:
            try:
                d=z.read('/api/users/0/items/'+binding['item_key']).json()['data'];technical=norm(d['title'])==norm(binding['title']) and (not p.get('doi') or doi(d.get('DOI'))==p['doi']);reason='verified' if technical else 'identity_changed'
            except requests.RequestException:reason='local_item_unavailable'
        for e in p['evidence']:
            claim=next(c for c in project.claims if c['claim_id']==e['claim_id']);read=p['reading_status']=='fulltext_read' if e['required_depth']=='fulltext' else p['reading_status'] in ('abstract_read','fulltext_read')
            ready=technical and read and e['relation']!='unresolved'
            rows.append(dict(claim_id=e['claim_id'],section_id=claim['section_id'],citation_anchor=claim['citation_anchor'],paper_id=p['paper_id'],exact_zotero_title=binding['title'] if binding else '',item_key=binding['item_key'] if binding else '',item_uri=binding['item_uri'] if binding else '',library_id=binding['library_id'] if binding else '',doi=p.get('doi',''),relation=e['relation'],reading_status=p['reading_status'],technical_ready=technical,evidence_ready=read and e['relation']!='unresolved',citation_ready=ready,technical_reason=reason,placeholder='【'+binding['title']+'】' if ready else '',scope=e['reason']))
    fields=list(rows[0]) if rows else ['claim_id','paper_id','citation_ready'];buf=io.StringIO();w=csv.DictWriter(buf,fields,delimiter='\t');w.writeheader();w.writerows(rows);atomic(project.path/'citation_handoff.tsv',buf.getvalue());return {'rows':len(rows),'ready':sum(r['citation_ready'] for r in rows)}

def main(argv=None):
    a=argparse.ArgumentParser();a.add_argument('--version',action='version',version=VERSION);s=a.add_subparsers(dest='cmd',required=True)
    x=s.add_parser('init');x.add_argument('--project',required=True);x.add_argument('--claims',required=True);x.add_argument('--collection',required=True);x.add_argument('--zotero-base',default='http://127.0.0.1:23119');x.add_argument('--backend',choices=['native','existing'],default='native')
    x=s.add_parser('doctor');x.add_argument('--zotero-base',default='http://127.0.0.1:23119')
    for name in ['discover','decide','resolve','attach','read','sync','handoff','bind']:
        x=s.add_parser(name);x.add_argument('--project',required=True)
        if name=='discover':x.add_argument('--query',required=True);x.add_argument('--provider',choices=['epmc','crossref'],default='epmc');x.add_argument('--pages',type=int,default=1)
        if name in ('decide','read'):x.add_argument('--record',required=True)
        if name in ('resolve','attach'):x.add_argument('--paper-id',required=True)
        if name=='attach':x.add_argument('--file',required=True)
        if name=='sync':x.add_argument('--apply',action='store_true')
        if name=='bind':x.add_argument('--paper-id',required=True);x.add_argument('--item-key',required=True);x.add_argument('--reason',required=True)
    args=a.parse_args(argv)
    if args.cmd=='doctor':
        z=Zotero(args.zotero_base);r=z.read('/api/');return {'python':sys.version.split()[0],'zotero_version':r.headers.get('X-Zotero-Version'),'read_status':r.status_code,'write_status':'not_tested','hashes_computed':False}
    if args.cmd=='init':
        p=Path(args.project).resolve()
        if not p.is_relative_to(ROOT):raise ContractError('Project output must remain inside this skill workspace')
        if p.exists() and any(p.iterdir()):raise ContractError('Project output must be empty')
        claims=load(args.claims)
        if not claims or len({c['claim_id'] for c in claims})!=len(claims):raise ContractError('Unique nonempty claims required')
        for c in claims:
            if not all(c.get(k) for k in ['claim_id','section_id','claim_text','citation_anchor']) or c.get('required_depth') not in ('abstract','fulltext'):raise ContractError('Invalid claim contract')
        p.mkdir(parents=True,exist_ok=True);write_json(p/'claims.json',claims);write_json(p/'project.json',dict(project_id=str(uuid.uuid4()),collection_name=args.collection,zotero_base=args.zotero_base,backend=args.backend,version=VERSION));return {'project':str(p)}
    p=Project(args.project)
    if args.cmd=='bind':
        paper=p.get(args.paper_id);obj=client(p).read('/api/users/0/items/'+args.item_key).json();d=obj['data']
        if not paper.get('doi') or doi(d.get('DOI'))!=paper['doi'] or title_key(d['title'])!=title_key(paper['title']):raise ContractError('Reviewed binding must have same DOI and complete normalized title')
        paper['preferred_zotero_key']=args.item_key;p.save();p.event('host_agent_binding',paper_id=args.paper_id,item_key=args.item_key,reason=args.reason);return {'binding':'verified'}
    if args.cmd=='discover':
        if not 1<=args.pages<=20:raise ContractError('pages must be 1..20; scope searches explicitly')
        return discover(p,args.query,args.provider,args.pages)
    if args.cmd=='decide':decide(p,load(args.record));return {'decisions':'recorded'}
    if args.cmd=='read':record_read(p,load(args.record));return {'reading':'recorded'}
    if args.cmd=='resolve':return resolve(p,args.paper_id)
    if args.cmd=='attach':return attach_local(p,args.paper_id,args.file)
    if args.cmd=='sync':return sync(p,args.apply)
    if args.cmd=='handoff':return handoff(p)
if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf8')
    try:
        result=main();print(json.dumps(result,ensure_ascii=False,indent=2))
        if isinstance(result,list) and any(x.get('status')=='failed' for x in result):sys.exit(2)
    except Exception as e: print(json.dumps({'error':type(e).__name__,'message':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
