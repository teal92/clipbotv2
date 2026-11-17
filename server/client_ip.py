"""Optional deployment-verified client IP for quotas, never authentication.

The Render/Cloudflare profile is safe only after the operator proves the public
ingress overwrites CF-Connecting-IP and prevents untrusted access to allowlisted
private peers. A CIDR match alone does not establish that trust relationship.
"""
import hmac
import re
from urllib.parse import urlsplit
import ipaddress
import os
from functools import lru_cache


@lru_cache(maxsize=16)
def _networks(value):
    if not value.strip():
        return ()
    try:
        parts = value.split(',')
        if len(parts) > 32:
            return ()
        return tuple(ipaddress.ip_network(part.strip(), strict=True) for part in parts)
    except ValueError:
        return ()


def client_ip(request):
    native = request.client.host if request.client else 'unknown'
    profile=os.getenv('CLIPBOT_TRUSTED_EDGE')
    if profile not in ('render-cloudflare','cloudflare-verified') or os.getenv('RENDER') != 'true':
        return native
    try:
        peer = ipaddress.ip_address(native)
    except ValueError:
        return native
    if not (peer.is_private or peer.is_loopback) or peer.is_unspecified or peer.is_multicast or peer.is_reserved:
        return native
    if profile=='cloudflare-verified':
        # Constant-time authentication of the overwriting hostname-only gateway.
        secret=os.getenv('CLIPBOT_EDGE_SECRET','')
        tokens=request.headers.getlist('x-clipbot-edge-token')
        hosts=request.headers.getlist('host')
        try:hostname=urlsplit(os.getenv('CLIPBOT_ORIGIN','')).hostname
        except ValueError:return native
        if (not re.fullmatch(r'[a-f0-9]{64}',secret) or len(tokens)!=1 or
            not re.fullmatch(r'[a-f0-9]{64}',tokens[0]) or not hmac.compare_digest(secret,tokens[0]) or
            not hostname or len(hosts)!=1 or hosts[0].lower() not in (hostname,hostname+':443')):
            return native
        values=request.headers.getlist('x-clipbot-client-ip')
        if len(values)!=1 or len(values[0])>45 or '%' in values[0]:return native
        try:claimed=ipaddress.ip_address(values[0])
        except ValueError:return native
        return str(claimed) if claimed.is_global and not (claimed.is_multicast or claimed.is_reserved or claimed.is_unspecified) else native
    networks = _networks(os.getenv('CLIPBOT_TRUSTED_PROXY_CIDRS', ''))
    if not any(peer.version == network.version and peer in network for network in networks):
        return native
    # Header duplication/list forms are never reduced to a caller-chosen entry.
    values = request.headers.getlist('cf-connecting-ip')
    if len(values) != 1 or len(values[0]) > 45 or '%' in values[0]:
        return native
    try:
        claimed = ipaddress.ip_address(values[0].strip())
    except ValueError:
        return native
    if not claimed.is_global or claimed.is_multicast or claimed.is_reserved or claimed.is_unspecified:
        return native
    return str(claimed)
