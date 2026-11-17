"""Single-worker application backstop; this is not an edge WAF.

Install inside origin/body/security validation. Disable proxy-header rewriting
unless the deployment has a verified, narrowly trusted proxy configuration.
"""
import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from .client_ip import client_ip


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class AtomicBudget:
    """Bounded fixed 60-second windows, charged only on complete admission.

    Optional SQLite persistence is for low-volume costly/write groups. Chat and
    ordinary reads must use memory to avoid disk writes on every poll. One
    service worker is required; this is not a distributed quota implementation.
    """
    def __init__(self, path=None, *, max_keys=8192, clock=time.time):
        self.clock = clock
        self.max_keys = max_keys
        self.lock = threading.Lock()
        self.buckets = {}
        self.db = sqlite3.connect(path, check_same_thread=False) if path else None
        if self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('CREATE TABLE IF NOT EXISTS request_limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,expires REAL NOT NULL)')
            self.db.execute('DELETE FROM request_limits WHERE expires<=?', (self.clock(),))
            self.buckets = {key: (count, expires) for key, count, expires in self.db.execute('SELECT key,count,expires FROM request_limits')}
            if len(self.buckets) > self.max_keys:
                self.db.close()
                raise RuntimeError('Request-limit state exceeds configured capacity')
            self.db.commit()
        self.next_sweep = 0

    def allow(self, checks):
        with self.lock:
            now = self.clock()
            if now >= self.next_sweep:
                self.buckets = {k: v for k, v in self.buckets.items() if v[1] > now}
                if self.db:
                    self.db.execute('DELETE FROM request_limits WHERE expires<=?', (now,))
                    self.db.commit()
                self.next_sweep = now + 10
            proposed = {}
            for key, limit in checks:
                if not isinstance(limit, int) or limit < 1:
                    raise ValueError('Invalid request limit')
                key = digest(repr(key))
                count, expires = self.buckets.get(key, (0, now + 60))
                if expires <= now:
                    count, expires = 0, now + 60
                if count >= limit:
                    return False
                proposed[key] = (count + 1, expires)
            if len(self.buckets.keys() | proposed.keys()) > self.max_keys:
                return False
            if self.db:
                try:
                    self.db.executemany('INSERT OR REPLACE INTO request_limits VALUES(?,?,?)',
                        [(k, v[0], v[1]) for k, v in proposed.items()])
                    self.db.commit()
                except sqlite3.Error:
                    self.db.rollback()
                    return False
            self.buckets.update(proposed)
            return True

    def close(self):
        if self.db:
            with self.lock:
                self.db.close()
                self.db=None


@dataclass(frozen=True)
class Principal:
    account: str
    device: str | None = None


def verified_principal(store):
    """Only database-verified cookies/devices become quota principals."""
    def resolve(request):
        if request.url.path.startswith('/api/worker/') and request.url.path not in ('/api/worker/pairing', '/api/worker/revoke'):
            from .worker_jobs import device_user, WorkerDenied
            header = request.headers.get('authorization', '')
            token = header[7:] if header.startswith('Bearer ') else ''
            if not 20 <= len(token) <= 100:
                return None
            with store.connection() as db:
                try:
                    return Principal(device_user(db, token), token)
                except WorkerDenied:
                    return None
        token = request.cookies.get('clipbot_session', '')
        if not 20 <= len(token) <= 100:
            return None
        session = store.session(token)
        return Principal(session['user_id']) if session else None
    return resolve


