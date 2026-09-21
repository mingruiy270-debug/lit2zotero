"""Record actual host-native web calls; this script is not a web search engine."""
import argparse,json
from datetime import datetime
from urllib.parse import urlparse
from lit2zotero import Project,ContractError,doi,load
def validate(record):
    if record.get('actor')!='host_agent':raise ContractError('Host agent record required')
    for k in ('tool','query','scope','performed_at'):
        if not isinstance(record.get(k),str) or not record[k].strip():raise ContractError('Missing '+k)
    datetime.fromisoformat(record['performed_at'].replace('Z','+00:00'))
    status=record.get('status')
    if status not in ('completed','no_results','failed','unavailable'):raise ContractError('Invalid search status')
    results=record.get('results')
    if not isinstance(results,list):raise ContractError('results list required')
    if status=='completed' and not results:raise ContractError('Use no_results for empty search')
    if status in ('no_results','unavailable') and results:raise ContractError('Invalid results for status')
    if status in ('failed','unavailable') and not record.get('reason'):raise ContractError('Failure reason required')
    for r in results:
        if not r.get('title'):raise ContractError('Result title required')
        for key in ('url','opened_url'):
            if key=='opened_url' and not r.get(key):continue
            u=urlparse(r.get(key,''))
            if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:raise ContractError('Invalid source URL')
        if r.get('doi'):doi(r['doi'])
    return record
def record_search(project,record):
    validate(record)
    links=[]
    for result in record['results']:
        ident=doi(result.get('doi'))
        links.append({'url':result['url'],'doi':ident,'paper_ids':[p['paper_id'] for p in project.papers if ident and p.get('doi')==ident]})
    project.event('host_native_web_search',record=record,identity_links=links,attestation='host_record_not_independently_verified')
    return {'status':'recorded','search_status':record['status'],'results':len(links),'linked_results':sum(bool(x['paper_ids']) for x in links),'linked_candidates':len({p for x in links for p in x['paper_ids']}),'decisions_changed':False}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--record',required=True);args=a.parse_args()
    try:print(json.dumps(record_search(Project(args.project),load(args.record)),ensure_ascii=False))
    except (ValueError,KeyError) as e:a.exit(1,str(e)+'\n')
