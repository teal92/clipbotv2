"""Owned capacity snapshots; shared Stripe price buckets never define user limits."""
import json,re
from .pricing import quote
CUSTOM_AMOUNTS=tuple(range(1000,8501,500))
def catalog(value):
    try:
        result=json.loads(value)
        if not isinstance(result,dict) or set(result)!={str(x) for x in CUSTOM_AMOUNTS}:return {}
        if len(set(result.values()))!=16 or any(not isinstance(x,str) or not re.fullmatch(r'price_[A-Za-z0-9_]+',x) for x in result.values()):return {}
        return result
    except (ValueError,TypeError):return {}
def schema(db):db.execute('CREATE TABLE IF NOT EXISTS billing_custom_capacity(resource TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(resource,id))')
def config(db,resource,id):
    row=db.execute('SELECT data FROM billing_custom_capacity WHERE resource=? AND id=?',(resource,id)).fetchone()
    if not row:return None
    try:
        value=json.loads(row['data']);quote('custom',value);return value
    except (ValueError,TypeError):return None
def bind(db,resource,id,value):
    if value is None:db.execute('DELETE FROM billing_custom_capacity WHERE resource=? AND id=?',(resource,id))
    else:
        quote('custom',value)
        db.execute('INSERT OR REPLACE INTO billing_custom_capacity VALUES(?,?,?)',(resource,id,json.dumps(value,sort_keys=True,separators=(',',':'))))
def proposal(plan,value=None):
    from .billing import BillingUnavailable
    try:return quote(plan,value)
    except (ValueError,TypeError):raise BillingUnavailable('Choose valid plan capacities within the supported limits.')
def validate_product(billing):
    from .billing import BillingUnavailable
    if not billing.custom_product or not billing.custom_prices:raise BillingUnavailable('Custom subscriptions are not configured yet.')
    product=billing.provider.product(billing.custom_product)
    if product.get('id')!=billing.custom_product or product.get('active') is not True or product.get('livemode') is not billing.live:raise BillingUnavailable('Custom subscription product could not be verified.')
