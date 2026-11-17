from .mail_budget import reserve_mail,MailLimitReached
"""Bounded text-only support outbox. No attachment, recipient, or retry controls from clients."""
import hashlib
import json
import os
import re
import secrets
import smtplib
import ssl
import threading
import time
import unicodedata
from email.message import EmailMessage


class ReportRejected(ValueError):
    def __init__(self,message,status=422):
        super().__init__(message);self.status=status


def mail_config():
    config={key:os.getenv(env,'').strip() for key,env in {
        'recipient':'CLIPBOT_REPORT_EMAIL','sender':'CLIPBOT_REPORT_FROM',
        'host':'CLIPBOT_REPORT_SMTP_HOST','username':'CLIPBOT_REPORT_SMTP_USERNAME',
        'password':'CLIPBOT_REPORT_SMTP_PASSWORD'}.items()}
    # Owner-confirmed official inbox; never accepted from submitted report fields.
    config['recipient']=config['recipient'] or 'support@your-domain.example'
    config['enabled']=False
    try:config['port']=int(os.getenv('CLIPBOT_REPORT_SMTP_PORT','465'))
    except ValueError:return config
    # TLS is mandatory, with verified certificates. Ports are deliberately bounded.
    valid=lambda value:bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',value)) and len(value)<=254
    config['enabled']=bool(all(config[k] for k in ('host','username','password')) and valid(config['recipient']) and valid(config['sender']) and config['port'] in (465,587) and not re.search(r'[\s/\\]',config['host']))
    return config


def clean_report(data):
    limits={'kind':20,'area':30,'title':120,'details':4000,'steps':2000,'expected':1000,'frequency':20,'impact':20,'environment':300}
    if set(data)!=set(limits):raise ReportRejected('Choose the listed report fields.')
    clean={}
    for key,limit in limits.items():
        value=data[key]
        if not isinstance(value,str) or len(value)>limit or any(unicodedata.category(ch).startswith('C') and ch not in '\n\r\t' for ch in value):
            raise ReportRejected('Use plain text within the report limits.')
        clean[key]=value.replace('\r\n','\n').replace('\r','\n').strip()
    if clean['kind'] not in ('bug','suggestion','feedback') or clean['area'] not in ('Dashboard','Streamers','Clips','Processing','Publishing','Davey','Logs','Usage','Settings','Account','Other') or clean['frequency'] not in ('once','sometimes','always','unsure') or clean['impact'] not in ('minor','disruptive','blocked'):
        raise ReportRejected('Choose the listed report options.')
    if len(clean['title'])<5 or len(clean['details'])<20 or (clean['kind']=='bug' and (len(clean['steps'])<10 or len(clean['expected'])<10)):
        raise ReportRejected('Include a detailed description. Bug reports also need steps and the expected result.')
    return clean


