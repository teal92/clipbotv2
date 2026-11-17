import asyncio
from concurrent.futures import ThreadPoolExecutor

from server.edge_protection import AtomicBudget, EdgeProtection, Principal, verified_principal
from server.store import Store
from starlette.requests import Request


def test_rejected_peer_cannot_spend_other_tenants_global_budget():
    budget = AtomicBudget()
    assert budget.allow([('global', 3), ('peer-a', 1)])
    for _ in range(20):
        assert not budget.allow([('global', 3), ('peer-a', 1)])
    assert budget.allow([('global', 3), ('peer-b', 2)])
    assert budget.allow([('global', 3), ('peer-b', 2)])


def test_concurrent_budget_admission_is_atomic():
    budget = AtomicBudget()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: budget.allow([('global', 7), ('tenant', 7)]), range(100)))
    assert sum(results) == 7


def test_budget_survives_restart_and_expires(tmp_path):
    clock = [100.0]
    path = tmp_path / 'limits.sqlite'
    first = AtomicBudget(path, clock=lambda: clock[0])
    assert first.allow([('tenant', 1)])
    first.close()
    second = AtomicBudget(path, clock=lambda: clock[0])
    assert not second.allow([('tenant', 1)])
    clock[0] = 161
    assert second.allow([('tenant', 1)])
    second.close()


def test_bucket_capacity_fails_closed_and_recovers():
    clock = [100.0]
    budget = AtomicBudget(max_keys=2, clock=lambda: clock[0])
    assert budget.allow([('a', 1), ('b', 1)])
    assert not budget.allow([('c', 1)])
    clock[0] = 161
    assert budget.allow([('c', 1)])


def scope(path='/api/worker/chat', headers=(), peer='proxy'):
    return {'type': 'http', 'method': 'GET', 'path': path, 'headers': headers,
            'client': (peer, 123), 'query_string': b'', 'scheme': 'https', 'server': ('test', 443)}


async def invoke(guard, request):
    responses = []
    async def receive():
        return {'type': 'http.disconnect'}
    async def send(message):
        responses.append(message)
    await guard(request, receive, send)
    return responses[0]['status']


async def okay(scope, receive, send):
    await send({'type': 'http.response.start', 'status': 200, 'headers': []})
    await send({'type': 'http.response.body', 'body': b'ok'})


def test_forged_forwarded_headers_and_device_ids_cannot_escape_peer_limit():
    guard = EdgeProtection(okay)
    async def run():
        for i in range(60):
            assert await invoke(guard, scope(headers=[(b'x-forwarded-for', str(i).encode()),
                (b'x-device-id', str(i).encode())])) == 200
        assert await invoke(guard, scope(headers=[(b'x-forwarded-for', b'new')])) == 429
        assert await invoke(guard, scope(peer='different')) == 200
    asyncio.run(run())


def test_verified_accounts_support_thirty_users_eight_hundred_chat_polls():
    guard = EdgeProtection(okay, principal=lambda r: Principal(r.headers['user'], r.headers['device']))
    async def run():
        for user in range(30):
            for _ in range(800):
                assert await invoke(guard, scope(headers=[(b'user', str(user).encode()),
                    (b'device', str(user).encode())])) == 200
    asyncio.run(run())


def test_provider_refresh_and_plan_change_share_account_cost_limit():
    guard = EdgeProtection(okay, principal=lambda r: Principal('one'))
    async def run():
        for _ in range(6):
            assert await invoke(guard, scope('/api/billing/change/refresh')) == 200
        assert await invoke(guard, scope('/api/billing/change')) == 429
        assert await invoke(guard, scope('/api/pipeline/publish')) == 429
        assert await invoke(guard, scope('/api/connections/twitch/refresh')) == 200
        assert await invoke(guard, scope('/api/account')) == 200
    asyncio.run(run())


def test_background_provider_work_cannot_starve_connection_lifecycle(tmp_path):
    guard = EdgeProtection(okay, principal=lambda r: Principal('one'),
                           persistent_path=tmp_path/'limits.sqlite')
    async def run():
        for _ in range(6):
            assert await invoke(guard, scope('/api/worker/publication-status')) == 200
        assert await invoke(guard, scope('/api/worker/publication-status')) == 429
        for platform in ('twitch', 'kick', 'tiktok', 'instagram', 'facebook'):
            for action in ('start', 'callback', 'destinations'):
                assert await invoke(guard, scope(f'/api/connections/{platform}/{action}')) == 200
        # Each lifecycle channel stays bounded and shares its account limit
        # across platforms. Starting attempts cannot block returning callbacks.
        for action in ('start', 'callback', 'destinations'):
            assert await invoke(guard, scope(f'/api/connections/twitch/{action}')) == 200
            assert await invoke(guard, scope(f'/api/connections/kick/{action}')) == 429
    try:
        asyncio.run(run())
    finally:
        guard.close()
    restarted = EdgeProtection(okay, principal=lambda r: Principal('one'),
                               persistent_path=tmp_path/'limits.sqlite')
    try:
        assert asyncio.run(invoke(restarted, scope('/api/connections/twitch/start'))) == 429
    finally:
        restarted.close()


def test_stream_discovery_cannot_starve_paid_analysis(tmp_path):
    guard=EdgeProtection(okay,principal=lambda r:Principal('one','paired'),persistent_path=tmp_path/'limits.sqlite')
    async def run():
        for _ in range(6):assert await invoke(guard,scope('/api/worker/discovery'))==200
        assert await invoke(guard,scope('/api/worker/analyze'))==200
        for _ in range(5):assert await invoke(guard,scope('/api/worker/analyze'))==200
        assert await invoke(guard,scope('/api/worker/analyze'))==429
        assert await invoke(guard,scope('/api/billing/change/refresh'))==200
    try:asyncio.run(run())
    finally:guard.close()


