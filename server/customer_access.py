from .client_ip import client_ip
"""Stored-email ownership and current-policy gates; no browser-controlled bypass."""
import hmac
import os
import re
import secrets
import time
from email.message import EmailMessage
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .legal import POLICY_VERSION
from .report_delivery import mail_config, ReportDelivery
from .store import token_hash

GENERIC = {'ok': True, 'message': 'If delivery is available, a verification link will be sent to your account email.'}
INVALID = 'Verification link is invalid or expired. Request a new link from your account.'


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class VerificationClaim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=40, max_length=100)


class PolicyAcceptance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(min_length=1, max_length=50)


def secure_origin(origin):
    try:
        parsed = urlsplit(origin)
        return bool(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
                    and not parsed.path and not parsed.query and not parsed.fragment and parsed.port in (None, 443)
                    and not re.search(r'[\s\\]', origin))
    except ValueError:
        return False


class CustomerAccess:
    def __init__(self, store, origin, config=None, transport=None, *, enforce=None, owner_uid=None, edge_verified=None, public_signup=None):
        self.store = store
        self.origin = origin.rstrip('/')
        self.config = mail_config() if config is None else config
        self.transport = transport or (lambda message: ReportDelivery._smtp(self, message))
        self.public_signup = os.getenv('CLIPBOT_PUBLIC_SIGNUP') == '1' if public_signup is None else bool(public_signup)
        invited = os.getenv('CLIPBOT_SIGNUP_EMAIL_HASHES')
        # Presence restricts registration even if public signup is enabled. Invalid
        # configuration denies everyone; remove the setting for normal public launch.
        self.signup_hashes = None
        if invited is not None:
            values = invited.split(',') if len(invited) <= 1299 else []
            self.signup_hashes = frozenset(values) if 1 <= len(values) <= 20 and all(re.fullmatch(r'[a-f0-9]{64}', value) for value in values) else frozenset()
        # Public registration always requires verified ownership/current policies.
        self.enforce = self.public_signup or self.signup_hashes is not None or (os.getenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS') == '1' if enforce is None else bool(enforce))
        self.owner_uid = os.getenv('CLIPBOT_ADMIN_USER_ID', '').strip() if owner_uid is None else owner_uid
        self.edge_verified = os.getenv('CLIPBOT_EDGE_VERIFIED') == '1' if edge_verified is None else bool(edge_verified)
        with store.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS email_verification(user_id TEXT PRIMARY KEY,verified REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS email_verification_tokens(token TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,email_hash TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS customer_access_attempts(scope TEXT NOT NULL,created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS customer_access_attempt_scope ON customer_access_attempts(scope,created);
            ''')

    @property
    def signup_enabled(self):
        return self.public_signup or self.signup_hashes is not None

    def signup_allowed(self, email):
        if self.signup_hashes is None:
            return self.public_signup
        return token_hash(email.strip().lower()) in self.signup_hashes

    @property
    def mail_ready(self):
        valid = lambda value: isinstance(value, str) and len(value) <= 254 and bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', value))
        return bool(self.config.get('enabled') and valid(self.config.get('sender')) and secure_origin(self.origin))

    def public_signup_ready(self):
        # Deployment may only set edge_verified after checking the actual ingress.
        return bool(self.mail_ready and self.edge_verified)

    def admit(self, rules):
        """Check all applicable limits and charge all or none in one write lock."""
        now = time.time()
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM customer_access_attempts WHERE created<?', (now - 86400,))
            for scope, limit, window in rules:
                count = db.execute('SELECT COUNT(*) FROM customer_access_attempts WHERE scope=? AND created>?', (scope, now-window)).fetchone()[0]
                if count >= limit:
                    return False
            db.executemany('INSERT INTO customer_access_attempts VALUES(?,?)', [(scope, now) for scope, _, _ in rules])
        return True

    def request_verification(self, uid, ip):
        # Only the authenticated account's stored email can be a destination.
        user = self.store.user(uid)
        if not user or not self.mail_ready:
            return dict(GENERIC)
        email = user['email']
        if len(email) > 254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', email):
            return dict(GENERIC)
        if not self.admit([('send-ip:' + token_hash(str(ip)), 10, 3600), ('send-account:' + token_hash(uid), 3, 3600), ('send-global', 50, 86400)]):
            return dict(GENERIC)
        token = secrets.token_urlsafe(32)
        hashed = token_hash('email-verification:' + token)
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM email_verification_tokens WHERE user_id=? OR expires<?', (uid, time.time()))
            db.execute('INSERT INTO email_verification_tokens VALUES(?,?,?,?)', (hashed, uid, token_hash(email), time.time()+900))
        message = EmailMessage()
        message['From'] = self.config['sender']
        message['To'] = email
        message['Subject'] = 'Verify your ClipBot email'
        message.set_content('Verify the email address on your ClipBot account. Sign in to the same account, then open this link within 15 minutes:\n\n'
                            + self.origin + '/verify-email.html#token=' + token
                            + '\n\nThis link works once and cannot reset your password. If you did not request it, ignore this email.\n')
        try:
            if self.transport(message):
                raise RuntimeError('Mail rejected')
        except Exception:
            with self.store.connection() as db:
                db.execute('DELETE FROM email_verification_tokens WHERE token=?', (hashed,))
        return dict(GENERIC)

    def confirm(self, uid, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return False
        with self.store.connection(atomic=True) as db:
            row = db.execute('SELECT t.email_hash,u.email FROM email_verification_tokens t JOIN users u ON u.id=t.user_id WHERE t.token=? AND t.user_id=? AND t.expires>?',
                             (token_hash('email-verification:' + token), uid, time.time())).fetchone()
            if not row or not hmac.compare_digest(row['email_hash'], token_hash(row['email'])):
                return False
            db.execute('DELETE FROM email_verification_tokens WHERE user_id=?', (uid,))
            db.execute('INSERT OR REPLACE INTO email_verification VALUES(?,?)', (uid, time.time()))
        return True

    def accept_policy(self, uid, version):
        if version != POLICY_VERSION:
            raise HTTPException(422, 'Read and accept the current Terms and acknowledge the Privacy Policy.')
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
                raise HTTPException(401, 'Sign in to continue.')
            db.execute('INSERT OR IGNORE INTO legal_acceptances VALUES(?,?,?)', (uid, POLICY_VERSION, time.time()))

    def readiness(self, uid):
        with self.store.connection() as db:
            verified = bool(db.execute('SELECT 1 FROM email_verification WHERE user_id=?', (uid,)).fetchone())
            accepted = bool(db.execute('SELECT 1 FROM legal_acceptances WHERE user_id=? AND version=?', (uid, POLICY_VERSION)).fetchone())
        return {'emailVerified': verified, 'policyAccepted': accepted, 'policyVersion': POLICY_VERSION,
                'enforced': bool(self.enforce or self.public_signup), 'ready': verified and accepted,
                'emailDeliveryAvailable': self.mail_ready}

    def require_ready(self, uid):
        if not (self.enforce or self.public_signup):
            return
        # Explicit configured owner account keeps prelaunch diagnostic access.
        user = self.store.user(uid)
        if self.owner_uid and user and user['email'] != 'clipbot-local-development@example.invalid' and hmac.compare_digest(uid, self.owner_uid):
            return
        if not self.readiness(uid)['ready']:
            raise HTTPException(428, 'Verify your account email and accept the current policies in Account before starting paid operations.')


def build_customer_access_router(access, current):
    router = APIRouter()

    @router.get('/api/account/readiness')
    def readiness(request: Request):
        return access.readiness(current(request)['user_id'])

    @router.post('/api/account/request-verification')
    def request_verification(data: EmptyRequest, request: Request):
        uid = current(request, True)['user_id']
        return access.request_verification(uid, client_ip(request))

    @router.post('/api/account/verify-email')
    def verify(data: VerificationClaim, request: Request):
        uid = current(request, True)['user_id']
        ip = client_ip(request)
        if not access.admit([('verify-ip:'+token_hash(ip), 10, 900), ('verify-account:'+token_hash(uid), 10, 900), ('verify-global', 100, 900)]):
            raise HTTPException(429, 'Too many attempts. Try again later.')
        if not access.confirm(uid, data.token):
            raise HTTPException(422, INVALID)
        return {'ok': True, **access.readiness(uid)}

    @router.post('/api/account/accept-policy')
    def accept(data: PolicyAcceptance, request: Request):
        uid = current(request, True)['user_id']
        ip = client_ip(request)
        if not access.admit([('policy-account:'+token_hash(uid), 20, 900), ('policy-ip:'+token_hash(ip), 40, 900), ('policy-global', 200, 900)]):
            raise HTTPException(429, 'Too many attempts. Try again later.')
        access.accept_policy(uid, data.version)
        return {'ok': True, **access.readiness(uid)}

    return router


def require_customer_ready(store, uid, *, db=None):
    """Cheap service/device boundary gate; never initializes schema under a write lock."""
    if os.getenv('CLIPBOT_PUBLIC_SIGNUP')!='1' and os.getenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS')!='1' and os.getenv('CLIPBOT_SIGNUP_EMAIL_HASHES') is None:return
    owner=os.getenv('CLIPBOT_ADMIN_USER_ID','').strip()
    def check(connection):
        user=connection.execute('SELECT email FROM users WHERE id=?',(uid,)).fetchone()
        if owner and user and user['email']!='clipbot-local-development@example.invalid' and hmac.compare_digest(uid,owner):return
        import sqlite3
        try:
            verified=connection.execute('SELECT 1 FROM email_verification WHERE user_id=?',(uid,)).fetchone()
            accepted=connection.execute('SELECT 1 FROM legal_acceptances WHERE user_id=? AND version=?',(uid,POLICY_VERSION)).fetchone()
        except sqlite3.OperationalError:verified=accepted=None
        if not user or not verified or not accepted:
            raise HTTPException(428,'Verify your account email and accept the current policies in Account before starting paid operations.')
    if db is not None:check(db)
    else:
        with store.connection() as connection:check(connection)
