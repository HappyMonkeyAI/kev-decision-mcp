import importlib.util
import json
from pathlib import Path
import tempfile
import pytest

spec = importlib.util.spec_from_file_location('project23_benchmark', Path(__file__).parents[1]/'scripts/project23-benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def record(i, symbol='BTC', invalid=False):
    state = {'symbol':symbol,'regime':'Trending','adx':float('nan') if invalid else i,
             'rsi':50,'ema_ribbon':'bullish_expansion','funding_rate':.001,
             'macro_btc_pulse':'normal','social_sentiment':'neutral','strategy_directives':[]}
    return {'messages':[{'role':'user','content':'Market State: '+json.dumps(state)},
                        {'role':'assistant','content':json.dumps({'thought':'SECRET_TARGET_TEXT','execute_entry':{'symbol':symbol,'side':'long'}})}]}


def test_dedup_invalid_data_and_input_separation():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = [record(i) for i in range(40)] + [record(0),record(9,invalid=True)]
        source=root/'source.jsonl'
        source.write_text(''.join(json.dumps(r)+'\n' for r in data))
        cases,manifest=benchmark.build(source,root/'output')
        assert manifest['duplicates_removed']==1
        assert manifest['excluded']['non_finite_or_missing_market_measure']==1
        assert len(cases)==40
        for case in cases:
            assert 'SECRET_TARGET_TEXT' not in json.dumps({'state':case['state'],'questions':case['questions']})


def test_cross_symbol_group_stays_in_one_split():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        source=root/'source.jsonl'
        source.write_text(''.join(json.dumps(record(i,symbol))+'\n' for i in range(40) for symbol in ('BTC','ETH')))
        cases,_=benchmark.build(source,root/'output')
        groups={}
        for case in cases:
            groups.setdefault(case['group_id'],set()).add(case['split'])
        assert all(len(splits)==1 for splits in groups.values())


def test_conflicting_identical_states_rejected():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        original=record(10)
        conflict=record(10)
        conflict['messages'][-1]['content']=json.dumps({'trigger_circuit_breaker':{'reason':'neutral_market'}})
        source=root/'source.jsonl'
        source.write_text(json.dumps(original)+'\n'+json.dumps(conflict)+'\n')
        with pytest.raises(ValueError,match='Conflicting'):
            benchmark.build(source,root/'output')
