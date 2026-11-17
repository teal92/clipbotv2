"""Account metadata only. Media never enters this database."""
import os
import hashlib, hmac, json, secrets, sqlite3, time, calendar, re
from datetime import datetime,timezone
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PREFS={'usagePreset':'paused','focus':'balanced','avoid':'personal','approval':'review'}

class UsernameChangeUnavailable(ValueError):
    pass

def normalize_username(value):
    if not isinstance(value,str):raise ValueError('Use a username of 3–30 letters, numbers or underscores.')
    username=value.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,30}',username):raise ValueError('Use a username of 3–30 letters, numbers or underscores.')
    return username

def username_available(db,username,exclude_uid=None):
    # Legacy display names reserve valid usernames until their owner changes them.
    return not db.execute("SELECT 1 FROM users WHERE lower(name)=? AND (? IS NULL OR id<>?) UNION ALL SELECT 1 FROM user_profiles WHERE username=? COLLATE NOCASE AND (? IS NULL OR user_id<>?) LIMIT 1",(username,exclude_uid,exclude_uid,username,exclude_uid,exclude_uid)).fetchone()

def username_change_available_at(changed_at):
    if changed_at is None:return None
    date=datetime.fromtimestamp(changed_at,timezone.utc)
    month_index=date.year*12+date.month-1+6;year,month=divmod(month_index,12);month+=1
    return date.replace(year=year,month=month,day=min(date.day,calendar.monthrange(year,month)[1])).timestamp()


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return salt+':'+digest

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

DUMMY_PASSWORD_HASH=password_hash('dummy-verification-password','00'*16)

