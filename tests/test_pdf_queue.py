import csv,sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lit2zotero import pdf_requirement,export_reading_queue,ContractError
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
        p=P();p.path=Path(__file__).parent/'work'/uuid.uuid4().hex;p.path.mkdir(parents=True)
        p.papers=[dict(paper_id='P1',title='Test fixture',decision='include',evidence=[{'required_depth':'fulltext'}],reading_status='unread',zotero={'pdf_attachment_keys':['TESTKEY']})]
        export_reading_queue(p)
        with (p.path/'reading_queue.tsv').open(encoding='utf8') as f:r=list(csv.DictReader(f,delimiter='\t'))[0]
        self.assertEqual(r['reading_collection'],'需要PDF');self.assertEqual(r['next_action'],'核查Zotero附件并接入精读')
        self.assertEqual(p.papers[0]['reading_status'],'unread')
if __name__=='__main__':unittest.main()
