import json,unittest,zipfile,tempfile,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_bridge import build
def validate_manifest(m):
    app=m['applications']['zotero']
    for key in ('id','update_url','strict_max_version'):
        if not app.get(key):raise ValueError('Missing '+key)
    if not app['update_url'].startswith('https:'):raise ValueError('Zotero requires secure updates')
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'one';self.registry=self.base/'shared/clients.json'
        shutil.copytree(ROOT/'bridge',self.root/'bridge',ignore=shutil.ignore_patterns('settings.json'))
    def test_built_xpi(self):
        with zipfile.ZipFile(build(self.root,self.registry)) as z:
            self.assertEqual(set(z.namelist()),{'manifest.json','bootstrap.js','settings.json'})
            validate_manifest(json.loads(z.read('manifest.json')))
            for name in z.namelist():self.assertEqual(z.read(name),(self.root/'bridge'/name).read_bytes())
            settings=json.loads(z.read('settings.json'));self.assertNotIn('token',settings)
            self.assertEqual(json.loads(z.read('manifest.json'))['applications']['zotero']['strict_max_version'],'10.0.*')
    def test_two_workspaces_idempotent(self):
        second=self.base/'two';shutil.copytree(self.root/'bridge',second/'bridge')
        first_xpi=build(self.root,self.registry).read_bytes()
        key=(self.root/'private/bridge.json').read_bytes()
        build(second,self.registry);build(self.root,self.registry)
        clients=json.loads(self.registry.read_text())['clients']
        self.assertEqual(len(clients),2)
        self.assertEqual((self.root/'private/bridge.json').read_bytes(),key)
        self.assertEqual(len({c['token'] for c in clients}),2)
        # The already installed package references a live registry, not a frozen client list.
        import io
        with zipfile.ZipFile(io.BytesIO(first_xpi)) as z:
            self.assertEqual(json.loads(z.read('settings.json'))['registryPath'],str(self.registry))
    def test_lock_refuses_concurrent_builder(self):
        self.registry.parent.mkdir();self.registry.with_suffix('.lock').touch()
        with self.assertRaises(ValueError):build(self.root,self.registry)
    def test_register_fork_without_rebuilding(self):
        manifest=self.root/'bridge/manifest.json';m=json.loads(manifest.read_text())
        m['applications']['zotero']['id']='lit2zotero-ggq@local.invalid';manifest.write_text(json.dumps(m))
        build(self.root,self.registry,register_only=True,legacy_namespace='lit2zotero.ggq',legacy_endpoint='/lit2zotero-ggq/v1')
        self.assertFalse((self.root/'dist').exists())
        c=json.loads(self.registry.read_text())['clients'][0]
        self.assertEqual(c['prefNamespace'],'lit2zotero.ggq')
        with self.assertRaises(ValueError):build(self.root,self.registry)
    def test_preserve_old_credentials(self):
        (self.root/'private').mkdir()
        old={'token':'s'*40,'allowedRoot':str(self.root)}
        (self.root/'private/bridge.json').write_text(json.dumps(old))
        build(self.root,self.registry)
        self.assertEqual(json.loads((self.root/'private/bridge.json').read_text())['token'],old['token'])
    def test_copied_credentials_rejected(self):
        build(self.root,self.registry)
        other=self.base/'other';shutil.copytree(self.root,other)
        with self.assertRaises(ValueError):build(other,self.registry)
    def test_corrupt_registry_not_overwritten(self):
        self.registry.parent.mkdir();self.registry.write_text('{bad')
        with self.assertRaises(ValueError):build(self.root,self.registry)
        self.assertEqual(self.registry.read_text(),'{bad')
    def test_missing_or_insecure_update_rejected(self):
        m={'applications':{'zotero':{'id':'test@local.invalid','strict_max_version':'9.*'}}}
        with self.assertRaises(ValueError):validate_manifest(m)
        m['applications']['zotero']['update_url']='file:///E:/updates.json'
        with self.assertRaises(ValueError):validate_manifest(m)
if __name__=='__main__':unittest.main()