class ReportDelivery:
    def __init__(self,store,config=None,transport=None):
        self.store=store;self.config=mail_config() if config is None else config
        self.transport=transport or self._smtp;self.stop_event=threading.Event();self.thread=None
        with store.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS report_delivery(reference TEXT PRIMARY KEY,user_id TEXT NOT NULL,ip_hash TEXT NOT NULL,fingerprint TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL,attempted REAL);
            CREATE INDEX IF NOT EXISTS report_delivery_created ON report_delivery(created);
            CREATE INDEX IF NOT EXISTS report_delivery_user ON report_delivery(user_id,created);
            CREATE INDEX IF NOT EXISTS report_delivery_ip ON report_delivery(ip_hash,created);
            ''')

    def submit(self,uid,ip,data):
        data=clean_report(data);now=time.time()
        payload=json.dumps(data,sort_keys=True,ensure_ascii=True)
        fingerprint=hashlib.sha256(payload.encode()).hexdigest()
        ip_hash=hashlib.sha256(str(ip or 'unknown').encode()).hexdigest()
        with self.store.connection(atomic=True) as db:
            # Keep the anti-abuse ledger bounded; report contents retain existing policy.
            db.execute("DELETE FROM report_delivery WHERE created<? AND status!='Queued'",(now-30*86400,))
            duplicate=db.execute('SELECT reference,status FROM report_delivery WHERE user_id=? AND fingerprint=? AND created>? ORDER BY created DESC LIMIT 1',(uid,fingerprint,now-86400)).fetchone()
            if duplicate:return {**dict(duplicate),'deliveryRequired':duplicate['status']=='Received'}
            counts=(db.execute('SELECT COUNT(*) FROM reports WHERE user_id=? AND created>?',(uid,now-86400)).fetchone()[0],db.execute('SELECT COUNT(*) FROM report_delivery WHERE ip_hash=? AND created>?',(ip_hash,now-86400)).fetchone()[0],db.execute('SELECT COUNT(*) FROM report_delivery WHERE created>?',(now-86400,)).fetchone()[0],db.execute("SELECT COUNT(*) FROM report_delivery WHERE status='Queued'").fetchone()[0])
            if any(count>=limit for count,limit in zip(counts,(5,10,100,100))):
                raise ReportRejected('Report limit reached. Please try again later.',429)
            reference='CB-'+secrets.token_hex(8).upper()
            status='Queued' if self.config.get('enabled') else 'Received'
            db.execute('INSERT INTO reports VALUES(?,?,?,?)',(reference,uid,now,payload))
            db.execute('INSERT INTO report_delivery VALUES(?,?,?,?,?,?,NULL)',(reference,uid,ip_hash,fingerprint,now,status))
        return {'reference':reference,'status':status,'deliveryRequired':status=='Received'}

    def receipts(self,uid):
        with self.store.connection() as db:
            return [dict(row) for row in db.execute("SELECT r.id AS reference,r.created,COALESCE(d.status,'Received') AS status FROM reports r LEFT JOIN report_delivery d ON d.reference=r.id WHERE r.user_id=? ORDER BY r.created DESC LIMIT 20",(uid,))]

    def deliver_one(self):
        if not self.config.get('enabled'):return False
        now=time.time()
        with self.store.connection(atomic=True) as db:
            # Claim before network I/O. A crash or timeout must never cause a resend.
            if db.execute('SELECT COUNT(*) FROM report_delivery WHERE attempted>?',(now-86400,)).fetchone()[0]>=50:return False
            if db.execute('SELECT COUNT(*) FROM report_delivery WHERE attempted>?',(now-60,)).fetchone()[0]:return False
            row=db.execute("SELECT r.id,r.user_id,r.data FROM reports r JOIN report_delivery d ON d.reference=r.id WHERE d.status='Queued' ORDER BY d.created LIMIT 1").fetchone()
            if not row:return False
            db.execute("UPDATE report_delivery SET status='Delivery unknown',attempted=? WHERE reference=?",(now,row['id']))
        message=EmailMessage()
        message['From']=self.config['sender'];message['To']=self.config['recipient']
        message['Subject']='ClipBot support report '+row['id']
        message['Message-ID']='<'+row['id']+'@clipbot-report.local>'
        data=json.loads(row['data'])
        # Submitted text stays in the body, never in headers or HTML. No files included.
        message.set_content('Reference: '+row['id']+'\nAccount ID: '+row['user_id']+'\n\n'+'\n\n'.join(key+':\n'+value for key,value in data.items()))
        try:
            refused=self.transport(message)
            status='Mail server rejected' if refused else 'Accepted by mail server'
        except MailLimitReached:
            status='Email limit reached'
        except Exception:
            status='Delivery unknown'
        with self.store.connection(atomic=True) as db:db.execute('UPDATE report_delivery SET status=? WHERE reference=?',(status,row['id']))
        return True

    def _smtp(self,message):
        reserve_mail(self.store)
        cfg=self.config;context=ssl.create_default_context()
        if cfg['port']==465:
            with smtplib.SMTP_SSL(cfg['host'],cfg['port'],timeout=15,context=context) as smtp:
                smtp.login(cfg['username'],cfg['password']);return smtp.send_message(message)
        with smtplib.SMTP(cfg['host'],cfg['port'],timeout=15) as smtp:
            smtp.ehlo();smtp.starttls(context=context);smtp.ehlo()
            smtp.login(cfg['username'],cfg['password']);return smtp.send_message(message)

    def start(self):
        if not self.config.get('enabled') or self.thread is not None:return
        def run():
            while not self.stop_event.is_set():
                try:self.deliver_one()
                except Exception:pass  # Persistent claim protects against duplicate delivery.
                self.stop_event.wait(60)
        self.thread=threading.Thread(target=run,name='support-report-outbox',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
