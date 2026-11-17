"""Bounded anonymous page activity. No accounts, URLs, raw IPs or persistent browser IDs."""
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timezone, timedelta


class SiteVisitors:
    def __init__(self, store):
        self.store=store
        with store.connection(atomic=True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS site_visitor_config(id INTEGER PRIMARY KEY CHECK(id=1),secret TEXT NOT NULL,started REAL NOT NULL,launch REAL);
            CREATE TABLE IF NOT EXISTS site_visitor_pages(id TEXT PRIMARY KEY,last_seen REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS site_visitor_seen ON site_visitor_pages(last_seen);
            CREATE TABLE IF NOT EXISTS site_visitor_rates(ip TEXT,bucket INTEGER,kind TEXT,count INTEGER NOT NULL,PRIMARY KEY(ip,bucket,kind));
            CREATE TABLE IF NOT EXISTS site_visitor_hours(hour INTEGER PRIMARY KEY,visits INTEGER NOT NULL,peak INTEGER NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO site_visitor_config VALUES(1,?,?,NULL)',(secrets.token_hex(32),time.time()))
            self.secret=db.execute('SELECT secret FROM site_visitor_config WHERE id=1').fetchone()[0].encode()

    def digest(self,value):
        return hmac.new(self.secret,value.encode(),hashlib.sha256).hexdigest()

    def pulse(self,visit_id,ip,user_agent,*,now=None,privacy=False):
        if privacy or re.search(r'bot|crawler|spider|headless|slurp',str(user_agent)[:512],re.I):return False
        if not isinstance(visit_id,str) or not re.fullmatch(r'[a-f0-9]{32}',visit_id):raise ValueError('Invalid page identifier')
        if not isinstance(ip,str) or not 1<=len(ip)<=128:raise ValueError('Invalid client identity')
        now=time.time() if now is None else now
        hour=int(now//3600)*3600;minute=int(now//60)*60
        page=self.digest('page:'+visit_id);peer=self.digest('rate:'+str(int(now//86400))+':'+ip)
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM site_visitor_pages WHERE last_seen<?',(now-1800,))
            db.execute('DELETE FROM site_visitor_rates WHERE bucket<?',(hour-3600,))
            old=db.execute('SELECT last_seen FROM site_visitor_pages WHERE id=?',(page,)).fetchone()
            if old and old[0]>now-30:return False
            limits=[(minute,'pulse',120)]+([] if old else [(hour,'new',30)])
            for bucket,kind,limit in limits:
                row=db.execute('SELECT count FROM site_visitor_rates WHERE ip=? AND bucket=? AND kind=?',(peer,bucket,kind)).fetchone()
                if row and row[0]>=limit:return False
            if not old:
                total=db.execute('SELECT COALESCE(SUM(visits),0) FROM site_visitor_hours WHERE hour>=?',(int(now//86400)*86400,)).fetchone()[0]
                if total>=100000:return False
            for bucket,kind,_ in limits:
                db.execute('INSERT INTO site_visitor_rates VALUES(?,?,?,1) ON CONFLICT(ip,bucket,kind) DO UPDATE SET count=count+1',(peer,bucket,kind))
            db.execute('INSERT INTO site_visitor_pages VALUES(?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen',(page,now))
            active=db.execute('SELECT COUNT(*) FROM site_visitor_pages WHERE last_seen>?',(now-300,)).fetchone()[0]
            db.execute('INSERT INTO site_visitor_hours VALUES(?,?,?) ON CONFLICT(hour) DO UPDATE SET visits=visits+excluded.visits,peak=MAX(peak,excluded.peak)',(hour,0 if old else 1,active))
        return True

    @staticmethod
    def history(db,period,now):
        current=datetime.fromtimestamp(now,timezone.utc);today=current.replace(hour=0,minute=0,second=0,microsecond=0)
        if period=='all':
            earliest=db.execute('SELECT MIN(hour) FROM site_visitor_hours WHERE hour<=?',(now,)).fetchone()[0]
            first=datetime.fromtimestamp(earliest,timezone.utc).year if earliest is not None else current.year
            width=max(1,(current.year-first+32)//32);years=list(range(first,current.year+1,width))
            result=[{'key':str(y) if width==1 else f'{y}–{min(y+width-1,current.year)}','visits':0,'peakActive':0} for y in years]
            for year,count,peak in db.execute("SELECT strftime('%Y',hour,'unixepoch'),SUM(visits),MAX(peak) FROM site_visitor_hours WHERE hour<=? GROUP BY 1",(now,)):
                bucket=result[(int(year)-first)//width];bucket['visits']+=count;bucket['peakActive']=max(bucket['peakActive'],peak)
            return result
        if period=='year':
            month=current.year*12+current.month-1
            starts=[datetime((month-i)//12,(month-i)%12+1,1,tzinfo=timezone.utc) for i in range(11,-1,-1)]
            pattern='%Y-%m'
        else:
            count={'day':24,'week':7,'month':30}[period]
            start=today if period=='day' else today-timedelta(days=count-1)
            starts=[start+(timedelta(hours=i) if period=='day' else timedelta(days=i)) for i in range(count)]
            pattern='%Y-%m-%dT%H:00Z' if period=='day' else '%Y-%m-%d'
        rows={r[0]:(r[1],r[2]) for r in db.execute("SELECT strftime(?,hour,'unixepoch'),SUM(visits),MAX(peak) FROM site_visitor_hours WHERE hour>=? AND hour<=? GROUP BY 1",(pattern,starts[0].timestamp(),now))}
        return [{'key':value.strftime(pattern),'visits':rows.get(value.strftime(pattern),(0,0))[0],'peakActive':rows.get(value.strftime(pattern),(0,0))[1]} for value in starts]

    def snapshot(self,*,now=None):
        now=time.time() if now is None else now
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM site_visitor_pages WHERE last_seen<?',(now-1800,))
            db.execute('DELETE FROM site_visitor_rates WHERE bucket<?',(int(now//3600)*3600-3600,))
            if os.getenv('CLIPBOT_PUBLIC_SIGNUP')=='1':db.execute('UPDATE site_visitor_config SET launch=? WHERE id=1 AND launch IS NULL',(now,))
            config=db.execute('SELECT started,launch FROM site_visitor_config WHERE id=1').fetchone()
            active=db.execute('SELECT COUNT(*) FROM site_visitor_pages WHERE last_seen>? AND last_seen<=?',(now-300,now)).fetchone()[0]
            total=db.execute('SELECT COALESCE(SUM(visits),0) FROM site_visitor_hours WHERE hour<=?',(now,)).fetchone()[0]
            today=db.execute('SELECT COALESCE(SUM(visits),0) FROM site_visitor_hours WHERE hour>=? AND hour<=?',(int(now//86400)*86400,now)).fetchone()[0]
            history={period:self.history(db,period,now) for period in ('day','week','month','year','all')}
        return {'activeVisitors':active,'activeWindowSeconds':300,'visitsToday':today,'totalVisits':total,'observedAt':now,
                'collectionStartedAt':config[0],'launchStartedAt':config[1],'history':history,'timezone':'UTC',
                'source':'ClipBot anonymous visible-page heartbeats; guests, customers and owner included.',
                'meaning':'Page sessions, not identified people. Separate tabs and reloads can count separately. Known automated clients and privacy opt-outs are excluded; blockers and abuse limits can undercount. No history before collection began.'}
