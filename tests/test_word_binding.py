import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_word_mapping import select,ContractError
class BindingTests(unittest.TestCase):
    def row(self,**kw):
        return dict(exact_zotero_title='Cell–cell evidence',citation_ready='True',item_key='ABCDEFGH',item_uri='http://zotero.org/users/1/items/ABCDEFGH',doi='10.1234/example')|kw
    def test_uses_explicit_identity(self):
        self.assertEqual(select('Cell-cell evidence',[self.row()])['item_key'],'ABCDEFGH')
    def test_unread_not_allowed(self):
        with self.assertRaises(ContractError):select('Cell–cell evidence',[self.row(citation_ready='False')])
    def test_multiple_keys_not_arbitrarily_chosen(self):
        with self.assertRaises(ContractError):select('Cell–cell evidence',[self.row(),self.row(item_key='IJKLMNOP')])
    def test_other_title_not_allowed(self):
        with self.assertRaises(ContractError):select('Other paper',[self.row()])
if __name__=='__main__':unittest.main()
