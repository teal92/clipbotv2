from types import SimpleNamespace
import pytest
from server.claude_connection import key_configuration,check_connection,MODEL

def test_rejects_whitespace_without_using_key():
    assert key_configuration(' sk-ant-test')=='surrounding_whitespace'
    assert key_configuration('sk-ant-te\nst')=='embedded_whitespace'
    assert key_configuration('')=='missing'
    assert key_configuration('sk-ant-test')=='configured'

def test_connection_only_reads_model_metadata():
    class Models:
        def retrieve(self,model):
            assert model==MODEL
            return SimpleNamespace(id=MODEL)
    client=SimpleNamespace(models=Models())
    assert check_connection('sk-ant-test',client)=={'keyConfiguration':'configured','reachable':True,'model':MODEL,'dispatchEnabled':False}

def test_invalid_key_does_not_attempt_network():
    assert check_connection(' sk-ant-test',object())=={'keyConfiguration':'surrounding_whitespace','reachable':False,'dispatchEnabled':False}

def test_failure_does_not_expose_secret_or_provider_message():
    class Models:
        def retrieve(self,model):raise RuntimeError('secret sk-ant-sensitive transcript')
    result=check_connection('sk-ant-test',SimpleNamespace(models=Models()))
    assert result['reachable'] is False
    assert result['errorCategory']=='RuntimeError'
    assert 'sensitive' not in str(result)
