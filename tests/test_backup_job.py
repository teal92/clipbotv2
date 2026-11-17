import json,subprocess,os
from datetime import datetime,timezone
from pathlib import Path
import pytest


def fixture(tmp_path,monkeypatch):
 from ops import backup_job as job
 from ops import encrypted_backup as backup
 destination=tmp_path/'backups';destination.mkdir()
 key_path=tmp_path/'master.dpapi';key_path.write_bytes(b'existing-protected-key')
 identity=tmp_path/'identity';identity.write_text('fixture-private-not-real')
 hosts=tmp_path/'known-hosts';hosts.write_text('fixture-known-host-not-real')
 config=tmp_path/'config.json';config.write_text(json.dumps({'identity':str(identity),'knownHosts':str(hosts),'target':job.TARGET}))
 master=b'm'*32;monkeypatch.setattr(backup,'master_key',lambda path,create=False:master)
 monkeypatch.setattr(backup,'restrict_permissions',lambda *args,**kwargs:None)
 monkeypatch.setattr(job,'python_executable',lambda:Path('verified-python.exe'))
 return job,backup,destination,key_path,config,master


def test_success_requires_independently_verified_encrypted_file_and_hides_child_details(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 import sqlite3
 source=tmp_path/'source.db'
 with sqlite3.connect(source) as db:db.execute('CREATE TABLE sample(value)');db.execute("INSERT INTO sample VALUES('private-record')")
 encrypted=b.seal(b.snapshot_archive(source,{}),b's'*32,{'kind':'snapshot','version':1})
 wrapped=b.wrap_remote(encrypted,b's'*32,master)
 name='clipbot-20261015T120000Z-1234abcd.cbk'
 calls=[]
 def runner(args,**kwargs):
  calls.append((args,kwargs));(dest/name).write_bytes(wrapped)
  report={'backupSaved':True,'backupFile':name,'encryptedBytes':len(wrapped),'tablesCompared':1,'unexpectedSecret':'never-display'}
  return subprocess.CompletedProcess(args,0,json.dumps(report),'private-stderr')
 assert job.run_job(config,dest,key,runner)==0
 status=json.loads((dest/'backup-status.json').read_text())
 assert status['state']=='succeeded' and status['lastSuccessful']['file']==name
 assert status['lastSuccessful']['tablesCompared']==1
 assert 'private-record' not in json.dumps(status) and 'never-display' not in json.dumps(status)
 assert calls[0][1]['timeout']==120 and calls[0][1].get('shell',False) is False
 assert '--target' in calls[0][0] and calls[0][0][-1]==job.TARGET


def test_unverified_output_never_becomes_success_and_previous_success_survives(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 prior={'file':'clipbot-20261014T120000Z-1234abcd.cbk','completedAt':'2026-10-14T12:00:00+00:00','tablesCompared':1,'encryptedBytes':100}
 (dest/'backup-status.json').write_text(json.dumps({'version':1,'state':'succeeded','lastSuccessful':prior}))
 def runner(args,**kwargs):return subprocess.CompletedProcess(args,0,json.dumps({'backupSaved':True,'backupFile':'../../secret.cbk','encryptedBytes':1,'tablesCompared':1}),'password=secret')
 assert job.run_job(config,dest,key,runner)==1
 status=json.loads((dest/'backup-status.json').read_text());assert status['state']=='failed' and status['lastSuccessful']==prior
 assert 'secret' not in json.dumps(status) and status['error']==job.FAILURE


def test_missing_master_key_fails_without_creating_key_or_launching_process(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch);key.unlink()
 calls=[]
 assert job.run_job(config,dest,key,lambda *a,**k:calls.append(a))==1
 assert not key.exists() and not calls


def test_foreign_target_rejected_before_any_process(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 data=json.loads(config.read_text());data['target']='srv-other@ssh.oregon.render.com';config.write_text(json.dumps(data))
 calls=[];assert job.run_job(config,dest,key,lambda *a,**k:calls.append(a))==1;assert calls==[]


def test_duplicate_job_returns_without_overwriting_running_status(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 with job.exclusive_run(dest):
  assert job.run_job(config,dest,key,lambda *a,**k:pytest.fail('duplicate process'))==2
 assert not (dest/'backup-status.json').exists()


def test_child_timeout_records_generic_failure(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 def runner(*args,**kwargs):raise subprocess.TimeoutExpired('private-key-path',120,stderr='secret')
 assert job.run_job(config,dest,key,runner)==1
 text=(dest/'backup-status.json').read_text();assert 'secret' not in text and 'private-key-path' not in text


def test_background_permission_helpers_never_open_visible_console(tmp_path,monkeypatch):
 from ops import encrypted_backup as b
 if b.os.name!='nt':pytest.skip('Windows background-process protection')
 calls=[]
 def runner(args,**kwargs):
  calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,'"fixture","S-1-5-21-123"\n','')
 monkeypatch.setattr(b.subprocess,'run',runner)
 b.restrict_permissions(tmp_path,True)
 assert len(calls)==4 and all(k.get('creationflags')==subprocess.CREATE_NO_WINDOW for a,k in calls)


def test_failure_diagnostic_records_stage_without_exception_text(tmp_path,monkeypatch):
 job,b,dest,key,config,master=fixture(tmp_path,monkeypatch)
 def broken(*args,**kwargs):raise ValueError('password=private-value')
 monkeypatch.setattr(b,'master_key',broken)
 assert job.run_job(config,dest,key,lambda *a,**k:pytest.fail('no child expected'))==1
 diagnostic=json.loads((dest/'backup-diagnostic.json').read_text())
 assert diagnostic['stage']=='key-unlock' and diagnostic['failureClass']=='ValueError'
 assert 'private-value' not in json.dumps(diagnostic)


@pytest.mark.skipif(os.name != 'nt', reason='Windows background entry point')
def test_background_main_uses_protected_explicit_locations_not_session_environment(tmp_path,monkeypatch):
 from ops import backup_job as job
 folder=tmp_path/'Documents/ClipBotBackups';folder.mkdir(parents=True)
 config=tmp_path/'existing-config.json';key=tmp_path/'existing-master.dpapi'
 (folder/'backup-location.json').write_text(json.dumps({'configFile':str(config),'keyFile':str(key)}))
 monkeypatch.setattr(job.Path,'home',classmethod(lambda cls:tmp_path))
 monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'different-background-profile'))
 monkeypatch.setattr(job.sys,'argv',['backup-job'])
 calls=[];monkeypatch.setattr(job,'run_job',lambda *args:calls.append(args) or 0)
 assert job.main()==0 and calls==[(config,folder,key)]


@pytest.mark.skipif(os.name != 'nt', reason='Windows background entry point')
def test_background_main_rejects_unexpected_location_fields(tmp_path,monkeypatch):
 from ops import backup_job as job
 folder=tmp_path/'Documents/ClipBotBackups';folder.mkdir(parents=True)
 (folder/'backup-location.json').write_text(json.dumps({'configFile':'one','keyFile':'two','command':'malicious'}))
 monkeypatch.setattr(job.Path,'home',classmethod(lambda cls:tmp_path));monkeypatch.setattr(job.sys,'argv',['backup-job'])
 monkeypatch.setattr(job,'run_job',lambda *args:pytest.fail('no process for unreviewed configuration'))
 assert job.main()==1
