from server.client_ip import client_ip
from starlette.requests import Request


def request(peer='10.1.2.3', claimed='8.8.8.8', extra=()):
    return Request({'type': 'http', 'client': (peer, 123),
        'headers': [(b'cf-connecting-ip', claimed.encode()), *extra]})


def profile(monkeypatch):
    monkeypatch.setenv('CLIPBOT_TRUSTED_EDGE', 'render-cloudflare')
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('CLIPBOT_TRUSTED_PROXY_CIDRS', '10.1.0.0/16,fd00:1234::/48')


def test_profile_disabled_ignores_forged_cloudflare_header(monkeypatch):
    profile(monkeypatch)
    monkeypatch.delenv('CLIPBOT_TRUSTED_EDGE')
    assert client_ip(request()) == '10.1.2.3'


def test_render_marker_required(monkeypatch):
    profile(monkeypatch)
    monkeypatch.delenv('RENDER')
    assert client_ip(request()) == '10.1.2.3'


def test_public_peer_cannot_claim_cloudflare_identity(monkeypatch):
    profile(monkeypatch)
    monkeypatch.setenv('CLIPBOT_TRUSTED_PROXY_CIDRS', '0.0.0.0/0')
    assert client_ip(request(peer='1.1.1.1')) == '1.1.1.1'


def test_trusted_private_peer_accepts_public_ipv4_and_ipv6(monkeypatch):
    profile(monkeypatch)
    assert client_ip(request()) == '8.8.8.8'
    assert client_ip(request(peer='fd00:1234::2', claimed='2606:4700:4700::1111')) == '2606:4700:4700::1111'


def test_unlisted_private_peer_cannot_claim_cloudflare_identity(monkeypatch):
    profile(monkeypatch)
    assert client_ip(request(peer='10.2.3.4')) == '10.2.3.4'


def test_forwarded_for_never_used(monkeypatch):
    profile(monkeypatch)
    assert client_ip(request(extra=[(b'x-forwarded-for', b'1.1.1.1')])) == '8.8.8.8'
    assert client_ip(request(claimed='', extra=[(b'x-forwarded-for', b'1.1.1.1')])) == '10.1.2.3'


def test_multiple_private_or_invalid_claims_are_ignored(monkeypatch):
    profile(monkeypatch)
    for claimed in ('8.8.8.8, 1.1.1.1', '10.2.3.4', '127.0.0.1', '::1',
                    'fd00::1', '169.254.1.1', 'not-an-ip', '8.8.8.8:443', 'fe80::1%eth0'):
        assert client_ip(request(claimed=claimed)) == '10.1.2.3'
    assert client_ip(request(extra=[(b'cf-connecting-ip', b'1.1.1.1')])) == '10.1.2.3'


def test_invalid_or_missing_allowlist_fails_closed(monkeypatch):
    profile(monkeypatch)
    for cidrs in ('', 'invalid', '10.1.0.0/16,invalid'):
        monkeypatch.setenv('CLIPBOT_TRUSTED_PROXY_CIDRS', cidrs)
        assert client_ip(request()) == '10.1.2.3'
