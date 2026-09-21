"""Bind Word-skill mappings to reviewed local item identities; never edit DOCX."""
import argparse,csv,io,json
from pathlib import Path
from lit2zotero import Zotero,ContractError,title_key,doi,atomic,write_json
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f,delimiter='\t'))
def table(p,data):
    b=io.StringIO();w=csv.DictWriter(b,fieldnames=list(data[0]),delimiter='\t');w.writeheader();w.writerows(data);atomic(p,b.getvalue())
def select(title,records):
    matches=[x for x in records if title_key(x['exact_zotero_title'])==title_key(title)]
    if not matches or any(x['citation_ready']!='True' for x in matches):raise ContractError('Title not ready in handoff')
    if len({(x['item_key'],x['item_uri'],x['doi']) for x in matches})!=1:raise ContractError('Ambiguous handoff identity')
    return matches[0]
def bind(handoff,mapping,out,base='http://127.0.0.1:23119'):
    records=rows(handoff);mapping=Path(mapping);out=Path(out)
    if out.exists() and any(out.iterdir()):raise ContractError('Output must be empty')
    z=Zotero(base,'');selected={};resolved={};audit=[]
    mappings=rows(mapping/'zotero_title_match.tsv')
    for m in mappings:
        h=select(m['placeholder_title'],records)
        obj=z.read('/api/users/0/items/'+h['item_key']).json();d=obj['data']
        if title_key(d['title'])!=title_key(h['exact_zotero_title']) or doi(d.get('DOI'))!=doi(h['doi']):raise ContractError('Local item changed')
        library=str(obj['library']['id'])
        uri='http://zotero.org/users/'+library+'/items/'+h['item_key']
        if h['item_uri']!=uri or str(h['library_id'])!=library:raise ContractError('Library identity changed')
        csl=z.read('/api/users/0/items/'+h['item_key']+'?format=csljson').json()
        if isinstance(csl,list):
            if len(csl)!=1:raise ContractError('Expected one CSL object')
            csl=csl[0]
        if title_key(csl['title'])!=title_key(d['title']):raise ContractError('CSL title conflict')
        old=m['selected_key']
        # Explicit host-agent binding resolves duplicates, never by title rank.
        status='duplicate_same_doi_resolved' if int(m.get('candidate_count') or 0)>1 else 'normalized_unique'
        author=next((c.get('lastName','') for c in d.get('creators',[]) if c.get('creatorType')=='author'),'')
        m.update(status=status,selected_key=h['item_key'],selected_library_id=library,selected_title=d['title'],selected_first_author=author,selected_date=d.get('date',''),selected_doi=d.get('DOI',''),selected_citation_key='')
        selected[title_key(m['placeholder_title'])]=m
        resolved[h['item_key']]={'metadata':{'key':h['item_key'],'library_id':library,'title':d['title'],'doi':d.get('DOI',''),'first_author':author,'date':d.get('date',''),'citation_key':''},'csl':csl}
        audit.append({'title':d['title'],'old_key':old,'verified_key':h['item_key'],'source':'host_agent_reviewed_handoff'})
    occurrences=rows(mapping/'citation_placeholder_occurrences.tsv')
    for o in occurrences:
        m=selected[title_key(o['title'])]
        o.update(match_status=m['status'],selected_key=m['selected_key'],selected_library_id=m['selected_library_id'])
    out.mkdir(parents=True,exist_ok=True)
    table(out/'zotero_title_match.tsv',mappings);table(out/'citation_placeholder_occurrences.tsv',occurrences)
    write_json(out/'resolved_items.json',resolved);write_json(out/'binding_audit.json',audit)
    return {'status':'pass','titles':len(mappings),'changed_keys':sum(x['old_key']!=x['verified_key'] for x in audit)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--handoff',required=True);p.add_argument('--mapping',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(bind(a.handoff,a.mapping,a.out),ensure_ascii=False))
