import json,threading
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from worker.processor import ClipProcessor

class ImmediatePool:
 def submit(self,fn,*args):fn(*args)

def test_local_edit_preserves_original_and_retries_identical_completion_without_analysis(tmp_path,monkeypatch):
 identity='a'*32;directory=tmp_path/identity;directory.mkdir()
 original=directory/'clip.mp4';original.write_bytes(b'original')
 source=directory/'capture.mkv';source.write_bytes(b'source')
 processor=ClipProcessor.__new__(ClipProcessor)
 processor.lock=threading.Lock();processor.stop=threading.Event();processor.preview_pool=ImmediatePool()
 candidate={'start':0,'end':40,'title':'Original','caption':'Before'}
 entry={'job':{'id':identity,'lease':'b'*32},'path':source,'phase':'review','transcript':[{'start':0,'end':40,'text':'hello'}],'candidate':candidate,'review_preview':'c'*64,'event':threading.Event()}
 processor.entries={identity:entry};processor.previews={'c'*64:original}
 calls=[];completion=[]
 edited={**candidate,'start':5,'end':25,'title':'Edited','caption':'After'}
 def request(method,path,body):
  calls.append(path)
  assert original.read_bytes()==b'original'
  if path.endswith('/begin'):return {'editId':'d'*32,'candidate':edited}
  if path.endswith('/complete'):
   completion.append(body)
   if len(completion)==1:raise TimeoutError('lost response')
   return {'ok':True}
  raise AssertionError(path)
 processor.client=SimpleNamespace(request=request)
 def render(value,path,transcript,destination,*,final_name):
  assert value==edited and transcript==entry['transcript']
  target=destination/final_name;target.write_bytes(b'edited')
  return {'path':target,'duration':20,'sha256':'e'*64,'sizeBytes':6,'width':1080,'height':1920,'framing':'blurred_fit'}
 monkeypatch.setattr('worker.processor.render',render)
 processor.start_edit(identity,'c'*64,{'title':'Edited','description':'After','start':5,'end':25})
 assert entry['edit_status']['status']=='complete'
 assert entry['candidate']==edited and original.read_bytes()==b'original'
 assert completion[0]==completion[1]
 assert all('/analyze' not in path for path in calls)
 assert processor.previews[entry['review_preview']].read_bytes()==b'edited'

def test_edit_requires_current_owned_preview_and_rejects_duplicate_busy_operations(tmp_path):
 processor=ClipProcessor.__new__(ClipProcessor);processor.lock=threading.Lock()
 processor.entries={'a':{'phase':'review','review_preview':'current','transcript':[1],'edit_busy':True}}
 with pytest.raises(ValueError):processor.start_edit('a','current',{})
 with pytest.raises(ValueError):processor.start_edit('a','foreign',{})


def test_valid_unicode_edit_fits_body_limit_but_oversized_requests_are_rejected(tmp_path):
 from fastapi.testclient import TestClient
 from worker.local_app import create_local_app
 uid='a'*32;job='b'*32;token='c'*64
 app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
 folder=tmp_path/job;folder.mkdir();path=folder/'clip.mp4';path.write_bytes(b'clip')
 app.state.previews[token]=path
 app.state.worker['client']=SimpleNamespace(token='synthetic-pairing',close=lambda:None,request=lambda *args:{'userId':uid,'jobs':[{'id':job}]})
 edit=Mock(return_value={'ok':True,'status':'saving'})
 app.state.worker['processor']=SimpleNamespace(start_edit=edit,close=lambda:None)
 headers={'Origin':'https://clipbot.example'}
 with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
  body={'userId':uid,'title':'Unicode caption','description':'😀'*1000,'start':0,'end':20}
  response=client.post('/feedback/'+token+'/edit',json=body,headers=headers)
  assert len(response.request.content)>4096
  assert response.status_code==200 and edit.call_count==1
  assert edit.call_args.args[2]['description']==body['description']
  response=client.post('/feedback/'+token+'/edit',content=b'x'*8193,headers={**headers,'Content-Type':'application/json'})
  assert response.status_code==413 and edit.call_count==1
