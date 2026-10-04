from datetime import datetime, timezone
import pytest
from kev_mcp_server import server

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


@pytest.fixture
def inputs(monkeypatch):
    monkeypatch.setattr(server, '_utc_now', lambda: NOW)
    return ({'symbol':'TEST','source':'fixture','observed_at':'2026-10-03T11:59:30Z','features':{'price':100}},
            {'symbol':'TEST','side':'long','rationale':'Paper test','horizon_seconds':3600},
            {'max_market_age_seconds':60,'rules':['Use only a simulated account']})


def test_model_review_preserves_context_and_never_authorizes(monkeypatch, inputs):
    calls=[]
    def evaluate(state, questions):
        calls.append((state,questions))
        return {'model':'fixture','answers':{'review':{'type':'choice','choice':'insufficient_information',
            'probabilities':{'supports_proposal':.1,'concerns':.2,'insufficient_information':.7}}}}
    monkeypatch.setattr(server,'kev_evaluate',evaluate)
    result=server.kev_review_trade(*inputs)
    assert result['suggestion']=='insufficient_information'
    assert result['executed'] is False and result['execution_authorized'] is False
    assert result['probabilities_calibrated'] is False
    assert calls[0][0]['market_context']==inputs[0]
    assert len(calls)==1 and result['market_age_seconds']==30


@pytest.mark.parametrize('observed,reason', [('2026-10-03T11:00:00Z','stale_market_context'),
                                           ('2026-10-03T12:00:01Z','future_market_timestamp')])
def test_stale_or_future_skips_network(monkeypatch,inputs,observed,reason):
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:pytest.fail('No inference allowed'))
    inputs[0]['observed_at']=observed
    result=server.kev_review_trade(*inputs)
    assert result['suggestion']=='insufficient_information' and result['reason']==reason
    assert result['probabilities'] is None


def test_missing_constraints_skips_network(monkeypatch,inputs):
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:pytest.fail('No inference allowed'))
    inputs[2].pop('rules')
    assert 'risk_constraints.rules' in server.kev_review_trade(*inputs)['missing_fields']


@pytest.mark.parametrize('change', ['nan','symbol','timezone','side'])
def test_invalid_inputs(monkeypatch,inputs,change):
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:pytest.fail('No inference allowed'))
    if change=='nan': inputs[0]['features']['price']=float('nan')
    if change=='symbol': inputs[1]['symbol']='OTHER'
    if change=='timezone': inputs[0]['observed_at']='2026-10-03T11:59:30'
    if change=='side': inputs[1]['side']='buy'
    with pytest.raises(ValueError): server.kev_review_trade(*inputs)


@pytest.mark.parametrize('answer', [{}, {'type':'choice','choice':'supports_proposal',
    'probabilities':{'supports_proposal':.1,'concerns':.8,'insufficient_information':.1}},
    {'type':'choice','choice':'concerns','probabilities':{'supports_proposal':0,'concerns':True,'insufficient_information':0}}])
def test_invalid_model_response(monkeypatch,inputs,answer):
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:{'answers':{'review':answer}})
    with pytest.raises(RuntimeError): server.kev_review_trade(*inputs)
