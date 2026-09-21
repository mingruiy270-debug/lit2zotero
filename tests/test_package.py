import json,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def validate_manifest(m):
    app=m['applications']['zotero']
    for key in ('id','update_url','strict_max_version'):
        if not app.get(key):raise ValueError('Missing '+key)
    if not app['update_url'].startswith('https:'):raise ValueError('Zotero requires secure updates')
class PackageTests(unittest.TestCase):
    def test_built_xpi(self):
        with zipfile.ZipFile(ROOT/'dist/lit2zotero-local.xpi') as z:
            self.assertEqual(set(z.namelist()),{'manifest.json','bootstrap.js','settings.json'})
            validate_manifest(json.loads(z.read('manifest.json')))
            for name in z.namelist():self.assertEqual(z.read(name),(ROOT/'bridge'/name).read_bytes())
    def test_missing_or_insecure_update_rejected(self):
        m={'applications':{'zotero':{'id':'test@local.invalid','strict_max_version':'9.*'}}}
        with self.assertRaises(ValueError):validate_manifest(m)
        m['applications']['zotero']['update_url']='file:///E:/updates.json'
        with self.assertRaises(ValueError):validate_manifest(m)
if __name__=='__main__':unittest.main()
