"""Register this workspace with one per-user bridge; do not edit Zotero profiles."""
import argparse
import json
import os
import re
import secrets
import tempfile
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def registry_default():
    if os.name == 'nt':
        return Path(os.environ['LOCALAPPDATA']) / 'Lit2Zotero' / 'clients.json'
    return Path.home() / '.config' / 'lit2zotero' / 'clients.json'

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def build(root=ROOT, registry=None, register_only=False, legacy_namespace=None, legacy_endpoint=None):
    root = Path(root).resolve()
    registry = Path(registry or registry_default()).resolve()
    manifest = json.loads((root/'bridge/manifest.json').read_text(encoding='utf8'))
    app = manifest['applications']['zotero']
    if not register_only and app['id'] != 'lit2zotero@local.invalid':
        raise ValueError('Use the canonical plugin ID; do not fork a plugin per workspace')
    if not app.get('strict_max_version') or not app.get('update_url', '').startswith('https:'):
        raise ValueError('Invalid Zotero manifest')
    registry.parent.mkdir(parents=True, exist_ok=True)
    lock = registry.with_suffix('.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Bridge registration locked; check the other builder before retrying') from None
    os.close(fd)
    try:
        data = json.loads(registry.read_text(encoding='utf8')) if registry.exists() else {'schema_version': 1, 'clients': []}
        if data.get('schema_version') != 1 or not isinstance(data.get('clients'), list):
            raise ValueError('Invalid shared registry; refusing to overwrite')
        key = root/'private/bridge.json'
        config = json.loads(key.read_text(encoding='utf8')) if key.exists() else {
            'token': secrets.token_urlsafe(36), 'allowedRoot': str(root)}
        if len(config.get('token', '')) < 32 or Path(config.get('allowedRoot', '')).resolve() != root:
            raise ValueError('Local credentials belong to another workspace or are invalid')
        config.setdefault('workspace_id', str(uuid.uuid4()))
        for field, supplied, default in [('prefNamespace',legacy_namespace,'lit2zotero'),('endpoint',legacy_endpoint,'/lit2zotero/v1')]:
            if supplied and field in config and config[field]!=supplied:
                raise ValueError('Existing legacy mapping differs; review migration first')
            config.setdefault(field,supplied or default)
        if not re.fullmatch(r'lit2zotero(?:\.[a-z0-9_-]+)*', config['prefNamespace']):
            raise ValueError('Invalid legacy preference namespace')
        if not re.fullmatch(r'/lit2zotero(?:-[a-z0-9_-]+)?/v1', config['endpoint']):
            raise ValueError('Invalid legacy endpoint')
        if str(uuid.UUID(config['workspace_id'])) != config['workspace_id']:
            raise ValueError('Invalid workspace ID')
        for client in data['clients']:
            client.setdefault('prefNamespace','lit2zotero')
            client.setdefault('endpoint','/lit2zotero/v1')
            same = client.get('workspace_id') == config['workspace_id']
            if same and any(client.get(k)!=config.get(k) for k in ('token','allowedRoot','prefNamespace','endpoint')):
                raise ValueError('Workspace identity conflict; review rather than replace credentials')
            if not same and (client.get('token') == config['token'] or client.get('allowedRoot') == str(root)):
                raise ValueError('Duplicate token or workspace root')
        legacy = []
        for p in (root/'projects').rglob('project.json'):
            obj = json.loads(p.read_text(encoding='utf8'))
            value = obj.get('project_id', '')
            if str(uuid.UUID(value)) != value:
                raise ValueError('Invalid existing project ID')
            legacy.append(value)
        others = [c for c in data['clients'] if c.get('workspace_id') != config['workspace_id']]
        if any(set(legacy) & set(c.get('legacyProjectIds', [])) for c in others):
            raise ValueError('A copied project belongs to another workspace; review migration first')
        data['clients'] = others + [dict(config, legacyProjectIds=sorted(set(legacy)))]
        save_json(key, config)
        save_json(registry, data)
    finally:
        lock.unlink()
    if register_only:
        return registry
    # XPI references the registry, not a workspace token or frozen clients list.
    save_json(root/'bridge/settings.json', {'schema_version': 1, 'registryPath': str(registry)})
    dist = root/'dist'
    dist.mkdir(exist_ok=True)
    target = dist/'lit2zotero-local.xpi'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('manifest.json', 'bootstrap.js', 'settings.json'):
            z.write(root/'bridge'/name, name)
    return target

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, help='Registry path visible to the Zotero host; normally use its native Python')
    parser.add_argument('--workspace',type=Path,default=ROOT,help='Explicit workspace to register/build')
    parser.add_argument('--register-only',action='store_true',help='Register an existing workspace without rebuilding its legacy plugin')
    parser.add_argument('--legacy-namespace',help='Reviewed existing Zotero preference namespace')
    parser.add_argument('--legacy-endpoint',help='Reviewed existing bridge endpoint; restart the one plugin after adding an alias')
    args = parser.parse_args()
    print(build(root=args.workspace,registry=args.registry,register_only=args.register_only,legacy_namespace=args.legacy_namespace,legacy_endpoint=args.legacy_endpoint))