class Store:
    def __init__(self,path):
        self.billing_mode=os.getenv("CLIPBOT_BILLING_MODE","test")
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS session_presence(token TEXT PRIMARY KEY,last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS beta_acceptance(user_id TEXT PRIMARY KEY,version TEXT NOT NULL,accepted REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS shared_feedback(id TEXT PRIMARY KEY,decision TEXT NOT NULL,reasons TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS legal_acceptances(user_id TEXT NOT NULL,version TEXT NOT NULL,accepted REAL NOT NULL,PRIMARY KEY(user_id,version));
            CREATE TABLE IF NOT EXISTS user_profiles(user_id TEXT PRIMARY KEY,username TEXT COLLATE NOCASE UNIQUE,avatar TEXT NOT NULL DEFAULT '',username_changed_at REAL);
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences(user_id TEXT PRIMARY KEY,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS coverage(user_id TEXT PRIMARY KEY,review_daily INTEGER NOT NULL,user_monthly INTEGER NOT NULL,scouts INTEGER NOT NULL,favorites INTEGER NOT NULL,categories INTEGER NOT NULL,posts INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(user_id TEXT NOT NULL,job_id TEXT NOT NULL,day TEXT NOT NULL,month TEXT NOT NULL,reserved INTEGER NOT NULL,spent INTEGER NOT NULL DEFAULT 0,input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'reserved',PRIMARY KEY(user_id,job_id));
            CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(user_id TEXT NOT NULL,candidate_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(user_id,candidate_id));
            CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL,data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS reports_user_created ON reports(user_id,created);
            CREATE TABLE IF NOT EXISTS worker_pairing(code TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS worker_devices(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL,last_seen REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS devices_user ON worker_devices(user_id);
            CREATE TABLE IF NOT EXISTS billing_requests(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,plan TEXT NOT NULL,session_id TEXT UNIQUE,url TEXT,created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS billing_request_users ON billing_requests(user_id,created);
            CREATE TABLE IF NOT EXISTS billing_state(user_id TEXT PRIMARY KEY,subscription TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,expires REAL NOT NULL,monthly_reviews INTEGER,request_id TEXT);
            CREATE TABLE IF NOT EXISTS billing_periods(user_id TEXT PRIMARY KEY,subscription TEXT NOT NULL,starts REAL NOT NULL,ends REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS job_timestamps(user_id TEXT NOT NULL,job_id TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,job_id));
            CREATE INDEX IF NOT EXISTS job_timestamp_user_created ON job_timestamps(user_id,created);
            CREATE TABLE IF NOT EXISTS billing_events(id TEXT PRIMARY KEY,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS billing_modes(resource TEXT NOT NULL,id TEXT NOT NULL,mode TEXT NOT NULL,PRIMARY KEY(resource,id));
            CREATE TABLE IF NOT EXISTS billing_cancellations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,subscription TEXT NOT NULL,mode TEXT NOT NULL,status TEXT NOT NULL,ends REAL NOT NULL,created REAL NOT NULL,UNIQUE(user_id,subscription,mode));
            CREATE TABLE IF NOT EXISTS billing_access_revocations(user_id TEXT NOT NULL,subscription TEXT NOT NULL,mode TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,subscription,mode));
            CREATE TABLE IF NOT EXISTS guards(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_attempts(ip TEXT NOT NULL,created REAL NOT NULL);
            ''')
            if 'username_changed_at' not in {row[1] for row in db.execute('PRAGMA table_info(user_profiles)')}:
                db.execute('ALTER TABLE user_profiles ADD COLUMN username_changed_at REAL')
                # Earlier releases did not record rename dates; begin their interval now.
                db.execute("UPDATE user_profiles SET username_changed_at=? WHERE username IS NOT NULL AND username!=''",(time.time(),))
            if 'request_id' not in {row[1] for row in db.execute('PRAGMA table_info(billing_state)')}:db.execute('ALTER TABLE billing_state ADD COLUMN request_id TEXT')
            # Legacy sandbox records remain test records even after a deployment changes mode.
            db.execute("INSERT OR IGNORE INTO billing_modes SELECT 'request',id,'test' FROM billing_requests")
            db.execute("INSERT OR IGNORE INTO billing_modes SELECT 'state',user_id,'test' FROM billing_state")
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='billing_changes' AND type='table'").fetchone():
                db.execute("INSERT OR IGNORE INTO billing_modes SELECT 'change',id,'test' FROM billing_changes")
    @contextmanager
    def connection(self,atomic=False):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        db.execute('CREATE TEMP TABLE runtime_billing_mode(mode TEXT NOT NULL)')
        db.execute('INSERT INTO runtime_billing_mode VALUES(?)',(self.billing_mode,))
        db.commit()
        try:
            if atomic:db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()
    def create_user(self,email,password,name,terms_version=None,signup_username=False):
        if signup_username:name=normalize_username(name)
        uid=secrets.token_hex(16);hashed=password_hash(password);now=time.time()
        with self.connection(atomic=True) as db:
            if signup_username and not username_available(db,name):raise sqlite3.IntegrityError('Username unavailable')
            db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(uid,email,hashed,name,now))
            if signup_username:db.execute('INSERT INTO user_profiles(user_id,username,username_changed_at) VALUES(?,?,?)',(uid,name,now))
            if terms_version:db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)',(uid,terms_version,time.time()))
        return uid
    def authenticate(self,email,password):
        with self.connection() as db:row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        # Hash absent users as well, avoiding a fast account-existence check.
        saved=row['password'] if row else DUMMY_PASSWORD_HASH
        valid=hmac.compare_digest(password_hash(password,saved.split(':')[0]),saved)
        return row['id'] if row and valid else None
    def user(self,uid):
        with self.connection() as db:row=db.execute("SELECT u.id,u.email,COALESCE(NULLIF(p.username,''),u.name) AS name,u.created,COALESCE(NULLIF(p.username,''),u.name) AS username,COALESCE(p.avatar,'') AS avatar,p.username_changed_at AS usernameChangedAt FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?",(uid,)).fetchone()
        if not row:return None
        result=dict(row);result['usernameChangeAvailableAt']=username_change_available_at(result['usernameChangedAt']);return result
    def new_session(self,uid):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token_hash(token),uid,csrf,time.time()+86400))
        return token,csrf
    def session(self,token):
        with self.connection() as db:row=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(token_hash(token),time.time())).fetchone()
        return dict(row) if row else None
    def logout(self,token):
        with self.connection() as db:db.execute('DELETE FROM sessions WHERE token=?',(token_hash(token),))
    def get_preferences(self,uid):
        with self.connection() as db:row=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
        return json.loads(row['data']) if row else dict(DEFAULT_PREFS)
    def save_preferences(self,uid,data):
        with self.connection(atomic=True) as db:
            self.save_preferences_in(db,uid,data)
    def save_preferences_in(self,db,uid,data):
        row=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
        old=json.loads(row['data']) if row else {}
        db.execute('INSERT OR REPLACE INTO preferences VALUES(?,?)',(uid,json.dumps(data)))
        if getattr(self,'davey',None) and any(old.get(key,default)!=data.get(key,default) for key,default in [('focus','balanced'),('avoid','personal')]):
            self.davey.preference_changed(db,uid)
    def coverage(self,uid,*,include_showcase=True):
        # Entitlement and posting projection come from one SQLite read snapshot.
        with self.connection() as db:
            from .owner_showcase import showcase_in
            showcase=showcase_in(db,uid) if include_showcase else None
            if showcase:return showcase
            from .billing_modes import entitlement_allowed
            if not entitlement_allowed(db,uid):return None
            row=db.execute("SELECT c.*,b.user_id AS billing_user,b.plan AS billing_plan,b.monthly_reviews AS billing_monthly_reviews FROM coverage c LEFT JOIN billing_state b ON b.user_id=c.user_id WHERE c.user_id=? AND (b.user_id IS NULL OR (b.status='active' AND b.expires>?))",(uid,time.time())).fetchone()
            from .billing_changes import capacity_snapshot
            period=db.execute('SELECT subscription,starts,ends FROM billing_periods WHERE user_id=?',(uid,)).fetchone()
            capacity=capacity_snapshot(db,uid,period['subscription'],period['starts'],period['ends']) if row and period else None
            from .launch_caps import effective_caps
            launch=effective_caps(db,uid,row,{'plan':row['billing_plan'],'monthly_reviews':row['billing_monthly_reviews']},include_showcase=include_showcase) if row and row['billing_user'] else None
        if not row:return None
        result=dict(row);billing_user=result.pop('billing_user');billing_plan=result.pop('billing_plan');result.pop('billing_monthly_reviews')
        if launch:result.update(review_daily=launch['review_daily'],user_monthly=launch['user_monthly'])
        result['uniqueClipsDaily']=(20 if billing_plan in ('starter','creator') else None) if billing_user else result['posts']
        if capacity:result['uniqueClipsDaily']=capacity['quantities']['uniqueClipsDaily']
        return result
    def set_coverage(self,uid,*,review_daily,user_monthly,scouts,favorites,categories,posts):
        # Internal provisioning only; never expose this as a client write endpoint.
        values=(review_daily,user_monthly,scouts,favorites,categories,posts)
        if any(type(x) is not int or x<0 for x in values):raise ValueError('Invalid coverage')
        with self.connection() as db:db.execute('INSERT OR REPLACE INTO coverage VALUES(?,?,?,?,?,?,?)',(uid,*values))
    def auth_rate(self,ip):
        now=time.time()
        with self.connection(atomic=True) as db:
            db.execute('DELETE FROM auth_attempts WHERE created<?',(now-900,))
            count=db.execute('SELECT COUNT(*) FROM auth_attempts WHERE ip=?',(ip,)).fetchone()[0]
            if count>=20:return False
            db.execute('INSERT INTO auth_attempts VALUES(?,?)',(ip,now));return True
    def workspace_feedback(self,uid):
        with self.connection() as db:
            candidates=[json.loads(row['data']) for row in db.execute('SELECT data FROM candidates WHERE user_id=? ORDER BY id LIMIT 200',(uid,))]
            reviews=[json.loads(row['data']) for row in db.execute('SELECT data FROM reviews WHERE user_id=? LIMIT 200',(uid,))]
            count=db.execute("SELECT COUNT(*) FROM reviews WHERE user_id=? AND json_valid(data) AND COALESCE(json_extract(data,'$.actor'),'human')='human'",(uid,)).fetchone()[0]
        return candidates,reviews,count
    def save_review(self,uid,candidate_id,decision,reasons,justification,local_learning=False):
        with self.connection(atomic=True) as db:
            candidate=db.execute('SELECT data FROM candidates WHERE id=? AND user_id=?',(candidate_id,uid)).fetchone()
            if not candidate:return False
            from .billing_modes import entitlement_allowed
            if not entitlement_allowed(db,uid):raise ValueError('An active subscription is required to review clips.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipeline_jobs'").fetchone():
                job=db.execute('SELECT stage FROM pipeline_jobs WHERE id=? AND user_id=?',(candidate_id,uid)).fetchone()
                if job and job['stage']=='editing':raise ValueError('Wait for clip edits to finish before making a decision.')
                db.execute("UPDATE pipeline_jobs SET stage=?,updated=? WHERE id=? AND user_id=? AND stage='review'",('rendering' if decision=='approve' else 'failed',time.time(),candidate_id,uid))
            value={'actor':'human','candidate':json.loads(candidate['data']),'user_feedback':{'decision':decision,'reasons':reasons,'justification':justification},'syncStatus':'local' if local_learning else 'server','reviewedAt':time.time()}
            db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?)',(uid,candidate_id,json.dumps(value)))
            if hasattr(self,'davey'):self.davey.evaluate(db,uid,candidate_id,decision)
            # Shared collection is paused until separate opt-in and quarantine exist.
            # Existing records are preserved; this decision is only account workflow audit.
        return True

    def development_user(self):
        # Dedicated local workspace; never grants paid coverage or admin access.
        email='clipbot-local-development@example.invalid'
        with self.connection(atomic=True) as db:
            row=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
            if row:return row['id']
            uid=secrets.token_hex(16)
            db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(uid,email,password_hash(secrets.token_urlsafe(48)),'Local Development',time.time()))
            return uid

    def save_report(self,uid,data):
        now=time.time()
        with self.connection(atomic=True) as db:
            if db.execute('SELECT COUNT(*) FROM reports WHERE user_id=? AND created>?',(uid,now-86400)).fetchone()[0]>=5:return None
            reference='CB-'+secrets.token_hex(8).upper()
            db.execute('INSERT INTO reports VALUES(?,?,?,?)',(reference,uid,now,json.dumps(data)))
        return reference
    def report_receipts(self,uid):
        with self.connection() as db:
            return [{'reference':row['id'],'created':row['created'],'status':'Received'} for row in db.execute('SELECT id,created FROM reports WHERE user_id=? ORDER BY created DESC LIMIT 20',(uid,))]

    def new_pairing(self,uid):
        code=secrets.token_urlsafe(24)
        with self.connection(atomic=True) as db:
            db.execute('DELETE FROM worker_pairing WHERE user_id=? OR expires<?',(uid,time.time()))
            db.execute('INSERT INTO worker_pairing VALUES(?,?,?)',(token_hash(code),uid,time.time()+600))
        return code
    def connect_worker(self,code):
        now=time.time()
        with self.connection(atomic=True) as db:
            row=db.execute('SELECT user_id FROM worker_pairing WHERE code=? AND expires>?',(token_hash(code),now)).fetchone()
            if not row:return None
            uid=row['user_id'];token=secrets.token_urlsafe(32)
            db.execute('DELETE FROM worker_pairing WHERE code=?',(token_hash(code),))
            db.execute('DELETE FROM worker_devices WHERE user_id=?',(uid,))
            db.execute('INSERT INTO worker_devices VALUES(?,?,?,?)',(token_hash(token),uid,now+2592000,0))
        return token
    def worker_heartbeat(self,token):
        now=time.time()
        with self.connection(atomic=True) as db:
            row=db.execute('SELECT user_id FROM worker_devices WHERE token=? AND expires>?',(token_hash(token),now)).fetchone()
            if not row:return False
            db.execute('UPDATE worker_devices SET last_seen=? WHERE token=?',(now,token_hash(token)))
        return True
    def worker_connected(self,uid):
        now=time.time()
        with self.connection() as db:return bool(db.execute('SELECT 1 FROM worker_devices WHERE user_id=? AND expires>? AND last_seen>?',(uid,now,now-90)).fetchone())
    def revoke_workers(self,uid):
        with self.connection(atomic=True) as db:
            db.execute('DELETE FROM worker_devices WHERE user_id=?',(uid,))
            db.execute('DELETE FROM worker_pairing WHERE user_id=?',(uid,))

    def billing_status(self,uid):
        with self.connection() as db:
            from .billing_modes import resource_mode
            if resource_mode(db,'state',uid)!=self.billing_mode:return None
            row=db.execute('SELECT plan,status,expires FROM billing_state WHERE user_id=?',(uid,)).fetchone()
        return dict(row) if row else None

    def beta_accepted(self,uid):
        with self.connection() as db:return bool(db.execute('SELECT 1 FROM beta_acceptance WHERE user_id=? AND version=?',(uid,'beta-feedback-v1')).fetchone())
    def accept_beta(self,uid):
        with self.connection() as db:db.execute('INSERT OR REPLACE INTO beta_acceptance VALUES(?,?,?)',(uid,'beta-feedback-v1',time.time()))
    def record_presence(self,session):
        with self.connection() as db:
            db.execute('DELETE FROM session_presence WHERE last_seen<?',(time.time()-120,))
            db.execute('INSERT OR REPLACE INTO session_presence VALUES(?,?)',(session['token'],time.time()))

    def update_profile(self,uid,username):
        username=normalize_username(username)
        with self.connection(atomic=True) as db:
            row=db.execute('SELECT u.id,p.username,p.username_changed_at FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?',(uid,)).fetchone()
            if not row:raise ValueError('Account not found.')
            if row['username'] and row['username'].lower()==username:return
            now=time.time();available_at=username_change_available_at(row['username_changed_at'])
            if available_at is not None and now<available_at:raise UsernameChangeUnavailable('You can change your username once every six calendar months. Next change: '+datetime.fromtimestamp(available_at,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')+'.')
            if not username_available(db,username,uid):raise sqlite3.IntegrityError('Username unavailable')
            db.execute('UPDATE users SET name=? WHERE id=?',(username,uid))
            db.execute("INSERT INTO user_profiles(user_id,username,username_changed_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,username_changed_at=excluded.username_changed_at",(uid,username,now))
    def update_avatar(self,uid,avatar):
        with self.connection(atomic=True) as db:
            db.execute("INSERT INTO user_profiles(user_id,avatar) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET avatar=excluded.avatar",(uid,avatar))
    def change_password(self,uid,session_token,current_password,new_password):
        # Validate and replace atomically, preventing concurrent old-password changes.
        with self.connection(atomic=True) as db:
            row=db.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()
            if not row or not db.execute('SELECT 1 FROM sessions WHERE token=? AND user_id=? AND expires>?',(session_token,uid,time.time())).fetchone():return False
            saved=row['password']
            if not hmac.compare_digest(password_hash(current_password,saved.split(':')[0]),saved):return False
            db.execute('UPDATE users SET password=? WHERE id=?',(password_hash(new_password),uid))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='password_resets'").fetchone():db.execute('DELETE FROM password_resets WHERE user_id=?',(uid,))
            db.execute('DELETE FROM session_presence WHERE token IN (SELECT token FROM sessions WHERE user_id=? AND token<>?)',(uid,session_token))
            db.execute('DELETE FROM sessions WHERE user_id=? AND token<>?',(uid,session_token))
            db.execute('DELETE FROM worker_devices WHERE user_id=?',(uid,))
            db.execute('DELETE FROM worker_pairing WHERE user_id=?',(uid,))
        return True
