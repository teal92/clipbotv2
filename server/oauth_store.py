"""Encrypted, per-account OAuth records. Never expose this vault through an API."""
import hmac,json,os,secrets,time
from cryptography.fernet import Fernet,InvalidToken
from .store import token_hash

class OAuthInvalid(Exception):
    pass

class OAuthVault:
    def __init__(self,store):
        self.store=store;self.cipher=None
        key=os.getenv('CLIPBOT_TOKEN_ENCRYPTION_KEY','')
        if key:
            try:
                if key!=key.strip():raise ValueError()
                self.cipher=Fernet(key.encode())
            except (ValueError,TypeError):raise RuntimeError('Invalid account token encryption configuration') from None
        with store.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,user_id TEXT NOT NULL,session_token TEXT NOT NULL,platform TEXT NOT NULL,cookie TEXT NOT NULL,verifier TEXT NOT NULL,expires REAL NOT NULL,generation TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_accounts(user_id TEXT NOT NULL,platform TEXT NOT NULL,payload TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(user_id,platform));
            CREATE TABLE IF NOT EXISTS oauth_leases(user_id TEXT NOT NULL,platform TEXT NOT NULL,owner TEXT NOT NULL,expires REAL NOT NULL,PRIMARY KEY(user_id,platform));
            CREATE TABLE IF NOT EXISTS oauth_generations(user_id TEXT NOT NULL,platform TEXT NOT NULL,generation TEXT NOT NULL,PRIMARY KEY(user_id,platform));
            """)
    def encrypt(self,data):
        if not self.cipher:raise OAuthInvalid('Account token encryption is not configured.')
        return self.cipher.encrypt(json.dumps(data,separators=(',',':')).encode()).decode()
    def decrypt(self,value):
        if not self.cipher:raise OAuthInvalid('Account token encryption is not configured.')
        try:return json.loads(self.cipher.decrypt(value.encode()))
        except (InvalidToken,ValueError,TypeError):raise OAuthInvalid('Reconnect this account.') from None
    def begin(self,session,platform,verifier):
        state=secrets.token_urlsafe(32);cookie=secrets.token_urlsafe(32);generation=secrets.token_hex(16)
        protected=self.encrypt({'verifier':verifier})
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM sessions WHERE token=? AND user_id=? AND expires>?',(session['token'],session['user_id'],time.time())).fetchone():raise OAuthInvalid('Sign in again.')
            db.execute('DELETE FROM oauth_states WHERE expires<? OR (user_id=? AND platform=?)',(time.time(),session['user_id'],platform))
            db.execute('INSERT OR REPLACE INTO oauth_generations VALUES(?,?,?)',(session['user_id'],platform,generation))
            db.execute('INSERT INTO oauth_states VALUES(?,?,?,?,?,?,?,?)',(token_hash(state),session['user_id'],session['token'],platform,token_hash(cookie),protected,time.time()+600,generation))
        return state,cookie
    def consume(self,platform,state,cookie):
        if not state or not cookie or len(state)>200 or len(cookie)>200:raise OAuthInvalid('Start the connection again.')
        with self.store.connection(atomic=True) as db:
            row=db.execute('SELECT o.* FROM oauth_states o JOIN sessions s ON s.token=o.session_token AND s.user_id=o.user_id WHERE o.state=? AND o.platform=? AND o.expires>? AND s.expires>?',(token_hash(state),platform,time.time(),time.time())).fetchone()
            if not row or not hmac.compare_digest(row['cookie'],token_hash(cookie)):raise OAuthInvalid('Start the connection again.')
            db.execute('DELETE FROM oauth_states WHERE state=?',(token_hash(state),))
        result=dict(row);result['verifier']=self.decrypt(row['verifier'])['verifier'];return result
    def save(self,uid,platform,tokens,profile,flow=None,expected=None):
        payload=self.encrypt({'user_id':uid,'platform':platform,'tokens':tokens,'profile':profile})
        with self.store.connection(atomic=True) as db:
            if expected is not None:
                existing=db.execute('SELECT payload FROM oauth_accounts WHERE user_id=? AND platform=?',(uid,platform)).fetchone()
                if not existing or not hmac.compare_digest(existing['payload'],expected):raise OAuthInvalid('Connection changed. Reload and try again.')
            if flow:
                valid=db.execute('SELECT 1 FROM oauth_generations g JOIN sessions s ON s.token=? AND s.user_id=g.user_id WHERE g.user_id=? AND g.platform=? AND g.generation=? AND s.expires>?',(flow['session_token'],uid,platform,flow['generation'],time.time())).fetchone()
                if not valid:raise OAuthInvalid('Start the connection again.')
            db.execute('INSERT OR REPLACE INTO oauth_accounts VALUES(?,?,?,?)',(uid,platform,payload,time.time()))
    def load(self,uid,platform):
        with self.store.connection() as db:row=db.execute('SELECT payload FROM oauth_accounts WHERE user_id=? AND platform=?',(uid,platform)).fetchone()
        if not row:return None
        data=self.decrypt(row['payload'])
        if data.get('user_id')!=uid or data.get('platform')!=platform:raise OAuthInvalid('Reconnect this account.')
        data['_version']=row['payload'];return data
    def disconnect(self,uid,platform):
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM oauth_accounts WHERE user_id=? AND platform=?',(uid,platform))
            db.execute('DELETE FROM oauth_states WHERE user_id=? AND platform=?',(uid,platform))
            db.execute('INSERT OR REPLACE INTO oauth_generations VALUES(?,?,?)',(uid,platform,secrets.token_hex(16)))

    def claim(self,uid,platform):
        owner=secrets.token_hex(16)
        with self.store.connection(atomic=True) as db:
            db.execute('DELETE FROM oauth_leases WHERE expires<?',(time.time(),))
            if db.execute('SELECT 1 FROM oauth_leases WHERE user_id=? AND platform=?',(uid,platform)).fetchone():raise OAuthInvalid('This connection is being updated. Try again shortly.')
            db.execute('INSERT INTO oauth_leases VALUES(?,?,?,?)',(uid,platform,owner,time.time()+120))
        return owner
    def release(self,uid,platform,owner):
        with self.store.connection() as db:db.execute('DELETE FROM oauth_leases WHERE user_id=? AND platform=? AND owner=?',(uid,platform,owner))