def request_policy(method, path):
    # A cold module-based frontend needs more than sixty asset requests.
    # Give bounded public assets their own bucket; never relax API quotas.
    if method in ('GET','HEAD') and (path=='/' or path.startswith('/js/') and path.endswith('.js') or path.startswith('/css/') and path.endswith('.css') or path in ('/showcase/demo.js','/showcase/demo.css','/showcase/landing.css')):
        return 'static',240
    if path in ('/api/auth/login','/api/auth/signup','/api/auth/reset-password'):
        return 'authentication',20
    if path == '/healthz':
        return 'health', 1200
    if path in ('/api/billing/webhook', '/api/events/kick/chat'):
        return 'webhook', 3000
    if method == 'GET' and path == '/api/worker/chat':
        return 'chat', 1200
    # Routine discovery and old publication polls cannot consume admission for
    # paid analysis. Each channel retains a bounded, persistent account quota.
    if path=='/api/worker/analyze':return 'analysis',6
    if path in ('/api/worker/discovery','/api/scouts/discover','/api/scouts/categories','/api/scouts/category-coverage'):return 'discovery',6
    # Interactive account authorization must not compete with background
    # publishing/billing polls. Fixed channels prevent arbitrary-path buckets;
    # separate callbacks leave room to finish sign-ins after starting them.
    parts = path.split('/')
    if (len(parts) == 5 and parts[:3] == ['', 'api', 'connections']
            and parts[3] in ('twitch', 'kick', 'tiktok', 'instagram', 'facebook')):
        if parts[4] == 'start':return 'connection-start',6
        if parts[4] == 'callback':return 'connection-callback',6
        if parts[4] in ('refresh', 'destinations'):return 'connection-manage',6
    costly = path in {'/api/billing/checkout', '/api/billing/change', '/api/billing/change/refresh',
        '/api/scouts/discover', '/api/scouts/categories', '/api/scouts/category-coverage',
        '/api/worker/discovery', '/api/pipeline/tiktok-settings', '/api/pipeline/publish',
        '/api/worker/publication-status', '/api/worker/uploaded'}
    costly |= path.startswith('/api/connections/') and path.endswith(('/refresh', '/destinations', '/start', '/callback'))
    costly |= path.startswith('/api/pipeline/publications/') and path.endswith('/reconcile')
    costly |= path.endswith('/analyze')
    if costly:
        return 'provider', 6
    if path == '/api/worker/jobs/open':
        return 'provider-job', 60
    if path.startswith('/api/worker/'):
        return 'worker', 480
    return ('write', 60) if method in ('POST', 'PATCH', 'PUT', 'DELETE') else ('read', 240)


class EdgeProtection:
    def __init__(self, app, principal=None, persistent_path=None, register=None):
        self.app = app
        self.principal = principal
        self.persistent_path=persistent_path
        self.budget = AtomicBudget()
        self.cost_budget = AtomicBudget(persistent_path)
        self.lookup_budget = AtomicBudget()
        self.streams = {}
        self.active = 0
        if register:register(self)
        self.stream_lock = threading.Lock()

    async def reject(self, scope, receive, send):
        await JSONResponse({'detail': 'Request limit reached. Wait one minute and try again.'},
            status_code=429, headers={'Retry-After': '60', 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff'})(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        # Native peer by default; optional operator-verified proxy profile only
        # changes quota attribution, never account/device identity.
        peer = digest(client_ip(request))
        group, limit = request_policy(request.method, scope.get('path', ''))
        # This coarse channel-specific cap runs BEFORE principal/database lookups.
        aggregate = 60000 if group == 'chat' else 120 if group=='authentication' else 12000
        if not self.lookup_budget.allow([(('lookup-global', group), aggregate * 4),
                (('lookup-peer', group, peer), 40000 if group == 'chat' else 6000)]):
            await self.reject(scope, receive, send)
            return
        identity = self.principal(request) if self.principal and group not in ('health', 'webhook','static') else None
        if identity is not None and not isinstance(identity, Principal):
            raise TypeError('Principal resolver must return a verified Principal or None')
        account = digest(identity.account) if identity else None
        checks = [(('global', group), aggregate), (('peer', group, peer),
            (40000 if group == 'chat' else 6000) if identity else (3000 if group == 'webhook' else 1200 if group == 'health' else 240 if group=='static' else 60))]
        if identity:
            checks.append((('account', group, account), limit))
            if identity.device:
                checks.append((('device', group, digest(identity.device)), limit))
        budget = self.cost_budget if group in ('provider','provider-job','analysis','discovery','write','authentication','connection-start','connection-callback','connection-manage') else self.budget
        if not budget.allow(checks):
            await self.reject(scope, receive, send)
            return
        stream = scope.get('path') == '/api/events'
        stream_key = account or peer
        with self.stream_lock:
            allowed = self.active < 256 and (not stream or
                (sum(self.streams.values()) < 200 and self.streams.get(stream_key, 0) < (3 if account else 1)))
            if allowed:
                self.active += 1
                if stream:
                    self.streams[stream_key] = self.streams.get(stream_key, 0) + 1
        if not allowed:
            await self.reject(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            with self.stream_lock:
                self.active -= 1
                if stream:
                    self.streams[stream_key] -= 1
                    if not self.streams[stream_key]:
                        del self.streams[stream_key]

    def close(self):
        self.cost_budget.close()
    def reopen(self):
        if self.persistent_path and self.cost_budget.db is None:
            self.cost_budget=AtomicBudget(self.persistent_path)
