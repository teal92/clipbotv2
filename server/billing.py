"""Mode-bound Stripe billing, default test; live requires explicit release acceptance."""
import os,secrets,time
from urllib.parse import urlsplit
import stripe
from .pricing import quote
from .billing_modes import resource_mode,bind_mode

class BillingUnavailable(Exception):pass

class StripeProvider:
    live=False
    def __init__(self,key):
        self.live=key.startswith(("sk_live_","rk_live_"))
        self.client=stripe.StripeClient(key,max_network_retries=0,http_client=stripe.RequestsClient(timeout=10))
    def price(self,id):return self.client.v1.prices.retrieve(id).to_dict()
    def product(self,id):return self.client.v1.products.retrieve(id).to_dict()
    def checkout(self,params,key):return self.client.v1.checkout.sessions.create(params,options={'idempotency_key':key}).to_dict()
    def cancel(self,id,key):return self.client.v1.subscriptions.update(id,{'cancel_at_period_end':True},options={'idempotency_key':key}).to_dict()
    def cancel_now(self,id,key):return self.client.v1.subscriptions.cancel(id,{'invoice_now':False,'prorate':False},options={'idempotency_key':key}).to_dict()
    def cancel_schedule_now(self,id,key):return self.client.v1.subscription_schedules.cancel(id,{'invoice_now':False,'prorate':False},options={'idempotency_key':key}).to_dict()
    def cancel_schedule(self,id,params,key):return self.client.v1.subscription_schedules.update(id,params,options={'idempotency_key':key}).to_dict()
    def portal_config(self,id):return self.client.v1.billing_portal.configurations.retrieve(id).to_dict()
    def portal(self,customer,config,url):return self.client.v1.billing_portal.sessions.create({'customer':customer,'configuration':config,'return_url':url}).to_dict()
    def subscription(self,id):return self.client.v1.subscriptions.retrieve(id,params={'expand':['latest_invoice']}).to_dict()
    def schedule(self,id):return self.client.v1.subscription_schedules.retrieve(id).to_dict()
    def upgrade(self,id,params,key):return self.client.v1.subscriptions.update(id,params,options={'idempotency_key':key}).to_dict()
    def downgrade(self,id,old_price,new_price,starts,ends,key):
        schedule=self.client.v1.subscription_schedules.create({'from_subscription':id},options={'idempotency_key':key+'-create'}).to_dict()
        phases=schedule.get('phases') or [];phase=phases[0] if len(phases)==1 else {}
        items=phase.get('items') or [];current=items[0] if len(items)==1 else {}
        price=current.get('price');price_id=price.get('id') if isinstance(price,dict) else price
        if (schedule.get('subscription')!=id or schedule.get('livemode') is not self.live or
            price_id!=old_price or current.get('quantity')!=1 or phase.get('start_date')!=int(starts) or phase.get('end_date')!=int(ends)):
            raise BillingUnavailable('The subscription schedule changed. Billing needs reconciliation.')
        preserved={k:phase[k] for k in ('collection_method','default_payment_method','automatic_tax','invoice_settings','metadata') if phase.get(k) is not None}
        params={'end_behavior':'release','proration_behavior':'none','phases':[
            {**preserved,'start_date':int(starts),'end_date':int(ends),'items':[{'price':old_price,'quantity':1}]},
            {**preserved,'start_date':int(ends),'duration':{'interval':'month','interval_count':1},'items':[{'price':new_price,'quantity':1}],'proration_behavior':'none'}]}
        return self.client.v1.subscription_schedules.update(schedule['id'],params,options={'idempotency_key':key+'-schedule'}).to_dict()

