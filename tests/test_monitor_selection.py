import time
from concurrent.futures import Future

from worker.runtime import MonitorRuntime
from server.trigger_settings import default_trigger_settings


def monitor(tmp_path, sources, config, settings=None):
    class Client:
        def configuration(self):
            return {'effective': config, 'triggers':default_trigger_settings(), **(settings or {})}
        def request(self, method, path, body=None):
            assert path == '/api/worker/discovery'
            return self.discovery
        def companion_heartbeat(self, payload):
            self.report = payload
    class Pool:
        def submit(self, *args):
            return Future()
        def shutdown(self, **kwargs):
            pass
    client = Client()
    client.discovery = {'sources': sources, 'errors': []}
    runtime = MonitorRuntime(client, tmp_path, lambda *args: None)
    runtime.pool.shutdown(wait=True)
    runtime.pool = Pool()
    return runtime, client


def config():
    return {'running': True, 'slots': 4, 'platformSlots': {'twitch': 2, 'kick': 2},
            'forced': [], 'favorites': [], 'forcedCategories': [], 'categories': []}


def source(platform, login, viewers=1):
    return {'platform': platform, 'login': login, 'live': True, 'viewers': viewers}


def test_forced_sources_preempt_existing_auto_scouts(tmp_path):
    cfg = config()
    sources = [source('kick', 'paulinholokobr', 1000), source('kick', 'other', 900),
               source('kick', 'spreen'), source('kick', 'yoloaventuras'),
               source('twitch', 'theburntpeanut'), source('twitch', 'zackrawrr')]
    runtime, client = monitor(tmp_path, sources, cfg, {'triggers': default_trigger_settings()})
    try:
        runtime.tick()
        old = runtime.active[('kick', 'paulinholokobr')]
        cfg['forced'] = [{'platform': s['platform'], 'login': s['login']} for s in sources[2:]]
        runtime.tick()
        assert old[1].is_set(), 'An auto-selected scout must yield to a newly forced source.'
        old[0].set_result(None)
        runtime.active[('kick', 'other')][0].set_result(None)
        runtime.tick()
        assert set(runtime.active) == {('kick', 'spreen'), ('kick', 'yoloaventuras'),
                                       ('twitch', 'theburntpeanut'), ('twitch', 'zackrawrr')}
    finally:
        runtime.close()


def test_configuration_change_refreshes_new_forced_source_without_wait(tmp_path):
    cfg = {**config(), 'slots': 1, 'platformSlots': {'twitch': 0, 'kick': 1}}
    runtime, client = monitor(tmp_path, [source('kick', 'old')], cfg)
    try:
        runtime.tick()
        cfg['forced'] = [{'platform': 'kick', 'login': 'spreen'}]
        client.discovery = {'sources': [source('kick', 'spreen')], 'errors': []}
        runtime.tick()
        assert [s['login'] for s in runtime.sources] == ['spreen']
    finally:
        runtime.close()


def test_failed_platform_discovery_preserves_running_scout(tmp_path):
    cfg = config()
    runtime, client = monitor(tmp_path, [source('kick', 'spreen'), source('twitch', 'one')], cfg)
    try:
        runtime.tick()
        client.discovery = {'sources': [source('twitch', 'one')],
                            'errors': [{'platform': 'kick', 'code': 'discovery_unavailable'}]}
        runtime.last_discovery = 0
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
        client.discovery = {'sources': [source('twitch', 'one')], 'errors': []}
        runtime.last_discovery = 0
        runtime.tick()
        assert runtime.active[('kick', 'spreen')][1].is_set()
    finally:
        runtime.close()


def test_heartbeat_does_not_report_retry_blocked_source_as_monitored(tmp_path):
    cfg = config()
    runtime, client = monitor(tmp_path, [source('kick', 'spreen')], cfg,
                              {'triggers': default_trigger_settings()})
    try:
        runtime.retries[('kick', 'spreen')] = time.monotonic() + 15
        runtime.tick()
        assert client.report['activeScouts'] == 0
        assert client.report['monitoredSources'] == []
    finally:
        runtime.close()

def test_automatic_scout_is_retained_when_popularity_changes(tmp_path):
    cfg = {**config(), 'slots': 1, 'platformSlots': {'twitch': 0, 'kick': 1}}
    runtime, client = monitor(tmp_path, [source('kick', 'spreen', 10), source('kick', 'other')], cfg)
    try:
        runtime.tick()
        client.discovery = {'sources': [source('kick', 'spreen'), source('kick', 'other', 1000)], 'errors': []}
        runtime.last_discovery = 0
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
        assert set(runtime.active) == {('kick', 'spreen')}
    finally:
        runtime.close()


def test_discovery_transport_failure_does_not_interrupt_active_scout(tmp_path, caplog):
    cfg = config()
    runtime, client = monitor(tmp_path, [source('kick', 'spreen')], cfg)
    try:
        runtime.tick()
        def unavailable(*args, **kwargs):
            raise ConnectionError('SECRET-URL')
        client.request = unavailable
        runtime.last_discovery = 0
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
        assert client.report['activeScouts'] == 1
        assert 'SECRET-URL' not in caplog.text
    finally:
        runtime.close()

def test_configuration_outage_keeps_scout_then_cancels_after_grace(tmp_path):
    import httpx
    cfg = config()
    runtime, client = monitor(tmp_path, [source('kick', 'spreen')], cfg)
    try:
        runtime.tick()
        def unavailable():
            raise httpx.ConnectError('SECRET-URL')
        client.configuration = unavailable
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
        assert runtime.latest['queueAvailable'] is False
        runtime.last_configuration = time.monotonic() - 61
        runtime.tick()
        assert runtime.active[('kick', 'spreen')][1].is_set()
    finally:
        runtime.close()


def test_heartbeat_transport_failure_does_not_stop_monitoring(tmp_path):
    import httpx
    cfg = config()
    runtime, client = monitor(tmp_path, [source('kick', 'spreen')], cfg)
    try:
        def unavailable(payload):
            raise httpx.ConnectError('SECRET-URL')
        client.companion_heartbeat = unavailable
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
        cfg['running'] = False
        runtime.tick()
        assert runtime.active[('kick', 'spreen')][1].is_set()
    finally:
        runtime.close()

def test_forced_category_keeps_existing_scout_until_window_finishes(tmp_path):
    cfg = {**config(), 'slots': 1, 'platformSlots': {'twitch': 0, 'kick': 1},
           'forcedCategories': [{'platform': 'kick', 'id': 'game', 'name': 'Game'}]}
    runtime, client = monitor(tmp_path, [{**source('kick', 'spreen', 10), 'categoryId': 'game'}], cfg)
    try:
        runtime.tick()
        client.discovery = {'sources': [{**source('kick', 'spreen'), 'categoryId': 'game'},
                                         {**source('kick', 'other', 1000), 'categoryId': 'game'}], 'errors': []}
        runtime.last_discovery = 0
        runtime.tick()
        assert not runtime.active[('kick', 'spreen')][1].is_set()
    finally:
        runtime.close()
