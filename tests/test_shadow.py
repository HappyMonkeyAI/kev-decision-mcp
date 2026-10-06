import pytest
from kev_mcp_server import server

TOOLS = {'read_file': {'description': 'Read a local text file', 'parameters': {'type': 'object'}}}


def answer(choice='read_file', probabilities=None):
    return {'answers': {'tool': {'type': 'choice', 'choice': choice,
            'probabilities': probabilities or {'read_file': .9, '__no_tool__': .1}, 'confidence': .2}}}


def test_shadow_calls_only_decision_endpoint_and_preserves_context(monkeypatch):
    calls = []
    def request(method, path, *, payload):
        calls.append((method, path, payload))
        return answer()
    monkeypatch.setattr(server, '_request', request)
    state = {'user_request': 'Read README', 'context': 'Current project is available'}
    result = server.kev_select_tool(state, TOOLS)
    assert result['mode'] == 'shadow' and result['executed'] is False
    assert result['suggested_tool'] == 'read_file' and result['top_probability'] == .9
    assert 'arguments' not in result and 'confidence' not in result
    assert len(calls) == 1 and calls[0][:2] == ('POST', '/v1/systemone')
    assert calls[0][2]['state'] == state
    assert calls[0][2]['questions']['tool']['criteria']['read_file'] == TOOLS['read_file']


def test_shadow_can_suggest_no_tool(monkeypatch):
    monkeypatch.setattr(server, 'kev_evaluate', lambda *args: answer('__no_tool__', {'read_file': .1, '__no_tool__': .9}))
    result = server.kev_select_tool('Hello', TOOLS)
    assert result['suggested_tool'] is None and result['executed'] is False


@pytest.mark.parametrize('tools', [{}, {'__no_tool__': {'description': 'Reserved'}},
    {'': {'description': 'Empty name'}}, {'read': {}}, {'read': {'description': ' '}},
    {'read': {'description': 'Read', 'parameters': []}},
    {str(i): {'description': 'Tool'} for i in range(255)}])
def test_bad_definitions_do_not_reach_network(monkeypatch, tools):
    monkeypatch.setattr(server, '_request', lambda *args, **kwargs: pytest.fail('Network should not be called'))
    with pytest.raises(ValueError):
        server.kev_select_tool('state', tools)


@pytest.mark.parametrize('result', [{}, {'answers': []}, {'answers': {'tool': {'type': 'score'}}},
    answer('missing'), answer(probabilities={'read_file': .9}),
    answer(probabilities={'read_file': 1.1, '__no_tool__': -.1}),
    answer(probabilities={'read_file': .8, '__no_tool__': .8}),
    answer(probabilities={'read_file': .1, '__no_tool__': .9}),
    answer(probabilities={'read_file': True, '__no_tool__': 0}),
    answer(probabilities={'read_file': float('nan'), '__no_tool__': .1})])
def test_malformed_answers_are_errors(monkeypatch, result):
    monkeypatch.setattr(server, 'kev_evaluate', lambda *args: result)
    with pytest.raises(RuntimeError):
        server.kev_select_tool('state', TOOLS)
