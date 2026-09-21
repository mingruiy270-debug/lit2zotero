import unittest,sys,json,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import lit2zotero as l
class Contracts(unittest.TestCase):
 def setUp(self):
  self.dir=Path(__file__).parent/'work'/uuid.uuid4().hex;self.dir.mkdir(parents=True)
  l.write_json(self.dir/'project.json',dict(project_id=str(uuid.uuid4()),collection_name='Lit2Zotero · contract test'))
  l.write_json(self.dir/'claims.json',[dict(claim_id='C1',section_id='M',claim_text='Method assumptions',citation_anchor='Sentence 1',required_depth='fulltext')]);self.p=l.Project(self.dir)
 def paper(self,title='A sufficiently descriptive scientific paper title',doi='10.1234/test'):
  return self.p.add(dict(title=title,doi=doi,abstract='A real abstract for a SOFTWARE TEST FIXTURE.',authors=[],sources=[]))
 def decision(self,p,**kw):
  d=dict(paper_id=p['paper_id'],decision='include',decision_maker='host_agent',reason='Test fixture',abstract_read=True,evidence=[dict(claim_id='C1',relation='supports',required_depth='fulltext',reason='Test assumptions')]);d.update(kw);return d
 def test_doi(self):self.assertEqual(l.doi('HTTPS://doi.org/10.1234/AbC'),'10.1234/abc')
 def test_invalid_doi(self):
  with self.assertRaises(l.ContractError):l.doi('not a doi')
 def test_duplicate(self):self.paper();self.paper();self.assertEqual(len(self.p.papers),1)
 def test_identifier_conflict(self):
  self.paper()
  with self.assertRaises(l.ContractError):self.paper(title='Entirely wrong paper')
 def test_title_different_doi(self):
  self.paper();b=self.paper(doi='10.1234/second');self.assertEqual(b['identity_status'],'title_collision')
  with self.assertRaises(l.ContractError):l.decide(self.p,[self.decision(b)])
 def test_tool_cannot_decide(self):
  p=self.paper()
  with self.assertRaises(l.ContractError):l.decide(self.p,[self.decision(p,decision_maker='search_tool')])
 def test_cannot_downgrade_reading(self):
  p=self.paper();d=self.decision(p);d['evidence'][0]['required_depth']='abstract'
  with self.assertRaises(l.ContractError):l.decide(self.p,[d])
 def test_no_abstract(self):
  p=self.paper();p['abstract']=''
  with self.assertRaises(l.ContractError):l.decide(self.p,[self.decision(p)])
 def test_valid_decision(self):
  p=self.paper();l.decide(self.p,[self.decision(p)]);self.assertEqual(self.p.get(p['paper_id'])['reading_status'],'abstract_read')
 def test_stale_project_write(self):
  other=l.Project(self.dir);self.paper();self.p.save();other.papers=[]
  with self.assertRaises(l.ContractError):other.save()
 def test_hyphen_title(self):self.assertEqual(l.title_key('Cell–cell methods.'),l.title_key('cell-cell methods'))
 def test_csl_utf8(self):
  from unittest.mock import Mock
  import requests
  r=requests.Response();r.status_code=200;r._content='[{"title":"细胞–cell Schäfer"}]'.encode('utf8');r.encoding='ISO-8859-1'
  z=l.Zotero('http://127.0.0.1:23119');z.session.get=Mock(return_value=r)
  self.assertEqual(z.read('/api/test').json()[0]['title'],'细胞–cell Schäfer')
 def test_redirect_limit(self):
  with self.assertRaises(l.ContractError):l.http('https://example.org',redirects=6)
 def test_unknown_claim_atomic(self):
  p=self.paper();d=self.decision(p);d['evidence'][0]['claim_id']='wrong'
  with self.assertRaises(l.ContractError):l.decide(self.p,[d])
  self.assertEqual(p['decision'],'defer')
 def test_dry_run_no_client(self):
  p=self.paper();l.decide(self.p,[self.decision(p)]);self.assertFalse(l.sync(self.p)['apply'])
 def test_localhost_only(self):
  with self.assertRaises(l.ContractError):l.Zotero('https://example.org')
 def test_loopback_pdf_denied(self):
  with self.assertRaises(l.ContractError):l.public_url('https://127.0.0.1/paper.pdf')
 def test_html_not_pdf(self):
  p=self.paper();f=self.dir/'wrong.pdf';f.write_text('<html>captcha</html>')
  with self.assertRaises(l.ContractError):l.validate_pdf(f,p)
 def test_pdf_wrong_identity(self):
  import pymupdf
  p=self.paper();d=pymupdf.open();d.new_page().insert_text((50,50),'Unrelated research');f=self.dir/'wrong.pdf';d.save(f)
  with self.assertRaises(l.ContractError):l.validate_pdf(f,p)
 def test_pdf_read_locator(self):
  import pymupdf
  p=self.paper();d=pymupdf.open();d.new_page().insert_text((50,50),p['title']+'\n'+p['doi']+'\nExample evidence.');f=self.dir/'good.pdf';d.save(f)
  l.attach_local(self.p,p['paper_id'],f);self.assertEqual(p['reading_status'],'fulltext_available_not_read')
  record=dict(paper_id=p['paper_id'],decision_maker='host_agent',summary='Software test only',locators=[dict(pdf_page=1,excerpt='Invented evidence')])
  with self.assertRaises(l.ContractError):l.record_read(self.p,record)
  record['locators'][0]['excerpt']='Example evidence.';l.record_read(self.p,record);self.assertEqual(p['reading_status'],'fulltext_read')
if __name__=='__main__':unittest.main(verbosity=2)
