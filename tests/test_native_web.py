import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from record_web_search import validate,record_search,ContractError
class NativeWebTests(unittest.TestCase):
    def record(self):
        return dict(actor='host_agent',tool='web.run',query='method benchmark',scope='test fixture',performed_at='2026-09-21T00:00:00Z',status='completed',results=[dict(title='Test title',url='https://example.org/paper',doi='10.1234/test')])
    def test_valid(self):self.assertEqual(validate(self.record())['status'],'completed')
    def test_tool_cannot_attest(self):
        r=self.record();r['actor']='search_tool'
        with self.assertRaises(ContractError):validate(r)
    def test_failure_not_success(self):
        r=self.record();r.update(status='unavailable',results=[],reason='Tool absent')
        self.assertEqual(validate(r)['status'],'unavailable')
    def test_empty_not_completed(self):
        r=self.record();r['results']=[]
        with self.assertRaises(ContractError):validate(r)
    def test_links_without_changing_decisions(self):
        class P:
            papers=[dict(paper_id='P123',doi='10.1234/test',decision='defer')]
            def event(self,*a,**kw):self.saved=kw
        p=P();out=record_search(p,self.record())
        self.assertEqual(out['linked_candidates'],1);self.assertEqual(p.papers[0]['decision'],'defer')
        self.assertEqual(p.saved['attestation'],'host_record_not_independently_verified')
if __name__=='__main__':unittest.main()
