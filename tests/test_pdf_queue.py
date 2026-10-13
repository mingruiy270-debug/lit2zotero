import csv,sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lit2zotero import pdf_requirement,export_reading_queue,ContractError,task_mode,sync,handoff,set_mode
class PdfQueueTests(unittest.TestCase):
    def test_fulltext_any_claim(self):
        self.assertEqual(pdf_requirement({'evidence':[{'required_depth':'abstract'},{'required_depth':'fulltext'}]}),'required')
    def test_pdf_presence_not_requirement(self):
        self.assertEqual(pdf_requirement({'pdf':'available.pdf','evidence':[{'required_depth':'abstract'}]}),'not_required')
    def test_read_stays_required(self):
        self.assertEqual(pdf_requirement({'reading_status':'fulltext_read','evidence':[{'required_depth':'fulltext'}]}),'required')
    def test_unknown_rejected(self):
        with self.assertRaises(ContractError):pdf_requirement({'evidence':[]})
    def test_queue_attachment_not_read(self):
        class P:pass
        p=P();p.config={'task_mode':'writing'};p.path=Path(__file__).parent/'work'/uuid.uuid4().hex;p.path.mkdir(parents=True)
        p.papers=[dict(paper_id='P1',title='Test fixture',decision='include',evidence=[{'required_depth':'fulltext'}],reading_status='unread',zotero={'pdf_attachment_keys':['TESTKEY']})]
        export_reading_queue(p)
        with (p.path/'reading_queue.tsv').open(encoding='utf8') as f:r=list(csv.DictReader(f,delimiter='\t'))[0]
        self.assertEqual(r['reading_collection'],'需要PDF');self.assertEqual(r['next_action'],'核查Zotero附件并接入精读')
        self.assertEqual(p.papers[0]['reading_status'],'unread')
        p.config['task_mode']='biokb';export_reading_queue(p)
        with (p.path/'reading_queue.tsv').open(encoding='utf8') as f:r=list(csv.DictReader(f,delimiter='\t'))[0]
        self.assertEqual(r['reading_collection'],'');self.assertEqual(r['pdf_requirement'],'required')
    def test_biokb_always_pdf(self):
        self.assertEqual(pdf_requirement({'evidence':[{'required_depth':'abstract'}]},'biokb'),'required')
    def test_unspecified_mode_does_not_assume_writing(self):
        from types import SimpleNamespace
        p=SimpleNamespace(config={})
        with self.assertRaises(ContractError):task_mode(p)
        with self.assertRaises(ContractError):sync(p)
    def test_nonwriting_cannot_make_citation_handoff(self):
        from types import SimpleNamespace
        with self.assertRaises(ContractError):handoff(SimpleNamespace(config={'task_mode':'biokb'}))
    def test_mode_preview_no_change(self):
        from types import SimpleNamespace
        p=SimpleNamespace(config={})
        out=set_mode(p,'biokb','user requested KB')
        self.assertFalse(out['apply']);self.assertEqual(p.config,{})
    def test_modes_preview(self):
        from types import SimpleNamespace
        for mode,layout in [('writing','reading_groups'),('biokb','flat'),('research','flat')]:
            p=SimpleNamespace(config={'task_mode':mode,'collection_name':'test'},papers=[{'paper_id':'P1','title':'t','decision':'include','evidence':[{'required_depth':'abstract'}]}])
            out=sync(p);self.assertEqual(out['layout'],layout)
            self.assertEqual(out['papers'][0]['pdf_requirement'],'required' if mode=='biokb' else 'not_required')
if __name__=='__main__':unittest.main()
