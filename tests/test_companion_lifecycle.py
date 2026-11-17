from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import Mock
from worker.lifecycle import CompanionLifecycle

def test_transient_outage_preserves_capture_and_repeated_outage_cancels():
 event=Event();runtime=Mock();runtime.active={'one':(Mock(),event)};runtime.tick.side_effect=TimeoutError();processor=Mock();client=NS(token='valid')
 lifecycle=CompanionLifecycle(runtime,processor,client)
 assert lifecycle.tick()==5 and not event.is_set()
 assert lifecycle.tick()==10 and not event.is_set()
 assert lifecycle.tick()==20 and event.is_set()
 processor.close.assert_not_called();runtime.close.assert_not_called()
 runtime.tick.side_effect=None;assert lifecycle.tick()==5

def test_revocation_shuts_down_processing_and_previews():
 runtime=Mock();runtime.active={};runtime.tick.side_effect=RuntimeError();processor=Mock();client=NS(token=None)
 lifecycle=CompanionLifecycle(runtime,processor,client)
 assert lifecycle.tick() is None
 processor.close.assert_called_once();runtime.close.assert_called_once()

def test_saved_pairing_survives_initial_network_outage(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from worker.local_app import create_local_app
 from unittest.mock import Mock
 monkeypatch.setattr('worker.credentials.load',lambda *args:'valid-pairing-token-123456')
 client=Mock();client.token=None;client.heartbeat.side_effect=TimeoutError()
 monkeypatch.setattr('worker.local_app.WorkerClient',lambda *_:client)
 monkeypatch.setattr('worker.local_app.prerequisites',lambda *_:{'tools':False})
 with TestClient(create_local_app('https://clipbot.example',tmp_path)):
  assert client.token=='valid-pairing-token-123456'
