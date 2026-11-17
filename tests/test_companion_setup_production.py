import re
from fastapi.testclient import TestClient
from worker.local_app import create_local_app
from worker.version import VERSION


def test_customer_setup_has_production_identity_and_no_testing_instructions(tmp_path):
    app=create_local_app(root=tmp_path,start_runtime=False)
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        page=client.get('/')
        assert '<title>ClipBot Companion' in page.text
        assert VERSION in page.text
        assert 'https://clipbot.your-domain.example' in page.text
        assert 'https://YOUR-GITHUB-USERNAME.github.io/ClipBotV2-setup-guide/' in page.text
        for old in ('first live test','first test is healthy','ClipBot Local Worker','8766','Sandbox','JSON.stringify(s.metrics)'):
            assert old not in page.text
        assert 'Your plan still controls' in page.text
        assert 'name=slots' not in page.text
        assert 'Start ClipBot' in page.text and '<button>Start' not in page.text
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert page.headers['cache-control']=='no-store'
        status=client.get('/status').json()
        assert status['version']==VERSION and not status['paired']
        assert not {'token','code','credential','csrfToken'} & status.keys()


def test_customer_pairing_script_keeps_security_and_clear_feedback(tmp_path):
    app=create_local_app(root=tmp_path,start_runtime=False)
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        page=client.get('/').text
        assert re.search("name=csrf content='([a-f0-9]+)'",page)
        script=client.get('/setup.js').text
        assert 'X-CSRF-Token' in script
        assert 'textContent' in script and '.innerHTML' not in script
        assert 'sessionStorage' not in script and 'localStorage' not in script
        assert 'response.ok' in script
        assert 'Connecting' in script


def test_pairing_script_behavior_uses_real_shipped_script(tmp_path):
    import shutil,subprocess
    from pathlib import Path
    import pytest
    from worker.setup_page import SETUP_JS
    node=shutil.which('node')
    if not node:pytest.skip('Node is required for browser-script verification')
    script=tmp_path/'setup.js';script.write_text(SETUP_JS,encoding='utf-8')
    subprocess.run([node,str(Path(__file__).with_name('companion-setup-script.cjs')),str(script)],check=True,timeout=15)
