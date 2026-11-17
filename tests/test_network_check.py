import requests
from server.network_check import error_diagnostics,key_shape

def test_exception_chain_is_reported_without_messages():
    inner=requests.exceptions.InvalidHeader('Secret sk_test_NEVER_PRINT is invalid')
    outer=RuntimeError('Secret outside')
    outer.__cause__=inner
    result=error_diagnostics(outer)
    assert result['networkCause']=='invalid_header'
    assert 'NEVER_PRINT' not in str(result)
    assert 'Secret' not in str(result)

def test_key_shape_never_returns_secret():
    assert key_shape('sk_test_example')=='sandbox_format'
    assert key_shape('sk_test_example\n')=='surrounding_whitespace'
    assert key_shape('sk_test_a\nb')=='embedded_whitespace'
    assert key_shape('sk_live_example')=='unsupported_key_mode'
    assert key_shape('')=='missing'
