import pytest
from starlette.requests import Request
from server.client_ip import client_ip

TOKEN='a'*64

def gateway_request(ip='8.8.8.8',token=TOKEN,peer='10.199.1.2',extra=()):
 return Request({'type':'http','client':(peer,123),'headers':[(b'host',b'clipbot.example.test'),(b'x-clipbot-client-ip',ip.encode()),(b'x-clipbot-edge-token',token.encode()),*extra]})

@pytest.fixture
def gateway(monkeypatch):
 monkeypatch.setenv('RENDER','true');monkeypatch.setenv('CLIPBOT_ORIGIN','https://clipbot.example.test');monkeypatch.setenv('CLIPBOT_TRUSTED_EDGE','cloudflare-verified');monkeypatch.setenv('CLIPBOT_EDGE_SECRET',TOKEN)

def test_authenticated_gateway_survives_private_proxy_address_changes(gateway):
 for peer in ('10.199.1.2','10.199.200.7','fd00::7'):
  assert client_ip(gateway_request(peer=peer))=='8.8.8.8'
 assert client_ip(gateway_request(ip='2606:4700:4700::1111'))=='2606:4700:4700::1111'

@pytest.mark.parametrize('change',['wrong_token','duplicate_token','duplicate_ip','wrong_host','public_peer','not_render','weak_secret','profile_off'])
def test_forged_or_ambiguous_gateway_falls_back_to_native(gateway,monkeypatch,change):
 args={}
 if change=='wrong_token':args['token']='b'*64
 elif change=='duplicate_token':args['extra']=[(b'x-clipbot-edge-token',TOKEN.encode())]
 elif change=='duplicate_ip':args['extra']=[(b'x-clipbot-client-ip',b'1.1.1.1')]
 elif change=='wrong_host':args['extra']=[(b'host',b'other.example.test')]
 elif change=='public_peer':args['peer']='1.1.1.1'
 elif change=='not_render':monkeypatch.delenv('RENDER')
 elif change=='weak_secret':monkeypatch.setenv('CLIPBOT_EDGE_SECRET','weak')
 else:monkeypatch.delenv('CLIPBOT_TRUSTED_EDGE')
 assert client_ip(gateway_request(**args))==args.get('peer','10.199.1.2')

@pytest.mark.parametrize('ip',['10.0.0.1','127.0.0.1','::1','fd00::1','8.8.8.8,1.1.1.1','8.8.8.8:443','fe80::1%eth0','not-an-ip'])
def test_gateway_rejects_nonpublic_or_malformed_addresses(gateway,ip):
 assert client_ip(gateway_request(ip=ip))=='10.199.1.2'

def test_standard_forwarding_headers_cannot_override_gateway_identity(gateway):
 assert client_ip(gateway_request(extra=[(b'cf-connecting-ip',b'1.1.1.1'),(b'x-forwarded-for',b'1.0.0.1')]))=='8.8.8.8'
