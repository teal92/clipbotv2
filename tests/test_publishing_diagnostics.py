import json
import pytest
from server.store import Store
from server.publishing_diagnostics import PublishingDiagnostics

def test_bundle_owned_bounded_and_excludes_provider_secrets(tmp_path):
 store=Store(tmp_path/'logs.db'); logs=PublishingDiagnostics(store)
 clip='a'*32
 logs.record('owner',clip,'b'*32,'instagram','prepared')
 logs.record('owner',clip,'b'*32,'instagram','published')
 bundle=logs.bundle('owner',clip)
 assert len(bundle['events'])==2
 assert bundle['events'][-1]['status']=='published'
 assert bundle['format']=='clipbot-publishing-session-v1'
 assert 'payload' not in json.dumps(bundle)
 with pytest.raises(KeyError):logs.bundle('other',clip)
 with pytest.raises(ValueError):logs.record('owner',clip,'b'*32,'instagram','failed',code='token-secret')

def test_bundle_groups_three_destinations_for_one_clip(tmp_path):
 store=Store(tmp_path/'logs.db'); logs=PublishingDiagnostics(store)
 for platform in ('tiktok','instagram','facebook'):logs.record('owner','a'*32,'b'*32,platform,'unknown',code='initialization_unconfirmed')
 assert len(logs.list('owner'))==1
 assert len(logs.bundle('owner','a'*32)['events'])==3
 assert logs.list('other')==[]
