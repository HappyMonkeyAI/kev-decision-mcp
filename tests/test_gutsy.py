import pytest
from kev_mcp_server import server


def test_reject_mass_is_preserved_and_compared_unconditionally():
    result=server._rejection_metadata({'choice':'support','probabilities':{'support':.9,'other':.1},'reject':.6})
    assert result['rejection_dominates'] is True
    assert result['unconditional_option_probabilities']['support']==pytest.approx(.36)
    assert sum(result['unconditional_option_probabilities'].values())+result['rejection_probability']==pytest.approx(1)


def test_missing_reject_on_gutsy_is_an_error(monkeypatch):
    monkeypatch.setenv('KEV_BACKEND','gutsy')
    with pytest.raises(RuntimeError,match='missing'):
        server._rejection_metadata({'choice':'x','probabilities':{'x':1}})


def test_rejection_metadata_rejects_empty_or_invalid_probabilities():
    with pytest.raises(RuntimeError, match='option probabilities'):
        server._rejection_metadata({'choice':'x','probabilities':{},'reject':.5})
    with pytest.raises(RuntimeError, match='option probabilities'):
        server._rejection_metadata({'choice':'x','probabilities':{'x':0.5},'reject':.5})


@pytest.mark.parametrize('reject',[True,-.1,1.1,float('nan')])
def test_invalid_reject(reject):
    with pytest.raises(RuntimeError):
        server._rejection_metadata({'choice':'x','probabilities':{'x':1},'reject':reject})


def test_gutsy_score_latency_and_model_alias(monkeypatch):
    monkeypatch.setenv('KEV_BACKEND','gutsy')
    monkeypatch.setenv('KEV_API_MODEL','gutsy-0.8b-v04')
    monkeypatch.setattr(server,'_request',lambda *a,**k:{'answers':{'s':{'type':'score','expected':.4,'reject':.2}},'usage':{'latency_ms':123}})
    assert server._body({}, {'s':{}})['model']=='gutsy-0.8b-v04'
    result=server.kev_evaluate({}, {'s':{}})
    assert result['answers']['s']['score']==.4 and result['answers']['s']['reject']==.2
    assert result['latency_ms']==123


def test_tool_rejection_prevents_a_tool_suggestion(monkeypatch):
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:{'answers':{'tool':{'type':'choice','choice':'read',
        'probabilities':{'read':.9,'__no_tool__':.1},'reject':.7}}})
    result=server.kev_select_tool({}, {'read':{'description':'Read'}})
    assert result['suggested_tool'] is None and result['conditional_model_choice']=='read'


def test_trade_rejection_prevents_support(monkeypatch):
    from datetime import datetime,timezone
    monkeypatch.setattr(server,'kev_evaluate',lambda *a:{'answers':{'review':{'type':'choice','choice':'supports_proposal',
        'probabilities':{'supports_proposal':.8,'concerns':.1,'insufficient_information':.1},'reject':.7}}})
    result=server.kev_review_trade({'symbol':'TEST','source':'fixture','observed_at':datetime.now(timezone.utc).isoformat(),'features':{'synthetic':True}},
        {'symbol':'TEST','side':'long','rationale':'test','horizon_seconds':60},
        {'max_market_age_seconds':60,'rules':['paper only']})
    assert result['suggestion']=='insufficient_information'
    assert result['probabilities']['supports_proposal']==.8 and result['execution_authorized'] is False
