import pytest
from server.billing import Billing
from server.store import Store

FIELDS={'SECRET_KEY':'rk_live_fixture','WEBHOOK_SECRET':'whsec_live_fixture','PORTAL_CONFIGURATION':'bpc_live_fixture','PRICE_STARTER':'price_live_starter','PRICE_CREATOR':'price_live_creator','PRICE_PRO':'price_live_pro'}

def settings(monkeypatch):
 monkeypatch.setenv('CLIPBOT_BILLING_MODE','live');monkeypatch.setenv('CLIPBOT_LIVE_BILLING_ACCEPTED','true')
 for field,value in FIELDS.items():
  monkeypatch.setenv('STRIPE_LIVE_'+field,value)
  monkeypatch.setenv('STRIPE_'+field, value.replace('live','test'))

def test_live_config_uses_only_its_scoped_namespace(tmp_path,monkeypatch):
 settings(monkeypatch)
 service=Billing(Store(tmp_path/'scoped.db'),'https://clipbot.example.test')
 assert service.ready and service.provider.live
 assert service.secret=='whsec_live_fixture' and service.prices['starter']=='price_live_starter'
 assert service.portal_configuration=='bpc_live_fixture'

def test_shadow_live_settings_never_replace_running_sandbox_config(tmp_path,monkeypatch):
 settings(monkeypatch);monkeypatch.setenv('CLIPBOT_BILLING_MODE','test')
 service=Billing(Store(tmp_path/'sandbox.db'),'https://clipbot.example.test')
 assert service.ready and not service.provider.live
 assert service.secret=='whsec_test_fixture' and service.prices['starter']=='price_test_starter'

@pytest.mark.parametrize('missing',['WEBHOOK_SECRET','PRICE_PRO','PORTAL_CONFIGURATION'])
def test_partial_live_namespace_fails_closed_without_legacy_fallback(tmp_path,monkeypatch,missing):
 settings(monkeypatch)
 monkeypatch.delenv('STRIPE_LIVE_'+missing)
 # Even legacy live values must not silently fill a partial namespace.
 for field,value in FIELDS.items():monkeypatch.setenv('STRIPE_'+field,value)
 service=Billing(Store(tmp_path/'partial.db'),'https://clipbot.example.test')
 assert not service.ready
