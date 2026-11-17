"""Read-only Claude readiness check. Never sends a prompt or enables AI."""
import json,os,re
import anthropic

MODEL='claude-haiku-5-5'

def key_configuration(key):
    if not key:return 'missing'
    if key!=key.strip():return 'surrounding_whitespace'
    if any(char.isspace() for char in key):return 'embedded_whitespace'
    if not key.startswith('sk-ant-'):return 'unsupported_format'
    return 'configured'

def check_connection(key,client=None):
    result={'keyConfiguration':key_configuration(key),'reachable':False,'dispatchEnabled':False}
    if result['keyConfiguration']!='configured':return result
    owned=client is None
    try:
        # Pin the official endpoint: never inherit an alternate provider base URL.
        client=client or anthropic.Anthropic(api_key=key,base_url='https://api.anthropic.com',max_retries=0,timeout=10.0)
        model=client.models.retrieve(MODEL)
        result['reachable']=model.id==MODEL
        result['model']=MODEL
    except Exception as error:
        category=type(error).__name__
        result['errorCategory']=category if re.fullmatch(r'[A-Za-z_]{1,80}',category) else 'ProviderError'
        status=getattr(error,'status_code',None)
        if type(status) is int:result['httpStatus']=status
        # Never log exception text, response bodies, keys, or authorization headers.
    finally:
        if owned and client is not None:client.close()
    return result

if __name__=='__main__':
    result=check_connection(os.getenv('ANTHROPIC_API_KEY',''))
    print(json.dumps(result))
    raise SystemExit(0 if result['reachable'] else 1)
