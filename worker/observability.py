"""Local bounded, metadata-only diagnostics; never log exception messages or media paths."""
import json,logging,re
from logging.handlers import RotatingFileHandler
from pathlib import Path
logger=logging.getLogger('clipbot.companion.pipeline');logger.setLevel(logging.INFO);logger.propagate=False
if not logger.handlers:logger.addHandler(logging.StreamHandler())
def configure(root):
    path=Path(root)/'logs';path.mkdir(parents=True,exist_ok=True)
    if not any(isinstance(h,RotatingFileHandler) for h in logger.handlers):
        h=RotatingFileHandler(path/'pipeline.log',maxBytes=524288,backupCount=2,encoding='utf-8');h.setFormatter(logging.Formatter('%(asctime)s %(message)s'));logger.addHandler(h)
def trace(event,job=None,**fields):
    clean={'event':event if re.fullmatch(r'[a-z_]{1,60}',str(event)) else 'invalid_event'}
    if job and re.fullmatch(r'[a-f0-9]{32}',str(job.get('id',''))):clean['jobId']=job['id']
    for key in ('stage','code','exceptionType'):
        if key in fields and re.fullmatch(r'[A-Za-z_]{1,80}',str(fields[key])):clean[key]=fields[key]
    if type(fields.get('elapsedMs')) is int:clean['elapsedMs']=max(0,min(86400000,fields['elapsedMs']))
    logger.info(json.dumps(clean,separators=(',',':')))
    return clean