class Billing:
    def __init__(self,store,origin,provider=None,prices=None):
        self.store=store;self.origin=origin
        self.mode=os.getenv('CLIPBOT_BILLING_MODE','test');self.live=self.mode=='live'
        store.billing_mode=self.mode
        fields=('SECRET_KEY','WEBHOOK_SECRET','PORTAL_CONFIGURATION','PRICE_STARTER','PRICE_CREATOR','PRICE_PRO','CUSTOM_PRODUCT','CUSTOM_PRICES')
        # Select one complete namespace. Partial live settings never borrow sandbox values.
        prefix='STRIPE_LIVE_' if self.live and any('STRIPE_LIVE_'+field in os.environ for field in fields) else 'STRIPE_'
        self.portal_configuration=os.getenv(prefix+'PORTAL_CONFIGURATION','')
        self.secret=os.getenv(prefix+'WEBHOOK_SECRET','')
        self.prices=prices or {plan:os.getenv(prefix+'PRICE_'+plan.upper(),'') for plan in ('starter','creator','pro')}
        key=os.getenv(prefix+'SECRET_KEY','')
        from .custom_billing import catalog,schema
        self.custom_product=os.getenv(prefix+'CUSTOM_PRODUCT','')
        self.custom_prices=catalog(os.getenv(prefix+'CUSTOM_PRICES',''))
        with store.connection() as db:schema(db)
        key_ok=key.startswith(('sk_live_','rk_live_') if self.live else ('sk_test_','rk_test_'))
        release_ok=not self.live or os.getenv('CLIPBOT_LIVE_BILLING_ACCEPTED')=='true'
        self.provider=(provider or (StripeProvider(key) if key_ok and self.secret.startswith('whsec_') and all(self.prices.values()) else None)) if self.mode in ('test','live') and release_ok and (not self.live or key_ok and self.secret.startswith('whsec_') and all(self.prices.values()) and self.portal_configuration) else None
    @property
    def ready(self):return self.provider is not None
    def price_id(self,plan,custom=None):
        from .custom_billing import proposal
        return self.custom_prices.get(str(proposal(plan,custom)['monthlyCents']),'') if plan=='custom' else self.prices.get(plan,'')
    def valid_price(self,item,plan,custom=None):
        if plan not in ('starter','creator','pro','custom'):return False
        from .custom_billing import proposal
        try:expected=proposal(plan,custom);price_id=self.price_id(plan,custom)
        except BillingUnavailable:return False
        if not price_id:return False
        price=item.get('price') or {};recurring=price.get('recurring') or {}
        return (isinstance(price,dict) and isinstance(recurring,dict) and type(item.get('quantity')) is int and item['quantity']==1 and
                price.get('id')==price_id and (plan!='custom' or price.get('product')==self.custom_product) and price.get('currency')=='usd' and type(price.get('unit_amount')) is int and
                price['unit_amount']==expected['monthlyCents'] and price.get('livemode') is self.live and recurring.get('interval')=='month' and
                type(recurring.get('interval_count')) is int and recurring['interval_count']==1)
    def cancel(self,uid):
        from .billing_management import cancel
        return cancel(self,uid)
    def cancellation_status(self,uid):
        from .billing_management import cancellation_status
        return cancellation_status(self,uid)
    def portal(self,uid):
        from .billing_management import portal
        return portal(self,uid)
    def change(self,uid,plan,custom=None):
        from .customer_access import require_customer_ready
        require_customer_ready(self.store,uid)
        from .billing_changes import change
        return change(self,uid,plan,custom)
    def change_status(self,uid):
        from .billing_changes import status
        return status(self,uid)
    def validate_live_configuration(self):
        if self.live:
            from .billing_management import validate_portal
            validate_portal(self)
            for candidate in ('starter','creator','pro'):
                configured=self.provider.price(self.prices[candidate])
                if configured.get('active') is not True or not self.valid_price({'quantity':1,'price':configured},candidate):raise BillingUnavailable('Live plan prices require configuration acceptance.')

    def start(self,uid,plan,custom=None):
        from .customer_access import require_customer_ready
        require_customer_ready(self.store,uid)
        from .custom_billing import proposal,config,bind,validate_product
        selected=proposal(plan,custom)
        if not self.ready or not self.price_id(plan,custom):raise BillingUnavailable('Checkout is unavailable for this plan.')
        self.validate_live_configuration()
        if plan=='custom':validate_product(self)
        price=self.provider.price(self.price_id(plan,custom))
        if price.get('active') is not True or not self.valid_price({'quantity':1,'price':price},plan,custom):raise BillingUnavailable('Stripe price does not match the configured plan and mode.')
        completed_request=''
        with self.store.connection() as db:
            previous=db.execute('SELECT status,subscription,request_id,customer FROM billing_state WHERE user_id=?',(uid,)).fetchone()
        if previous:
            with self.store.connection() as db:
                if resource_mode(db,'state',uid)!=self.mode:raise BillingUnavailable('Billing mode changed. Use a separate billing database or reconcile the previous mode before checkout.')
            subscription=self.provider.subscription(previous['subscription'])
            if (subscription.get('livemode') is not self.live or subscription.get('id')!=previous['subscription'] or subscription.get('customer')!=previous['customer'] or subscription.get('metadata',{}).get('request_id')!=previous['request_id']):
                raise BillingUnavailable('Existing subscription ownership could not be verified. No new checkout was created.')
            if subscription.get('status') not in ('canceled','incomplete_expired'):
                raise BillingUnavailable('An existing subscription is still recoverable. Resolve or cancel it before starting another checkout.')
            completed_request=previous['request_id']
        with self.store.connection(atomic=True) as db:
            state=db.execute('SELECT status,expires,subscription,request_id FROM billing_state WHERE user_id=?',(uid,)).fetchone()
            if state and (not previous or state['subscription']!=previous['subscription'] or state['request_id']!=previous['request_id']):
                raise BillingUnavailable('Billing changed. Refresh before requesting checkout.')
            if state and state['status']=='active' and state['expires']>time.time():raise BillingUnavailable('You already have an active subscription. Cancel it before purchasing another.')
            row=db.execute("SELECT r.* FROM billing_requests r LEFT JOIN billing_modes m ON m.resource='request' AND m.id=r.id WHERE r.user_id=? AND r.created>? AND COALESCE(m.mode,'test')=? ORDER BY r.created DESC LIMIT 1",(uid,time.time()-86400,self.mode)).fetchone()
            if row and row['id']==completed_request:row=None
            if row:
                if row['plan']!=plan:raise BillingUnavailable('A checkout for another plan is pending. Finish it or wait for its 24-hour session to expire.')
                if plan=='custom' and config(db,'request',row['id'])!=custom:raise BillingUnavailable('A checkout for different Custom capacities is pending.')
                request_id=row['id'];created=row['created']
                if row['url']:return {'url':row['url'],'sandbox':not self.live}
            else:
                request_id=secrets.token_hex(16);created=time.time()
                db.execute('INSERT INTO billing_requests(id,user_id,plan,created) VALUES(?,?,?,?)',(request_id,uid,plan,created))
                bind_mode(db,'request',request_id,self.mode)
                if plan=='custom':bind(db,'request',request_id,custom)
        params={'mode':'subscription','line_items':[{'price':self.price_id(plan,custom),'quantity':1}],'client_reference_id':uid,'metadata':{'request_id':request_id},'subscription_data':{'metadata':{'request_id':request_id}},'success_url':self.origin+'/?checkout=success','cancel_url':self.origin+'/?checkout=cancelled'}
        # Request schema v2 removes the API-rejected payment_method_types field.
        # Saved successful sessions are reused above; only unsaved rejected requests get this corrected key.
        session=self.provider.checkout(params,'clipbot-checkout-v2-'+request_id)
        if ('livemode' in session or self.live) and session.get('livemode') is not self.live:raise BillingUnavailable('Checkout response mode does not match configured billing.')
        url=session.get('url','')
        if not isinstance(url,str) or not 1<=len(url)<=4096 or any(ord(c)<=32 or ord(c)==127 for c in url):raise BillingUnavailable('Invalid checkout response.')
        try:
            parsed=urlsplit(url)
            valid=parsed.scheme=='https' and parsed.hostname=='checkout.stripe.com' and not parsed.username and not parsed.password and parsed.port in (None,443)
        except ValueError:valid=False
        # Stripe's hosted checkout includes an opaque fragment; preserve it.
        if not valid:raise BillingUnavailable('Invalid checkout response.')
        with self.store.connection() as db:db.execute('UPDATE billing_requests SET session_id=?,url=? WHERE id=?',(session['id'],url,request_id))
        return {'url':url,'sandbox':not self.live}
    def verify(self,body,signature):
        if not self.ready or not self.secret:raise BillingUnavailable('Billing is not configured.')
        try:return stripe.Webhook.construct_event(body,signature,self.secret,tolerance=300).to_dict()
        except (ValueError,stripe.SignatureVerificationError):raise BillingUnavailable('Invalid payment event signature.')
    def receive(self,event):
        if not self.ready or event.get('livemode') is not self.live:raise BillingUnavailable('Payment event mode does not match configured billing.')
        kind=event.get('type','');obj=event.get('data',{}).get('object',{})
        if kind.startswith('customer.subscription.'):
            subscription_id=obj.get('id')
        elif kind in ('checkout.session.completed','checkout.session.async_payment_succeeded'):
            subscription_id=obj.get('subscription')
        elif kind in ('invoice.paid','invoice.payment_failed'):
            subscription_id=obj.get('subscription') or ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription')
        else:return
        if not subscription_id:return
        # Serialize reconciliation and re-fetch current provider state, avoiding stale event snapshots.
        with self.store.connection(atomic=True) as db:
            if db.execute('SELECT 1 FROM billing_events WHERE id=?',(event['id'],)).fetchone():return
            sub=self.provider.subscription(subscription_id)
            if sub.get('livemode') is not self.live or sub.get('id')!=subscription_id:raise BillingUnavailable('The subscription could not be verified.')
            request_id=sub.get('metadata',{}).get('request_id')
            request=db.execute('SELECT * FROM billing_requests WHERE id=?',(request_id,)).fetchone()
            if not request:return
            if resource_mode(db,'request',request_id)!=self.mode:raise BillingUnavailable('Payment request belongs to a different mode.')
            uid=request['user_id']
            if db.execute('SELECT 1 FROM billing_state WHERE user_id=?',(uid,)).fetchone() and resource_mode(db,'state',uid)!=self.mode:raise BillingUnavailable('Subscription belongs to a different mode.')
            owned=db.execute('SELECT subscription,customer FROM billing_state WHERE user_id=?',(uid,)).fetchone()
            if owned and owned['subscription']==subscription_id and owned['customer']!=sub.get('customer'):
                raise BillingUnavailable('Subscription ownership changed; reconciliation is required.')
            existing=db.execute('SELECT subscription,request_id FROM billing_state WHERE user_id=?',(uid,)).fetchone()
            if existing and existing['subscription']!=subscription_id:
                previous=db.execute('SELECT created FROM billing_requests WHERE id=?',(existing['request_id'],)).fetchone()
                if previous and previous['created']>=request['created']:return
            items=sub.get('items',{}).get('data',[])
            item=items[0] if len(items)==1 else {}
            invoice=sub.get('latest_invoice') or {}
            expires=item.get('current_period_end',sub.get('current_period_end',0))
            starts=item.get('current_period_start',sub.get('current_period_start',0))
            from .billing_schedule_cancellation import reconcile_plan
            reconcile_plan(self,db,uid,sub,expires)
            from .billing_changes import resolve
            plan,adjustment,preserve=resolve(self,db,sub,request,item,starts,expires)
            from .custom_billing import proposal as capacity_proposal,config,bind
            custom=config(db,'state',uid) if db.execute('SELECT 1 FROM billing_state WHERE user_id=? AND subscription=?',(uid,sub['id'])).fetchone() else config(db,'request',request_id)
            proposal=capacity_proposal(plan,custom if plan=='custom' else None);valid_price=self.valid_price(item,plan,custom if plan=='custom' else None)
            from .billing_usage import valid_period
            active=sub.get('status')=='active' and isinstance(invoice,dict) and (invoice.get('status')=='paid' or preserve) and type(expires) in (int,float) and expires>time.time() and valid_price and valid_period(starts,expires) and not sub.get('pause_collection')
            from .billing_changes import capacity_snapshot
            capacity=capacity_snapshot(db,uid,subscription_id,starts,expires) if active else None
            if capacity:
                proposal=capacity
                adjustment=None
            monthly_reviews=adjustment['review_limit'] if adjustment else proposal['monthlyReviews']
            db.execute('INSERT OR REPLACE INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,subscription_id,sub['customer'],plan,'active' if active else 'inactive',expires or 0,monthly_reviews,request_id))
            bind_mode(db,'state',uid,self.mode)
            bind(db,'state',uid,custom if plan=='custom' else None)
            from .billing_management import reconcile_cancellation
            reconcile_cancellation(self,db,uid,sub,expires)
            db.execute('DELETE FROM coverage WHERE user_id=?',(uid,))
            db.execute('DELETE FROM billing_periods WHERE user_id=?',(uid,))
            if active:db.execute('INSERT INTO billing_periods(user_id,subscription,starts,ends) VALUES(?,?,?,?)',(uid,subscription_id,starts,expires))
            if active:
                values=proposal['quantities']
                db.execute('INSERT INTO coverage VALUES(?,?,?,?,?,?,?)',(uid,values['dailyReviews'] if values['dailyReviews'] is not None else 1000000,adjustment['ai_limit'] if adjustment else proposal['aiCeilingMicros'],values['scouts'],values['streamerFavorites'],values['categoryFavorites'],values.get('postsPerPlatformDaily') or 10))
            db.execute('INSERT INTO billing_events VALUES(?,?)',(event['id'],time.time()))
