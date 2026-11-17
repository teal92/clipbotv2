import importlib

import pytest


def module():
    return importlib.import_module('tools.probe_native_tls')


def test_tls_probe_requires_good_connection_and_both_rejections():
    check = module().check_results
    assert check({'trusted':0,'untrusted':1,'wrongHostname':1}) == {
        'trusted':True,'untrusted':True,'wrongHostname':True}
    for results in ({'trusted':1,'untrusted':1,'wrongHostname':1},
                    {'trusted':0,'untrusted':0,'wrongHostname':1},
                    {'trusted':0,'untrusted':1,'wrongHostname':0}, {}):
        with pytest.raises(ValueError):
            check(results)


def test_tls_probe_never_changes_trust_or_uses_external_servers(tmp_path):
    arguments = module().ffmpeg_arguments(tmp_path/'ffmpeg',tmp_path/'root.pem',41234)
    assert arguments[arguments.index('-tls_verify')+1] == '1'
    assert arguments[arguments.index('-ca_file')+1] == str(tmp_path/'root.pem')
    assert arguments[arguments.index('-i')+1] == 'https://localhost:41234/probe.wav'
    for port in (0,65536,'https://example.com'):
        with pytest.raises(ValueError):
            module().ffmpeg_arguments(tmp_path/'ffmpeg',tmp_path/'root.pem',port)


def test_tls_negative_cases_must_fail_certificate_checks_not_unrelated_io():
    assert module().certificate_rejection(1,b'error:0A000086:SSL routines::certificate verify failed') is True
    assert module().certificate_rejection(1,b'hostname mismatch') is True
    for code,stderr in [(0,b'certificate verify failed'),(1,b'Connection refused'),(1,b'HTTP error 404')]:
        assert module().certificate_rejection(code,stderr) is False
