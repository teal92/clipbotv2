"""Persisted provider modes and one shared entitlement boundary."""
import time

def resource_mode(db,resource,id):
    row=db.execute('SELECT mode FROM billing_modes WHERE resource=? AND id=?',(resource,id)).fetchone()
    return row['mode'] if row else 'test'  # Explicit migration rule for pre-mode records.

def bind_mode(db,resource,id,mode):
    db.execute('INSERT OR REPLACE INTO billing_modes VALUES(?,?,?)',(resource,id,mode))

def cancellation_revoked(db,uid):
    return bool(db.execute('SELECT 1 FROM billing_access_revocations r JOIN billing_state b ON b.user_id=r.user_id AND b.subscription=r.subscription JOIN runtime_billing_mode m ON m.mode=r.mode WHERE r.user_id=?',(uid,)).fetchone())

def entitlement_allowed(db,uid):
    from .owner_showcase import showcase_in
    if showcase_in(db,uid):return True
    mode=db.execute('SELECT mode FROM runtime_billing_mode').fetchone()['mode']
    state=db.execute('SELECT status,expires,subscription FROM billing_state WHERE user_id=?',(uid,)).fetchone()
    if not state:return mode=='test'  # Legacy manual allowances are never live entitlements.
    if cancellation_revoked(db,uid):return False
    return mode in ('test','live') and resource_mode(db,'state',uid)==mode and state['status']=='active' and state['expires']>time.time()
