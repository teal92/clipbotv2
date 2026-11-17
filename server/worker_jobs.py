"""Tenant-owned durable processing jobs and compare-and-swap worker leases."""
import json,math,secrets,time
from .store import token_hash
from .pipeline_events import EventStore
from .scouts import source_identity,limits_in

class WorkerDenied(ValueError):pass

def device_user(db,token):
    if not isinstance(token,str) or not 20<=len(token)<=100:raise WorkerDenied('Reconnect your local worker.')
    row=db.execute('SELECT user_id FROM worker_devices WHERE token=? AND expires>?',(token_hash(token),time.time())).fetchone()
    if not row:raise WorkerDenied('Reconnect your local worker.')
    return row['user_id']

def capture_authorized(db,uid):
    from .billing_modes import entitlement_allowed
    if not entitlement_allowed(db,uid):raise WorkerDenied('Active scout coverage is required.')
    # Internal queued-job helpers do not create a billing bypass for a real plan.
    from .owner_showcase import operational_billing
    billing=operational_billing(db,uid)
    if not billing:return
    if billing['status']!='active' or billing['expires']<=time.time() or limits_in(db,uid)['scouts']<=0:
        raise WorkerDenied('Active scout coverage is required.')
    setting=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='scout_settings'").fetchone() else None
    if not setting:raise WorkerDenied('Monitoring is stopped or coverage is unavailable.')
    config=json.loads(setting['data'])
    if not config.get('running') or min(config.get('slots',0),limits_in(db,uid)['scouts'])<=0:
        raise WorkerDenied('Monitoring is stopped or coverage is unavailable.')

WORKER_TRANSITIONS={'queued':{'capturing'},'capturing':{'transcribing'},'transcribing':{'analyzing'},'rendering':{'ready'}}
METRICS={'cpuPercent':100,'memoryPercent':100,'freeDiskBytes':2**63-1,'queuedWindows':100,'activeScouts':40,'ingestBytes':2**63-1}

