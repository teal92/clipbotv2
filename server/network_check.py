"""Secret-safe Stripe diagnostics. CLI uses read-only requests; never creates charges."""
import json,os,re,logging

CATEGORIES={'InvalidHeader':'invalid_header','SSLError':'certificate_or_tls','ProxyError':'proxy_connection','ConnectTimeout':'connect_timeout','ReadTimeout':'read_timeout','Timeout':'timeout','NameResolutionError':'dns_resolution','gaierror':'dns_resolution','NewConnectionError':'connection_failed','ConnectionRefusedError':'connection_refused','ConnectionResetError':'connection_reset'}

def key_shape(key):
    if not key:return 'missing'
    if key!=key.strip():return 'surrounding_whitespace'
    if any(character.isspace() for character in key):return 'embedded_whitespace'
    return 'sandbox_format' if re.fullmatch(r'sk_test_[A-Za-z0-9]+',key) else 'unsupported_key_mode'

def error_diagnostics(error):
    queue=[error];seen=set();classes=[];network='unknown'
    while queue and len(seen)<12:
        item=queue.pop(0)
        if not isinstance(item,BaseException) or id(item) in seen:continue
        seen.add(id(item));name=type(item).__name__
        if re.fullmatch(r'[A-Za-z_]{1,80}',name):classes.append(name)
        if network=='unknown' and name in CATEGORIES:network=CATEGORIES[name]
        for child in [item.__cause__,item.__context__,getattr(item,'reason',None),getattr(item,'original_error',None),*item.args]:
            if isinstance(child,BaseException):queue.append(child)
    return {'networkCause':network,'exceptionClasses':classes}

def log_billing_failure(error,stage):
    stage=stage if stage in ('checkout','reconciliation') else 'operation'
    code=getattr(error,'code',None);request_id=getattr(error,'request_id',None);status=getattr(error,'http_status',None);param=getattr(error,'param',None)
    safe_code=code if isinstance(code,str) and re.fullmatch(r'[a-z_]{1,64}',code) else 'unknown'
    safe_request=request_id if isinstance(request_id,str) and re.fullmatch(r'req_[A-Za-z0-9]{1,100}',request_id) else 'unavailable'
    safe_param=param if isinstance(param,str) and re.fullmatch(r'[a-z_\[\]0-9.]{1,100}',param) else 'unavailable'
    diagnostics=error_diagnostics(error)
    logging.getLogger('uvicorn.error').error('ClipBot billing %s failed: category=%s http_status=%s code=%s request_id=%s parameter=%s network_cause=%s exception_classes=%s key_configuration=%s',stage,type(error).__name__,status if type(status) is int else 'unknown',safe_code,safe_request,safe_param,diagnostics['networkCause'],','.join(diagnostics['exceptionClasses']),key_shape(os.getenv('STRIPE_SECRET_KEY','')))

def main():
    from .billing import StripeProvider
    import stripe
    key=os.getenv('STRIPE_SECRET_KEY','');shape=key_shape(key)
    print(json.dumps({'keyConfiguration':shape,'proxyConfigured':any(os.getenv(name) for name in ('HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy')),'customCABundleConfigured':bool(os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('SSL_CERT_FILE'))}))
    if shape!='sandbox_format':print('Read-only check skipped. Correct the sandbox key entry in Render.');return
    price_id=os.getenv('STRIPE_PRICE_STARTER','')
    if not re.fullmatch(r'price_[A-Za-z0-9]+',price_id):print('Read-only check skipped. Starter price reference is missing or malformed.');return
    try:
        price=StripeProvider(key).price(price_id)
        print(json.dumps({'stripeReachable':True,'sandboxPrice':price.get('livemode') is False,'starterPriceMatches':price.get('currency')=='usd' and price.get('unit_amount')==700}))
    except stripe.StripeError as error:
        print(json.dumps({'stripeReachable':False,'category':type(error).__name__,'httpStatus':getattr(error,'http_status',None),**error_diagnostics(error)}))
if __name__=='__main__':main()
