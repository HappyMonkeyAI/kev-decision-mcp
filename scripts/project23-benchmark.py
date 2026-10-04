"""Build and optionally evaluate a private, deduplicated Project23 choice benchmark."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import logging
from pathlib import Path
import statistics
import time
from kev_mcp_server import server
logging.getLogger('httpx').setLevel(logging.WARNING)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(source, output):
    unique = {}
    duplicates = 0
    symbols = Counter()
    slices = defaultdict(Counter)
    excluded = Counter()
    for number, line in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
        record = json.loads(line)
        messages = record['messages']
        state = json.loads(next(m['content'] for m in messages if m['role'] == 'user').removeprefix('Market State: '))
        target = json.loads(next(m['content'] for m in messages if m['role'] == 'assistant'))
        actions = [k for k in target if k in ('execute_entry', 'trigger_circuit_breaker', 'set_regime_bias', 'close_position')]
        if len(actions) != 1 or actions[0] not in ('execute_entry', 'trigger_circuit_breaker'):
            excluded['unsupported_target'] += 1
            continue
        action = actions[0]
        if any(type(state.get(k)) not in (int,float) or not math.isfinite(state[k]) for k in ('adx','rsi','funding_rate')):
            excluded['non_finite_or_missing_market_measure'] += 1
            continue
        args = target[action]
        if action == 'execute_entry' and (args.get('symbol') != state.get('symbol') or args.get('side') not in ('long', 'short')):
            excluded['invalid_entry_symbol_or_side'] += 1
            continue
        if action == 'trigger_circuit_breaker' and args.get('reason') not in ('neutral_market', 'macro_velocity_crash', 'invalidated_setup'):
            excluded['unreviewed_abort_reason'] += 1
            continue
        identity = digest(state)
        if identity in unique:
            if unique[identity]['expected']['action'] != action:
                raise ValueError('Conflicting tool labels for identical state')
            duplicates += 1
            continue
        # Group identical/coarse market setups across symbols, including boundaries.
        group = dict(state)
        group.pop('symbol', None)
        for key in ('adx', 'rsi'):
            group[key] = round(float(group[key]) / 5) * 5
        group['funding_rate'] = 'positive' if state['funding_rate'] > 0 else 'negative' if state['funding_rate'] < 0 else 'zero'
        group_id = digest(group)
        split = 'dev' if int(group_id[:8], 16) % 2 == 0 else 'test'
        criteria = {'execute_entry': 'Choose this when the market context supports entering a directional trade.',
                    'trigger_circuit_breaker': 'Choose this when the setup is neutral, invalidated, or too risky; do not enter a trade.'}
        if int(identity[:2], 16) % 2:
            criteria = dict(reversed(list(criteria.items())))
        unique[identity] = {'id':identity, 'group_id':group_id, 'split':split, 'state':state,
                            'questions':{'action':{'type':'choice','instructions':'Select the appropriate next action from the market state. This is an offline classification task; do not place trades or generate arguments.', 'criteria':criteria}},
                            'expected':{'action':action}, 'source_line':number}
        symbols[state['symbol']] += 1
        slices['regime=' + state['regime']][action] += 1
        slices['ribbon=' + state['ema_ribbon']][action] += 1
        slices['pulse=' + state['macro_btc_pulse']][action] += 1
    selected = []
    for split in ('dev','test'):
        selected.extend(sorted((c for c in unique.values() if c['split'] == split), key=lambda c:digest(c['id']))[:200])
    output.mkdir(parents=True, exist_ok=True)
    dataset = output / 'cases.jsonl'
    dataset.write_text(''.join(json.dumps(c) + '\n' for c in selected), encoding='utf-8')
    dev = Counter(c['expected']['action'] for c in selected if c['split'] == 'dev')
    majority = dev.most_common(1)[0][0]
    manifest = {'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'dataset_sha256':hashlib.sha256(dataset.read_bytes()).hexdigest(),
                'unique_eligible':len(unique),'duplicates_removed':duplicates,'excluded':dict(excluded),
                'selected':len(selected),'split_counts':dict(Counter(c['split'] for c in selected)),
                'split_labels':{s:dict(Counter(c['expected']['action'] for c in selected if c['split']==s)) for s in ('dev','test')},
                'majority_from_dev':majority,'symbol_counts_unique':dict(symbols),'label_review_slices':{k:dict(v) for k,v in slices.items()},
                'scope':'Recorded-label agreement, not verified trading correctness. No chronological split or outcome validation. Group by coarse market setup across symbols; no group crosses splits. Select up to 200 cases per split deterministically, without label balancing. Targets and reasoning are never in API payloads.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return selected, manifest


def evaluate(cases, manifest, output, url):
    import os
    os.environ['KEV_API_BASE_URL'] = url
    models = server.kev_list_models()
    if 'kev-0.8b' not in json.dumps(models):
        raise RuntimeError('Endpoint does not report Kev 0.8B')
    server.kev_evaluate(cases[0]['state'], cases[0]['questions'])
    rows = []
    for i, case in enumerate(cases):
        start = time.perf_counter()
        try:
            answer = server.kev_evaluate(case['state'],case['questions'])['answers']['action']
            prediction = answer['choice']
            probabilities = answer['probabilities']
            if set(probabilities) != set(case['questions']['action']['criteria']) or abs(sum(probabilities.values())-1) > .02:
                raise ValueError('Invalid probabilities')
            rows.append({'id':case['id'],'split':case['split'],'target':case['expected']['action'],
                         'prediction':prediction,'probabilities':probabilities,'ms':(time.perf_counter()-start)*1000})
        except Exception as exc:
            rows.append({'id':case['id'],'split':case['split'],'error_type':type(exc).__name__})
        if (i+1)%50 == 0:
            print(f'Evaluated {i+1}/{len(cases)}',flush=True)
    summaries = {}
    for split in ('dev','test'):
        all_rows = [r for r in rows if r['split']==split]
        good = [r for r in all_rows if 'prediction' in r]
        summaries[split] = {'cases':len(all_rows),'completed':len(good),'errors':len(all_rows)-len(good),
                            'label_agreement':sum(r['prediction']==r['target'] for r in good)/len(good) if good else None,
                            'majority_agreement_same_cases':sum(r['target']==manifest['majority_from_dev'] for r in good)/len(good) if good else None,
                            'confusion':dict(Counter(r['target']+' -> '+r['prediction'] for r in good)),
                            'median_ms':statistics.median(r['ms'] for r in good) if good else None,
                            'brier_sum_mean':statistics.mean(sum((p-(k==r['target']))**2 for k,p in r['probabilities'].items()) for r in good) if good else None}
    report = {'summary':summaries,'models':models,'manifest':manifest,'rows':rows,
              'adapter_sha256':hashlib.sha256(Path(server.__file__).read_bytes()).hexdigest()}
    (output/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(summaries,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,default=Path('benchmarks/private/project23'))
    parser.add_argument('--url')
    args = parser.parse_args()
    cases, manifest = build(args.source,args.output)
    print(json.dumps({k:manifest[k] for k in ('unique_eligible','duplicates_removed','excluded','selected','split_counts','split_labels','majority_from_dev')},indent=2),flush=True)
    if args.url:
        evaluate(cases,manifest,args.output,args.url)