class WorkerJobs:
    def __init__(self,store):
        self.store=store;self.events=EventStore(store)
        with store.connection() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS pipeline_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,source TEXT NOT NULL,stage TEXT NOT NULL,lease TEXT,device TEXT,lease_expires REAL NOT NULL DEFAULT 0,metrics TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL,updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS pipeline_user_stage ON pipeline_jobs(user_id,stage,created);""")
            db.execute('CREATE TABLE IF NOT EXISTS candidate_previews(user_id TEXT NOT NULL,job_id TEXT NOT NULL,device TEXT NOT NULL,token TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(user_id,job_id))')
            if 'error_code' not in {r['name'] for r in db.execute('PRAGMA table_info(pipeline_jobs)')}:db.execute('ALTER TABLE pipeline_jobs ADD COLUMN error_code TEXT')
    def enqueue(self,uid,source):
        source=source_identity(source);now=time.time();job=secrets.token_hex(16)
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise WorkerDenied('Account not found.')
            if db.execute("SELECT COUNT(*) FROM pipeline_jobs WHERE user_id=? AND stage NOT IN ('published','failed','cancelled')",(uid,)).fetchone()[0]>=42:raise WorkerDenied('Processing queue is full.')
            db.execute('INSERT INTO pipeline_jobs(id,user_id,source,stage,created,updated) VALUES(?,?,?,?,?,?)',(job,uid,json.dumps(source),'queued',now,now))
        self.events.emit(uid,'job_enqueued',job_id=job,stage='queued',platform=source['platform'],login=source['login'])
        return job
    def open(self,device_token,source):
        source=source_identity(source);serialized=json.dumps(source);now=time.time()
        with self.store.connection(atomic=True) as db:
            uid=device_user(db,device_token);limits=limits_in(db,uid)
            from .customer_access import require_customer_ready
            require_customer_ready(self.store,uid,db=db)
            self.expire_captures(db,uid,now)
            setting=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone()
            config=json.loads(setting['data']) if setting else {}
            capacity=min(config.get('slots',0),limits['scouts'])
            if not config.get('running') or capacity<=0:raise WorkerDenied('Monitoring is stopped or coverage is unavailable.')
            # Render/review queues are bounded separately from active capture slots.
            active=db.execute("SELECT COUNT(*) FROM pipeline_jobs WHERE user_id=? AND stage IN ('queued','capturing')",(uid,)).fetchone()[0]
            pending=db.execute("SELECT COUNT(*) FROM pipeline_jobs WHERE user_id=? AND stage IN ('queued','capturing','transcribing','analyzing','rendering')",(uid,)).fetchone()[0]
            duplicate=db.execute("SELECT 1 FROM pipeline_jobs WHERE user_id=? AND source=? AND stage IN ('queued','capturing','transcribing','analyzing','rendering')",(uid,serialized)).fetchone()
            platform_capacity=config.get('platformSlots',{}).get(source['platform'],capacity)
            platform_active=sum(json.loads(r['source'])['platform']==source['platform'] for r in db.execute("SELECT source FROM pipeline_jobs WHERE user_id=? AND stage IN ('queued','capturing')",(uid,)))
            reviews=db.execute("SELECT COUNT(*) FROM pipeline_jobs WHERE user_id=? AND stage='review'",(uid,)).fetchone()[0]
            if reviews>=40 or active>=capacity or platform_active>=platform_capacity or pending>=capacity+2 or duplicate:raise WorkerDenied('Scout slots or processing queue are busy.')
            job=secrets.token_hex(16);lease=secrets.token_hex(16)
            db.execute('INSERT INTO pipeline_jobs(id,user_id,source,stage,lease,device,lease_expires,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(job,uid,serialized,'queued',lease,token_hash(device_token),now+120,now,now))
        self.events.emit(uid,'job_opened',job_id=job,stage='queued',platform=source['platform'],login=source['login'])
        return {'id':job,'source':source,'stage':'queued','lease':lease,'leaseExpires':now+120}
    @staticmethod
    def expire_captures(db,uid,now):
        # A lost capture has no verified complete window. Never reuse its old lease.
        db.execute("UPDATE pipeline_jobs SET stage='failed',lease=NULL,updated=? WHERE user_id=? AND stage IN ('queued','capturing') AND lease IS NOT NULL AND lease_expires<=?",(now,uid,now))
    def resume(self,device_token,job_id):
        now=time.time()
        with self.store.connection(atomic=True) as db:
            uid=device_user(db,device_token)
            from .owner_showcase import operational_cancellation_revoked
            if operational_cancellation_revoked(db,uid):raise WorkerDenied('Subscription cancellation has ended access.')
            row=db.execute("SELECT * FROM pipeline_jobs WHERE id=? AND user_id=? AND lease_expires<=? AND stage IN ('transcribing','analyzing','review','rendering','ready')",(job_id,uid,now)).fetchone()
            if not row:raise WorkerDenied('Job cannot be resumed or its current lease is still active.')
            if row['stage'] in ('analyzing','transcribing'):
                run=db.execute('SELECT status FROM analysis_runs WHERE user_id=? AND job_id=?',(uid,job_id)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='analysis_runs'").fetchone() else None
                if run and run['status']!='settled':raise WorkerDenied('Paid analysis requires reconciliation; automatic retries are disabled.')
            lease=secrets.token_hex(16)
            stage='transcribing' if row['stage']=='analyzing' else row['stage']
            db.execute('UPDATE pipeline_jobs SET lease=?,device=?,lease_expires=?,stage=?,updated=? WHERE id=?',(lease,token_hash(device_token),now+120,stage,now,job_id))
            result={'id':job_id,'source':json.loads(row['source']),'stage':stage,'lease':lease,'leaseExpires':now+120}
        self.events.emit(uid,'job_resumed',job_id=job_id,stage=stage,source='worker')
        return result
    def claim(self,device_token):
        now=time.time()
        with self.store.connection(atomic=True) as db:
            uid=device_user(db,device_token)
            capture_authorized(db,uid)
            from .customer_access import require_customer_ready
            require_customer_ready(self.store,uid,db=db)
            row=db.execute("SELECT * FROM pipeline_jobs WHERE user_id=? AND stage='queued' AND lease_expires<=? ORDER BY created LIMIT 1",(uid,now)).fetchone()
            if not row:return None
            lease=secrets.token_hex(16)
            db.execute('UPDATE pipeline_jobs SET lease=?,device=?,lease_expires=?,updated=? WHERE id=?',(lease,token_hash(device_token),now+120,now,row['id']))
            result={'id':row['id'],'source':json.loads(row['source']),'stage':row['stage'],'lease':lease,'leaseExpires':now+120}
        self.events.emit(uid,'job_claimed',job_id=row['id'],stage=row['stage'],source='worker')
        return result
    def report(self,device_token,job_id,lease_id,event):
        if not isinstance(event,dict) or set(event)-{'stage','metrics','errorCode'}:raise WorkerDenied('Invalid worker event.')
        stage=event.get('stage');metrics=event.get('metrics',{})
        if not isinstance(metrics,dict) or set(metrics)-set(METRICS):raise WorkerDenied('Invalid worker metrics.')
        for key,value in metrics.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=METRICS[key]:raise WorkerDenied('Invalid worker metrics.')
        from .pipeline_events import CODES
        if event.get('errorCode') is not None and event.get('errorCode') not in CODES:raise WorkerDenied('Invalid worker error.')
        now=time.time()
        with self.store.connection(atomic=True) as db:
            uid=device_user(db,device_token)
            row=db.execute('SELECT * FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>?',(job_id,uid,lease_id,token_hash(device_token),now)).fetchone()
            if not row:raise WorkerDenied('Job lease expired, cancelled or belongs to another worker.')
            from .owner_showcase import operational_cancellation_revoked
            if stage!='failed' and operational_cancellation_revoked(db,uid):raise WorkerDenied('Subscription cancellation has ended access.')
            if stage=='capturing':
                capture_authorized(db,uid)
                from .customer_access import require_customer_ready
                require_customer_ready(self.store,uid,db=db)
            if row['stage'] in ('failed','cancelled','published','publishing'):raise WorkerDenied('Job is no longer accepting worker events.')
            if stage!=row['stage'] and stage not in WORKER_TRANSITIONS.get(row['stage'],set()) and stage!='failed':raise WorkerDenied('Invalid processing transition.')
            db.execute('UPDATE pipeline_jobs SET stage=?,metrics=?,lease_expires=?,updated=?,error_code=? WHERE id=?',(stage,json.dumps(metrics),0 if stage=='failed' else now+120,now,event.get('errorCode'),job_id))
        if stage!=row['stage'] or event.get('errorCode'):
            self.events.emit(uid,'job_reported',job_id=job_id,stage=stage,code=event.get('errorCode'),elapsed_ms=min(86400000,max(0,int((now-row['updated'])*1000))),source='worker',level='error' if stage=='failed' else 'info')
        return {'ok':True,'stage':stage}
    def cancel(self,uid,job_id):
        with self.store.connection(atomic=True) as db:
            result=db.execute("UPDATE pipeline_jobs SET stage='cancelled',lease=NULL,lease_expires=0,updated=? WHERE id=? AND user_id=? AND stage NOT IN ('published','publishing','cancelled')",(time.time(),job_id,uid))
            cancelled=result.rowcount==1
        if cancelled:self.events.emit(uid,'job_cancelled',job_id=job_id,stage='cancelled')
        return cancelled
    def snapshot(self,uid):
        with self.store.connection() as db:
            return [{'id':r['id'],'source':json.loads(r['source']),'stage':r['stage'],'metrics':json.loads(r['metrics']),'updated':r['updated'],'created':r['created'],'errorCode':r['error_code']} for r in db.execute('SELECT * FROM pipeline_jobs WHERE user_id=? ORDER BY created DESC LIMIT 100',(uid,))]
