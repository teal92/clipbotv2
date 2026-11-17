import asyncio
from pathlib import Path
import httpx
from server.app import create_app
from server.store import Store

def test_cold_frontend_load_does_not_exhaust_sensitive_api_budget(tmp_path):
    async def check():
        app=create_app(Store(tmp_path/'preview.db'),origin='http://testserver')
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                assets=['/']+['/'+str(p.relative_to(Path('frontend'))).replace('\\','/') for p in Path('frontend').rglob('*') if p.suffix in ('.js','.css')]
                assert len(assets)>60
                for url in assets:assert (await client.get(url)).status_code==200,url
                assert (await client.get('/api/auth/options')).status_code==200
                for _ in range(59):assert (await client.get('/api/account')).status_code==401
                assert (await client.get('/api/account')).status_code==429
                assert (await client.get('/js/app.js')).status_code==200
        finally:
            app.state.edge_guard.cost_budget.close()
    asyncio.run(check())
