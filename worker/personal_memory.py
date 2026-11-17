"""Account-bound local feedback, never model training or a global dataset."""
import hashlib,json,re,sqlite3,time,math
from contextlib import contextmanager
from pathlib import Path

REASONS=frozenset({'Strong hook','Funny','Great reaction','Good context','Good timing','Right audience','Other','Weak hook','Not funny','Needs context','Bad timing','Too long','Weak payoff','Wrong audience','Repetitive'})

class PersonalMemory:
    def __init__(self,root,origin,user_id):
        if not isinstance(user_id,str) or not re.fullmatch(r'[a-f0-9]{32}',user_id):raise ValueError('Invalid memory account.')
        scope=hashlib.sha256((origin+'\n'+user_id).encode()).hexdigest()
        directory=Path(root).resolve()/scope;directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/'personal.db'
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reviews(candidate_id TEXT PRIMARY KEY,decision TEXT NOT NULL,reasons TEXT NOT NULL,justification TEXT NOT NULL,confirmed INTEGER NOT NULL,updated REAL NOT NULL,schema_version INTEGER NOT NULL)')
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def record(self,candidate_id,decision,reasons,justification):
        if not isinstance(candidate_id,str) or not re.fullmatch(r'[a-f0-9]{32}',candidate_id) or decision not in ('approve','reject'):raise ValueError('Invalid local decision.')
        if not isinstance(reasons,list) or len(reasons)>10 or any(not isinstance(r,str) or r not in REASONS for r in reasons):raise ValueError('Invalid feedback reasons.')
        if not isinstance(justification,str) or len(justification)>1000:raise ValueError('Invalid feedback explanation.')
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,0,?,1)',(candidate_id,decision,json.dumps(sorted(set(reasons))),justification,time.time()))
            db.execute('DELETE FROM reviews WHERE candidate_id IN (SELECT candidate_id FROM reviews ORDER BY updated DESC,candidate_id DESC LIMIT -1 OFFSET 2000)')
    def confirm(self,reviews):
        with self.connection() as db:
            for item in reviews:
                if isinstance(item,dict):db.execute('UPDATE reviews SET confirmed=1 WHERE candidate_id=? AND decision=?',(item.get('candidateId'),item.get('decision')))
    def review(self,candidate_id):
        with self.connection() as db:row=db.execute('SELECT decision,reasons,justification,confirmed FROM reviews WHERE candidate_id=?',(candidate_id,)).fetchone()
        return {'decision':row['decision'],'reasons':json.loads(row['reasons']),'justification':row['justification'],'confirmed':bool(row['confirmed'])} if row else None
    def apply_reset(self,marker):
        if type(marker) not in (int,float) or not math.isfinite(marker) or marker<=0:return
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reset_state(id INTEGER PRIMARY KEY,marker REAL NOT NULL)')
            old=db.execute('SELECT marker FROM reset_state WHERE id=1').fetchone()
            if old and marker<=old[0]:return
            db.execute('DELETE FROM reviews')
            db.execute('INSERT OR REPLACE INTO reset_state VALUES(1,?)',(marker,))
    def summary(self):
        summary={'schemaVersion':1,'reviewCount':0,'approveReasons':{},'rejectReasons':{}}
        with self.connection() as db:rows=db.execute('SELECT decision,reasons FROM reviews WHERE confirmed=1 ORDER BY updated DESC,candidate_id DESC LIMIT 200').fetchall()
        for row in rows:
            summary['reviewCount']+=1;counts=summary[row['decision']+'Reasons']
            for reason in json.loads(row['reasons']):counts[reason]=counts.get(reason,0)+1
        return summary
