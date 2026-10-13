"""Opt-in real Zotero health-only registration/revocation test, no library writes.

Run with the Zotero host's Python after installing bridge 0.2.0.
Adds ONE disposable client, then removes only that client; never prints credentials.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_bridge import build,registry_default,save_json

def main():
    registry=registry_default()
    session=requests.Session();session.trust_env=False
    client=None
    with tempfile.TemporaryDirectory(prefix='lit2zotero-registration-test-') as folder:
        root=Path(folder)
        (root/'bridge').mkdir()
        shutil.copy2(ROOT/'bridge/manifest.json',root/'bridge/manifest.json')
        try:
            build(root,registry,register_only=True)
            client=json.loads((root/'private/bridge.json').read_text(encoding='utf8'))
            def health(token,extra=None):
                headers={'X-Lit2Zotero-Token':token,'Zotero-Allowed-Request':'true'}
                headers.update(extra or {})
                return session.post('http://localhost:23119/lit2zotero/v1',headers=headers,json={'op':'health'},timeout=15)
            response=health(client['token'])
            assert response.status_code==200, 'New client health HTTP '+str(response.status_code)
            result=response.json()['result']
            assert result['workspace_id']==client['workspace_id'], 'Workspace identity mismatch'
            assert 'multi-workspace' in result['operations']
            assert health('invalid-test-token').status_code==403
            assert health(client['token'],{'Origin':'http://example.invalid'}).status_code==403
            print('PASS new workspace registered while plugin running; wrong token/browser rejected')
        finally:
            if client is not None:
                lock=registry.with_suffix('.lock')
                fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
                try:
                    data=json.loads(registry.read_text(encoding='utf8'))
                    data['clients']=[c for c in data['clients'] if c['workspace_id']!=client['workspace_id']]
                    save_json(registry,data)
                finally:
                    lock.unlink()
        assert health(client['token']).status_code==403, 'Revoked client accepted'
        print('PASS disposable client revoked without restart; no library operations performed')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('FAIL live registration test:',type(e).__name__)
        raise SystemExit(1)
