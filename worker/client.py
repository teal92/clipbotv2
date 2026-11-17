"""Minimal pairing/heartbeat client. No media upload and no cloud secrets."""
import argparse,getpass,ipaddress,os,time
from urllib.parse import urlsplit
import httpx

ANALYSIS_ERROR_CODES=frozenset({'analysis_failed','analysis_invalid_json','analysis_invalid_schema','analysis_invalid_range','analysis_invalid_metadata','analysis_incomplete','analysis_provider_auth','analysis_provider_rate_limit','analysis_provider_unavailable','analysis_provider_timeout','analysis_usage_unknown','analysis_invalid_transcript','analysis_configuration','analysis_input_limit'})
REQUEST_ERROR_CODES=ANALYSIS_ERROR_CODES|{'analysis_busy','review_limit','analysis_budget','analysis_preferences_changed','analysis_invalid_preferences','analysis_invalid_cue','service_rate_limited','analysis_request_invalid','analysis_authorization','service_unavailable','service_timeout'}
DEFAULT_ORIGIN='https://clipbot.your-domain.example'

def configured_origin():
    # Self-hosters point the Companion at their own server with CLIPBOT_SERVICE_ORIGIN.
    # The value gets the same checks as any service address (HTTPS, or loopback HTTP) and an
    # invalid value raises instead of silently falling back to a different server.
    value=os.environ.get('CLIPBOT_SERVICE_ORIGIN','').strip()
    return service_origin(value) if value else DEFAULT_ORIGIN

class WorkerRequestError(RuntimeError):
    def __init__(self,code,http_status=None):
        self.code=code if code in REQUEST_ERROR_CODES else 'analysis_failed'
        self.http_status=http_status if type(http_status) is int and 400<=http_status<=599 else None
        super().__init__('Davey analysis stopped ('+self.code+'). Check ClipBot job status. No automatic paid retry was started.')

def service_origin(value):
    parsed=urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/') or not parsed.hostname:raise ValueError('Enter only the ClipBot service address.')
    if parsed.scheme=='http':
        try:local=ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:local=parsed.hostname=='localhost'
        if not local:raise ValueError('Remote worker connections require HTTPS.')
    elif parsed.scheme!='https':raise ValueError('Use HTTPS, or HTTP for localhost only.')
    return value.rstrip('/')

class WorkerClient:
    def __init__(self,origin,transport=None):
        self.origin=service_origin(origin);self.token=None
        self.http=httpx.Client(base_url=self.origin,headers={'Origin':self.origin},timeout=15,follow_redirects=False,trust_env=False,transport=transport)
    def connect(self,code):
        result=self.http.post('/api/worker/connect',json={'code':code})
        if result.status_code!=201:raise RuntimeError('Pairing failed. Generate a new code in Connect Accounts and try again.')
        token=result.json().get('token')
        if not isinstance(token,str) or not 20<=len(token)<=100:raise RuntimeError('Invalid service response.')
        self.token=token
    def heartbeat(self):
        if not self.token:raise RuntimeError('Pair the worker first.')
        result=self.http.post('/api/worker/heartbeat',headers={'Authorization':'Bearer '+self.token})
        if result.status_code==401:self.token=None;raise RuntimeError('Worker access expired or was revoked. Pair again.')
        if result.status_code!=200:raise RuntimeError('Service unavailable. No processing started.')
        return result.json()
    def request(self,method,path,body=None):
        if not self.token:raise RuntimeError('Pair the worker first.')
        try:result=self.http.request(method,path,headers={'Authorization':'Bearer '+self.token},json=body,timeout=60 if path=='/api/worker/analyze' else 45 if path=='/api/worker/discovery' else 15)
        except httpx.TimeoutException:
            if path=='/api/worker/analyze':raise WorkerRequestError('service_timeout') from None
            raise
        except httpx.TransportError:
            if path=='/api/worker/analyze':raise WorkerRequestError('service_unavailable') from None
            raise
        if result.status_code==401:
            self.token=None;raise RuntimeError('Worker access expired or was revoked. Pair again.')
        if result.status_code!=200:
            if path=='/api/worker/analyze':
                try:
                    detail=result.json().get('detail',{});code=detail.get('code') if isinstance(detail,dict) else None
                except (ValueError,AttributeError):code=None
                if isinstance(code,str) and code in REQUEST_ERROR_CODES:raise WorkerRequestError(code,result.status_code)
                code='service_rate_limited' if result.status_code==429 else 'analysis_request_invalid' if result.status_code in (400,413,422) else 'analysis_authorization' if result.status_code in (403,409,428) else 'service_unavailable'
                raise WorkerRequestError(code,result.status_code)
            raise RuntimeError('Worker request was refused. Check ClipBot job status.')
        return result.json()
    def diagnostic(self,data):
        if not self.token or not isinstance(data,dict) or set(data)-{'event','jobId','lease','stage','code','elapsedMs','source','level','details'}:return False
        if 'details' in data:
            details=data['details']
            if not isinstance(details,dict) or set(details)-{'httpStatus'} or any(type(v) is not int or not 400<=v<=599 for v in details.values()):return False
        try:
            response=self.http.post('/api/worker/diagnostic',headers={'Authorization':'Bearer '+self.token},json=data,timeout=3)
            return response.status_code in (200,201,202,204)
        except Exception:return False
    def companion_heartbeat(self,report):return self.request('POST','/api/worker/companion-heartbeat',report)
    def configuration(self):return self.request('GET','/api/worker/config')
    def claim(self):return self.request('POST','/api/worker/jobs/claim').get('job')
    def report(self,job,event):return self.request('POST','/api/worker/jobs/report',{'jobId':job['id'],'lease':job['lease'],'event':event})
    def close(self):
        self.token=None;self.http.close()

def main():
    parser=argparse.ArgumentParser(description='ClipBot worker connection test. Monitoring and processing are not enabled yet.')
    parser.add_argument('--service',default='http://127.0.0.1:8766')
    parser.add_argument('--once',action='store_true',help='Check the connection once, then exit.')
    args=parser.parse_args()
    client=None
    try:
        client=WorkerClient(args.service)
        code=getpass.getpass('Pairing code from Connect Accounts (hidden): ')
        client.connect(code);code=''
        while True:
            client.heartbeat()
            print('Worker connected. Monitoring and processing remain disabled.')
            if args.once:break
            time.sleep(30)
    except KeyboardInterrupt:print('Worker stopped.')
    except (RuntimeError,ValueError,httpx.HTTPError):print('Connection stopped. Check the service address and generate a new pairing code. No media was transferred.');raise SystemExit(1)
    finally:
        if client:client.close()
if __name__=='__main__':main()
