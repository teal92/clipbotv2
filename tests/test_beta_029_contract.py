import json
import pytest
from server.analysis import AnalysisDenied,parse_candidate


def value(**changes):
    return dict(start=3,lengthSeconds=20,score=80,title='Complete moment',caption='An evidenced clip',rationale='Setup and payoff',safetyFlags=[],**changes)


def test_duration_contract_normalizes_to_existing_worker_timestamps():
    candidate=parse_candidate(json.dumps(value()),40)
    assert candidate['start']==3 and candidate['end']==23
    assert 'lengthSeconds' not in candidate


@pytest.mark.parametrize('start,length',[(1.002,15),(4.001,60),(1.01,15)])
def test_fractional_starts_preserve_exact_duration_boundaries(start,length):
    candidate=value();candidate.update(start=start,lengthSeconds=length)
    result=parse_candidate(json.dumps(candidate),120)
    assert round(result['end']-result['start'],6)==length


@pytest.mark.parametrize('start,length',[(1.002,15),(4.001,60)])
def test_renderer_accepts_fractional_boundary_before_checking_source(tmp_path,start,length):
    from worker.render import render,RenderError
    with pytest.raises(RenderError) as error:
        render({'start':start,'end':start+length},tmp_path/'missing.mkv',[],tmp_path)
    assert error.value.code=='render_source_unavailable'


@pytest.mark.parametrize('length',[True,14,61,'20',float('inf')])
def test_duration_contract_never_pads_or_coerces_invalid_lengths(length):
    candidate=value();candidate['lengthSeconds']=length
    with pytest.raises(AnalysisDenied):parse_candidate(json.dumps(candidate),120)


def test_duration_contract_refuses_outside_captured_media():
    candidate=value();candidate['start']=30
    with pytest.raises(AnalysisDenied):parse_candidate(json.dumps(candidate),40)


def test_duration_contract_refuses_ambiguous_end_and_length():
    candidate=value();candidate['end']=23
    with pytest.raises(AnalysisDenied):parse_candidate(json.dumps(candidate),40)


def test_requested_lengths_are_explicit_supported_schema_values():
    from server.analysis import candidate_output_config
    config=candidate_output_config({'duration':40.021,'minClipSeconds':15,'maxClipSeconds':45})
    props=config['format']['schema']['anyOf'][0]['properties']
    assert props['lengthSeconds']['enum']==list(range(15,41))
    assert 'end' not in props
    assert 'minimum' not in json.dumps(config) and 'maximum' not in json.dumps(config)


def test_impossible_requested_length_never_calls_paid_provider(tmp_path):
    from server.store import Store
    from server.budgets import BudgetLedger
    from server.analysis import AnalysisService
    from test_analysis import Messages
    store=Store(tmp_path/'short.db');uid=store.create_user('owner@example.test','StrongLocalPass!2026','owner')
    messages=Messages();service=AnalysisService(store,BudgetLedger(store,enabled=True),messages)
    result=service.analyze(uid,'short',[{'start':0,'end':18,'text':'A short incomplete window'}],{'duration':20,'platform':'twitch','creator':'owner','minClipSeconds':30,'maxClipSeconds':45})
    assert result is None and messages.calls==0
    assert service.ledger.snapshot(uid)['reservedMicros']==0


def test_every_analysis_failure_code_can_be_recorded_without_masking_original_error():
    from server.analysis import ERROR_MESSAGES
    from server.pipeline_events import CODES
    from worker.client import REQUEST_ERROR_CODES
    assert set(ERROR_MESSAGES)<=CODES
    assert set(ERROR_MESSAGES)<=REQUEST_ERROR_CODES
