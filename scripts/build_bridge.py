"""Build a machine-local XPI. Never distribute its embedded private settings."""
import json,secrets,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(root=ROOT):
    private=root/'private';private.mkdir(exist_ok=True)
    key=private/'bridge.json'
    if not key.exists():
        key.write_text(json.dumps({'token':secrets.token_urlsafe(36),'allowedRoot':str(root.resolve())},ensure_ascii=False),encoding='utf8')
    config=json.loads(key.read_text(encoding='utf8'))
    if len(config.get('token',''))<32:raise ValueError('Invalid local token')
    if Path(config['allowedRoot']).resolve()!=root.resolve():raise ValueError('Local configuration belongs to another location; review it before rebuilding')
    (root/'bridge/settings.json').write_bytes(key.read_bytes())
    manifest=json.loads((root/'bridge/manifest.json').read_text(encoding='utf8'))
    app=manifest['applications']['zotero']
    if not all(app.get(k) for k in ('id','update_url','strict_max_version')) or not app['update_url'].startswith('https:'):
        raise ValueError('Invalid Zotero manifest')
    dist=root/'dist';dist.mkdir(exist_ok=True)
    target=dist/'lit2zotero-local.xpi'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ('manifest.json','bootstrap.js','settings.json'):z.write(root/'bridge'/name,name)
    return target
if __name__=='__main__':print(build())
