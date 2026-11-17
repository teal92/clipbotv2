from .client_ip import client_ip
"""One-time email recovery. Only token hashes persist; ownership is proven by redemption."""
import hashlib, re, secrets, time
from email.message import EmailMessage
from urllib.parse import urlsplit
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .store import password_hash,token_hash
from .password_policy import password_policy_errors,validate_new_password
from .report_delivery import mail_config,ReportDelivery
GENERIC={'ok':True,'message':'If an eligible account exists and delivery succeeds, a reset link will be emailed.'}
class RecoveryUnavailable(ValueError):
    status=409
class RecoveryEmail(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:str=Field(min_length=3,max_length=254)
class RecoveryPassword(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=40,max_length=100)
    newPassword:str=Field(min_length=12,max_length=128)
class AccountRecovery:
    def __init__(self,store,origin,config=None,transport=None):
        self.store=store;self.origin=origin.rstrip('/');self.config=mail_config() if config is None else config
        self.transport=transport or (lambda message:ReportDelivery._smtp(self,message))
        parsed=urlsplit(self.origin)
        self.valid_origin=bool(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and not parsed.path and (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')))
        with store.connection() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS password_resets(token TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS recovery_attempts(scope TEXT NOT NULL,created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS recovery_attempt_scope ON recovery_attempts(scope,created);
        CREATE TABLE IF NOT EXISTS email_verification(user_id TEXT PRIMARY KEY,verified REAL NOT NULL);
        ''')
    def allow(self,scope,limit,window=900):
        return self.allow_many([(scope,limit,window)])
    def allow_many(self,rules):
        now=time.time()
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM recovery_attempts WHERE created<?',(now-86400,))
            for scope,limit,window in rules:
                if db.execute('SELECT COUNT(*) FROM recovery_attempts WHERE scope=? AND created>?',(scope,now-window)).fetchone()[0]>=limit:return False
            db.executemany('INSERT INTO recovery_attempts VALUES(?,?)',[(scope,now) for scope,limit,window in rules])
        return True
    def request_reset(self,uid,ip='owner'):
        user=self.store.user(uid)
        valid=lambda value:bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',value)) and len(value)<=254
        if not user or not self.config.get('enabled') or not self.valid_origin or not valid(user['email']):raise RecoveryUnavailable('Secure password recovery email is unavailable. Configure the SMTP service and a valid stored customer email.')
        if not self.allow_many([('account:'+token_hash(uid),3,3600),('send-global',50,86400)]):raise RecoveryUnavailable('Password recovery request limit reached. Try again later.')
        token=secrets.token_urlsafe(32);hashed=token_hash(token)
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM password_resets WHERE expires<? OR user_id=?',(time.time(),uid))
            db.execute('INSERT INTO password_resets VALUES(?,?,?)',(hashed,uid,time.time()+900))
        message=EmailMessage();message['From']=self.config['sender'];message['To']=user['email'];message['Subject']='Reset your ClipBot password'
        message.set_content('A ClipBot password reset was requested for your account.\n\nOpen this link within 15 minutes:\n'+self.origin+'/reset-password.html#token='+token+'\n\nThis link works once. If you did not request it, ignore this email. Your password remains unchanged.\n')
        try:
            if self.transport(message):raise RuntimeError('Mail rejected')
        except Exception:
            with self.store.connection() as db:db.execute('DELETE FROM password_resets WHERE token=?',(hashed,))
            raise RecoveryUnavailable('Password recovery email could not be confirmed. Try again later.') from None
        return dict(GENERIC)
    def forgot(self,email,ip):
        if not self.allow_many([('forgot-ip:'+token_hash(ip),10,900),('forgot-email:'+token_hash(email),3,900),('forgot-global',100,900)]):return
        with self.store.connection() as db:row=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
        if row:
            try:self.request_reset(row['id'],ip)
            except RecoveryUnavailable:pass
    def redeem(self,token,new_password):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token) or password_policy_errors(new_password):return False
        # Hash outside the write lock; claim, replace, and revoke in one transaction.
        hashed_password=password_hash(new_password)
        with self.store.connection(atomic=True) as db:
            row=db.execute('SELECT user_id FROM password_resets WHERE token=? AND expires>?',(token_hash(token),time.time())).fetchone()
            if not row:return False
            uid=row['user_id']
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():return False
            db.execute('DELETE FROM password_resets WHERE user_id=?',(uid,))
            db.execute('UPDATE users SET password=? WHERE id=?',(hashed_password,uid))
            db.execute('DELETE FROM session_presence WHERE token IN (SELECT token FROM sessions WHERE user_id=?)',(uid,))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            db.execute('DELETE FROM worker_devices WHERE user_id=?',(uid,));db.execute('DELETE FROM worker_pairing WHERE user_id=?',(uid,))
            db.execute('INSERT OR REPLACE INTO email_verification VALUES(?,?)',(uid,time.time()))
        return True

def build_recovery_router(recovery):
    router=APIRouter()
    @router.post('/api/auth/forgot-password')
    def forgot(data:RecoveryEmail,request:Request,tasks:BackgroundTasks):
        # Identical status and response, including unavailable configuration and unknown users.
        email=data.email.strip().lower();ip=client_ip(request)
        tasks.add_task(recovery.forgot,email,ip);return dict(GENERIC)
    @router.post('/api/auth/reset-password')
    def reset(data:RecoveryPassword,request:Request):
        ip=client_ip(request)
        if not recovery.allow_many([('redeem-ip:'+token_hash(ip),10,900),('redeem-global',100,900)]):raise HTTPException(429,'Too many attempts. Try again later.')
        try:validate_new_password(data.newPassword)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if not recovery.redeem(data.token,data.newPassword):raise HTTPException(422,'Reset link is invalid or expired. Request a new link.')
        return {'ok':True,'message':'Password reset. Sign in with your new password. Other sessions and local workers were disconnected.'}
    return router
