import pytest
from worker.windows_integration import parse_pair_link

def test_app_links_accept_only_one_bounded_pairing_code():
 assert parse_pair_link('clipbot-companion://pair?code='+'a'*24)=='a'*24
 for ok in ['clipbot-companion://pair/?code='+'a'*24,'CLIPBOT-COMPANION://Pair?code='+'a'*24]:assert parse_pair_link(ok)=='a'*24
 for value in ['https://evil.test/','clipbot-companion://run?code='+'a'*24,'clipbot-companion://pair?code='+'a'*24+'&service=https://evil.test','clipbot-companion://pair?code=x','clipbot-companion://pair/path?code='+'a'*24,'clipbot-companion://pair//?code='+'a'*24]:
  with pytest.raises(ValueError):parse_pair_link(value)

def test_singleton_is_held_until_shutdown_work_finishes(tmp_path,monkeypatch):
 import os,threading,time
 if os.name!='nt':pytest.skip('Windows singleton integration')
 import worker.windows_integration as integration
 from worker.companion import finish_shutdown
 from types import SimpleNamespace
 monkeypatch.setattr(integration,'user_directory',lambda:tmp_path)
 first=integration.SingleInstance();assert first.primary
 release=threading.Event();worker=threading.Thread(target=release.wait);worker.start()
 closer=threading.Thread(target=finish_shutdown,args=(SimpleNamespace(should_exit=False),worker,first));closer.start()
 second=None;third=None
 try:
  time.sleep(.02);second=integration.SingleInstance();assert not second.primary;second.close()
  release.set();closer.join(timeout=2);assert not closer.is_alive()
  third=integration.SingleInstance();assert third.primary
 finally:
  release.set();closer.join(timeout=2);first.close()
  if second:second.close()
  if third:third.close()