def test_analysis_rate_limit_persists_across_restart(tmp_path):
    path=tmp_path/'limits.sqlite';principal=lambda r:Principal('one','paired')
    first=EdgeProtection(okay,principal=principal,persistent_path=path)
    async def fill():
        for _ in range(6):assert await invoke(first,scope('/api/worker/analyze'))==200
    asyncio.run(fill());first.close()
    second=EdgeProtection(okay,principal=principal,persistent_path=path)
    try:assert asyncio.run(invoke(second,scope('/api/worker/analyze')))==429
    finally:second.close()


def test_sse_concurrency_releases_slots_after_cancellation():
    started = asyncio.Event()
    release = asyncio.Event()
    async def stream(scope, receive, send):
        started.set()
        await release.wait()
        await okay(scope, receive, send)
    guard = EdgeProtection(stream, principal=lambda r: Principal('one'))
    async def run():
        tasks = [asyncio.create_task(invoke(guard, scope('/api/events'))) for _ in range(3)]
        await started.wait()
        await asyncio.sleep(0)
        assert await invoke(guard, scope('/api/events')) == 429
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        release.set()
        assert await invoke(guard, scope('/api/events')) == 200
    asyncio.run(run())


def test_store_resolver_rejects_forged_device_and_expired_session(tmp_path):
    store = Store(tmp_path / 'accounts.sqlite')
    user = store.create_user('one@example.invalid', 'long-password-for-tests', 'one')
    session, _ = store.new_session(user)
    device = store.connect_worker(store.new_pairing(user))
    resolve = verified_principal(store)
    assert resolve(Request(scope(headers=[(b'authorization', ('Bearer ' + device).encode())])) ) == Principal(user, device)
    assert resolve(Request(scope(headers=[(b'authorization', b'Bearer forged-device-token')])) ) is None
    assert resolve(Request(scope('/api/account', headers=[(b'cookie', ('clipbot_session=' + session).encode())]))) == Principal(user)
    assert resolve(Request(scope('/api/worker/pairing', headers=[(b'cookie', ('clipbot_session=' + session).encode())]))) == Principal(user)
    assert resolve(Request(scope('/api/worker/revoke', headers=[(b'cookie', ('clipbot_session=' + session).encode())]))) == Principal(user)
    store.logout(session)
    assert resolve(Request(scope('/api/account', headers=[(b'cookie', ('clipbot_session=' + session).encode())]))) is None


def test_exhausted_chat_peer_does_not_block_other_accounts_or_health():
    guard = EdgeProtection(okay, principal=lambda r: Principal('legit') if r.headers.get('user') else None)
    async def run():
        for _ in range(60):
            assert await invoke(guard, scope()) == 200
        for _ in range(100):
            assert await invoke(guard, scope()) == 429
        assert await invoke(guard, scope(headers=[(b'user', b'legit')], peer='other')) == 200
        assert await invoke(guard, scope('/healthz')) == 200
        assert await invoke(guard, scope('/api/billing/webhook')) == 200
    asyncio.run(run())


def test_costly_admission_persists_across_guard_restart(tmp_path):
    path = tmp_path / 'request-limits.sqlite'
    guard = EdgeProtection(okay, principal=lambda r: Principal('one'), persistent_path=path)
    async def run():
        for _ in range(6):
            assert await invoke(guard, scope('/api/billing/checkout')) == 200
        guard.close()
        restarted = EdgeProtection(okay, principal=lambda r: Principal('one'), persistent_path=path)
        assert await invoke(restarted, scope('/api/billing/change/refresh')) == 429
        restarted.close()
    asyncio.run(run())


def test_tenant_provider_quota_does_not_spend_another_tenants_budget():
    guard = EdgeProtection(okay, principal=lambda r: Principal(r.headers['user']))
    async def run():
        for _ in range(6):
            assert await invoke(guard, scope('/api/billing/checkout', [(b'user', b'one')])) == 200
        for _ in range(100):
            assert await invoke(guard, scope('/api/billing/checkout', [(b'user', b'one')])) == 429
        assert await invoke(guard, scope('/api/billing/checkout', [(b'user', b'two')])) == 200
    asyncio.run(run())


def test_verified_proxy_profile_separates_unauthenticated_public_peers(monkeypatch):
    monkeypatch.setenv('CLIPBOT_TRUSTED_EDGE', 'render-cloudflare')
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('CLIPBOT_TRUSTED_PROXY_CIDRS', '10.1.0.0/16')
    guard = EdgeProtection(okay)
    async def run():
        for _ in range(60):
            assert await invoke(guard, scope(headers=[(b'cf-connecting-ip', b'8.8.8.8')], peer='10.1.2.3')) == 200
        assert await invoke(guard, scope(headers=[(b'cf-connecting-ip', b'8.8.8.8')], peer='10.1.2.3')) == 429
        assert await invoke(guard, scope(headers=[(b'cf-connecting-ip', b'1.1.1.1')], peer='10.1.2.3')) == 200
    asyncio.run(run())
def test_expensive_authentication_is_globally_bounded_before_password_work():
    calls=[]
    async def password_work(scope,receive,send):
        calls.append(1)
        await okay(scope,receive,send)
    guard=EdgeProtection(password_work)
    async def run():
        for number in range(120):
            assert await invoke(guard,{**scope(path='/api/auth/login',peer=f'client-{number}'),'method':'POST'})==200
        assert await invoke(guard,{**scope(path='/api/auth/login',peer='fresh-client'),'method':'POST'})==429
    asyncio.run(run())
    assert len(calls)==120
