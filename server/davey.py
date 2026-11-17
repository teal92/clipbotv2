"""Server-owned personal-consent and measured progression; never model training."""
import hashlib,json,os,time
from contextlib import nullcontext
from .claude_connection import MODEL
from .scouts import source_identity

POLICY_VERSION='davey-personal-v1'
DEFAULTS={'personalContext':False,'shadowEnabled':False,'automatic':False,'platforms':[],
          'dailyPostLimit':3,'minScore':90,'sources':[],'rightsAccepted':False}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def candidate_hash(candidate):
    return digest({key:candidate.get(key) for key in ('start','end','score','title','caption','rationale','safetyFlags')})


class DaveyStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS davey_settings(user_id TEXT PRIMARY KEY,data TEXT NOT NULL,revision INTEGER NOT NULL,updated REAL NOT NULL,context_revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS davey_predictions(user_id TEXT NOT NULL,job_id TEXT NOT NULL,context_key TEXT NOT NULL,candidate_hash TEXT NOT NULL,model TEXT NOT NULL,decision TEXT NOT NULL,safety_ok INTEGER NOT NULL,created REAL NOT NULL,human_decision TEXT,evaluated REAL,invalidated INTEGER NOT NULL DEFAULT 0,automated INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,job_id));
        CREATE INDEX IF NOT EXISTS davey_validation_context ON davey_predictions(user_id,context_key,evaluated);
        CREATE TABLE IF NOT EXISTS davey_incidents(user_id TEXT NOT NULL,job_id TEXT NOT NULL,kind TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,PRIMARY KEY(user_id,job_id,kind));
        CREATE TABLE IF NOT EXISTS davey_destination_consent(user_id TEXT NOT NULL,platform TEXT NOT NULL,destination TEXT NOT NULL,authorization_version TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(user_id,platform));
        CREATE TABLE IF NOT EXISTS davey_memory_resets(user_id TEXT PRIMARY KEY,created REAL NOT NULL);
        ''')
        with store.connection() as db:
            if 'context_revision' not in {row[1] for row in db.execute('PRAGMA table_info(davey_settings)')}:
                db.execute('ALTER TABLE davey_settings ADD COLUMN context_revision INTEGER NOT NULL DEFAULT 0')
        store.davey=self

    @staticmethod
    def _settings(db,uid):
        row=db.execute('SELECT data,revision FROM davey_settings WHERE user_id=?',(uid,)).fetchone()
        if row:
            try:
                value=json.loads(row['data'])
                if set(value)==set(DEFAULTS):return value,row['revision']
            except (ValueError,TypeError):pass
        return json.loads(json.dumps(DEFAULTS)),0

    def settings(self,uid):
        with self.store.connection() as db:return self._settings(db,uid)[0]

    @staticmethod
    def _manual_count(db,uid):
        return db.execute("SELECT COUNT(*) FROM reviews WHERE user_id=? AND json_valid(data) AND COALESCE(json_extract(data,'$.actor'),'human')='human' AND json_extract(data,'$.user_feedback.decision') IN ('approve','reject')",(uid,)).fetchone()[0]

    def _context_key(self,db,uid,settings):
        row=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
        try:prefs=json.loads(row['data']) if row else {}
        except (ValueError,TypeError):prefs={}
        generation=db.execute('SELECT context_revision FROM davey_settings WHERE user_id=?',(uid,)).fetchone()
        return digest({'policy':POLICY_VERSION,'model':MODEL,'generation':generation[0] if generation else 0,'focus':prefs.get('focus','balanced'),
            'avoid':prefs.get('avoid','personal'),'personalContext':settings['personalContext'],
            'minScore':settings['minScore'],'sources':settings['sources']})

    def context_key(self,uid):
        with self.store.connection() as db:return self._context_key(db,uid,self._settings(db,uid)[0])

    def preference_changed(self,db,uid):
        settings,revision=self._settings(db,uid)
        row=db.execute('SELECT context_revision FROM davey_settings WHERE user_id=?',(uid,)).fetchone()
        settings={**settings,'automatic':False}
        db.execute('INSERT OR REPLACE INTO davey_settings(user_id,data,revision,updated,context_revision) VALUES(?,?,?,?,?)',(uid,json.dumps(settings),revision+1,time.time(),(row[0] if row else 0)+1))

    def _status(self,db,uid,settings,revision):
        count=self._manual_count(db,uid);key=self._context_key(db,uid,settings)
        rows=db.execute("SELECT decision,human_decision FROM davey_predictions WHERE user_id=? AND context_key=? AND model=? AND invalidated=0 AND automated=0 AND human_decision IN ('approve','reject') ORDER BY evaluated DESC,job_id DESC LIMIT 200",(uid,key,MODEL)).fetchall()
        total=len(rows);positive=sum(row['decision']=='approve' for row in rows)
        matches=sum(row['decision']==row['human_decision'] for row in rows)
        correct_positive=sum(row['decision']==row['human_decision']=='approve' for row in rows)
        incidents=db.execute('SELECT COUNT(*) FROM davey_incidents WHERE user_id=? AND resolved=0',(uid,)).fetchone()[0]
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='publications'").fetchone():
            incidents+=db.execute("SELECT COUNT(*) FROM publications WHERE user_id=? AND status='unknown'",(uid,)).fetchone()[0]
        qualified=bool(count>=100 and settings['personalContext'] and settings['shadowEnabled'] and
            total>=25 and matches*100>=90*total and positive>=20 and correct_positive*100>=95*positive and not incidents)
        phase=4 if qualified else 3 if count>=100 else 2 if count else 1
        reset=db.execute('SELECT created FROM davey_memory_resets WHERE user_id=?',(uid,)).fetchone()
        destinations=[]
        pub=getattr(self.store,'davey_publications',None)
        if pub:
            for platform in ('instagram','facebook'):
                connected=pub.oauth.status(uid,platform)
                if connected.get('connected') and not connected.get('destinationRequired'):destinations.append({'platform':platform,'name':connected.get('accountName','Selected account')})
        return {'phase':phase,'qualified':qualified,'manualDecisions':count,'revision':revision,'contextKey':key,
            'memoryResetAt':reset[0] if reset else 0,'availableDestinations':destinations,
            'personalContext':settings['personalContext'],'shadowEnabled':settings['shadowEnabled'],
            'automaticRequested':settings['automatic'],'automaticEnabled':bool(qualified and settings['automatic'] and os.getenv('CLIPBOT_AUTONOMY_ENABLED')=='1'),
            'releaseAvailable':os.getenv('CLIPBOT_AUTONOMY_ENABLED')=='1','unresolvedIncidents':incidents,
            'validation':{'decisions':total,'agreement':round(matches*100/total,1) if total else 0,
                'predictedApprovals':positive,'approvalPrecision':round(correct_positive*100/positive,1) if positive else 0},
            'settings':settings,'policyVersion':POLICY_VERSION,'model':MODEL}

    def status(self,uid):
        with self.store.connection() as db:
            settings,revision=self._settings(db,uid)
            return self._status(db,uid,settings,revision)

    def reset(self,uid,revision):
        with self.store.connection(atomic=True) as db:
            if self._settings(db,uid)[1]!=revision:raise ValueError('Davey settings changed. Refresh before resetting.')
            self.preference_changed(db,uid)
            db.execute('UPDATE davey_settings SET data=? WHERE user_id=?',(json.dumps(DEFAULTS),uid))
            db.execute('DELETE FROM davey_destination_consent WHERE user_id=?',(uid,))
            db.execute('INSERT OR REPLACE INTO davey_memory_resets VALUES(?,?)',(uid,time.time()))
        return self.status(uid)

    def save(self,uid,values,expected_revision=None,db=None):
        if not isinstance(values,dict) or set(values)!=set(DEFAULTS):raise ValueError('Choose the listed Davey settings.')
        for key in ('personalContext','shadowEnabled','automatic','rightsAccepted'):
            if type(values[key]) is not bool:raise ValueError('Choose the listed Davey settings.')
        for key,low,high in [('dailyPostLimit',1,100),('minScore',75,100)]:
            if type(values[key]) is not int or not low<=values[key]<=high:raise ValueError('Choose bounded Davey limits.')
        platforms=values['platforms'];sources=values['sources']
        if not isinstance(platforms,list) or len(platforms)>2 or any(p not in ('instagram','facebook') for p in platforms) or len(set(platforms))!=len(platforms):raise ValueError('Choose supported automatic-post destinations.')
        if not isinstance(sources,list) or len(sources)>40:raise ValueError('Choose up to 40 approved stream sources.')
        normalized=[source_identity(source) for source in sources]
        if len({(s['platform'],s['login']) for s in normalized})!=len(normalized):raise ValueError('Choose distinct stream sources.')
        values={**values,'platforms':sorted(platforms),'sources':sorted(normalized,key=lambda s:(s['platform'],s['login']))}
        with (self.store.connection(atomic=True) if db is None else nullcontext(db)) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ValueError('Davey account unavailable.')
            old,revision=self._settings(db,uid)
            if expected_revision is not None and (type(expected_revision) is not int or expected_revision!=revision):raise ValueError('Davey settings changed. Refresh before saving.')
            if old['personalContext'] and not values['personalContext']:
                values={**values,'shadowEnabled':False,'automatic':False}
            elif old['shadowEnabled'] and not values['shadowEnabled']:
                values={**values,'automatic':False}
            if values['shadowEnabled'] and (not values['personalContext'] or self._manual_count(db,uid)<100):raise ValueError('Personal context and 100 manual decisions are required for validation.')
            if values['automatic']:
                status=self._status(db,uid,values,revision)
                if not status['qualified'] or not values['rightsAccepted'] or not platforms or not normalized:raise ValueError('Complete validation and choose approved sources and destinations before enabling automatic posting.')
                if os.getenv('CLIPBOT_AUTONOMY_ENABLED')!='1':raise ValueError('Automatic posting has not been released yet.')
            if values==old:return self._status(db,uid,old,revision)
            destinations=[]
            if values['automatic']:
                pub=getattr(self.store,'davey_publications',None)
                if pub is None:raise ValueError('Automatic publishing is unavailable.')
                from .publication import PublicationDenied
                try:
                    for platform in values['platforms']:
                        _,destination,version=pub.credentials(uid,platform)
                        destinations.append((uid,platform,destination,version,revision+1))
                except PublicationDenied:raise ValueError('Connect and select each approved publishing account first.') from None
            generation=db.execute('SELECT context_revision FROM davey_settings WHERE user_id=?',(uid,)).fetchone()
            changed=any(values[key]!=old[key] for key in ('personalContext','minScore','sources'))
            db.execute('INSERT OR REPLACE INTO davey_settings(user_id,data,revision,updated,context_revision) VALUES(?,?,?,?,?)',(uid,json.dumps(values),revision+1,time.time(),(generation[0] if generation else 0)+int(changed)))
            db.execute('DELETE FROM davey_destination_consent WHERE user_id=?',(uid,))
            db.executemany('INSERT INTO davey_destination_consent VALUES(?,?,?,?,?)',destinations)
            return self._status(db,uid,values,revision+1)

    def prediction(self,uid,job,candidate,context_key):
        with self.store.connection(atomic=True) as db:
            settings,_=self._settings(db,uid)
            if not settings['personalContext'] or not settings['shadowEnabled'] or self._manual_count(db,uid)<100 or context_key!=self._context_key(db,uid,settings):return False
            row=db.execute('SELECT data FROM candidates WHERE user_id=? AND id=?',(uid,job)).fetchone()
            if not row or candidate_hash(json.loads(row['data']))!=candidate_hash(candidate):return False
            if db.execute('SELECT 1 FROM reviews WHERE user_id=? AND candidate_id=?',(uid,job)).fetchone():return False
            safe=candidate.get('safetyFlags')==[]
            if type(candidate.get('score')) is not int:return False
            decision=('approve' if candidate['score']>=settings['minScore'] else 'reject') if safe else 'hold'
            return bool(db.execute('INSERT OR IGNORE INTO davey_predictions(user_id,job_id,context_key,candidate_hash,model,decision,safety_ok,created) VALUES(?,?,?,?,?,?,?,?)',(uid,job,context_key,candidate_hash(candidate),MODEL,decision,int(safe),time.time())).rowcount)

    def evaluate(self,db,uid,job,decision):
        row=db.execute('SELECT * FROM davey_predictions WHERE user_id=? AND job_id=?',(uid,job)).fetchone()
        if not row or row['human_decision'] is not None or row['automated'] or row['invalidated'] or row['decision']=='hold':return False
        review=db.execute('SELECT data FROM reviews WHERE user_id=? AND candidate_id=?',(uid,job)).fetchone()
        candidate=db.execute('SELECT data FROM candidates WHERE user_id=? AND id=?',(uid,job)).fetchone()
        if not review or not candidate:return False
        data=json.loads(review['data'])
        if data.get('actor','human')!='human' or decision not in ('approve','reject') or data.get('user_feedback',{}).get('decision')!=decision:return False
        if candidate_hash(json.loads(candidate['data']))!=row['candidate_hash']:
            db.execute('UPDATE davey_predictions SET invalidated=1 WHERE user_id=? AND job_id=?',(uid,job));return False
        return bool(db.execute('UPDATE davey_predictions SET human_decision=?,evaluated=? WHERE user_id=? AND job_id=? AND human_decision IS NULL',(decision,time.time(),uid,job)).rowcount)
