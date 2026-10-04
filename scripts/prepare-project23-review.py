"""Create a private development-only, varied label-review queue; no labels approved."""
from collections import defaultdict
import json
from pathlib import Path

root = Path('benchmarks/private/project23')
cases = [json.loads(line) for line in (root/'cases.jsonl').read_text().splitlines()]
strata = defaultdict(list)
for case in cases:
    if case['split'] == 'dev':
        strata[(case['expected']['action'],case['state']['regime'],case['state']['macro_btc_pulse'])].append(case)
selected = []
while strata and len(selected) < 20:
    for key in sorted(list(strata)):
        selected.append(strata[key].pop(0))
        if not strata[key]:
            del strata[key]
        if len(selected) == 20:
            break
destination = root/'label-review.jsonl'
if destination.exists():
    raise SystemExit('Review file exists; refusing to overwrite human annotations')
destination.write_text(''.join(json.dumps({'id':c['id'],'state':c['state'],
    'recorded_action':c['expected']['action'],'split':'dev','review_status':'pending',
    'reviewed_action':None,'rule_evidence':None,'missing_information':[],
    'review_question':'Is the recorded action justified by explicit project rules using only this state? Unknown is allowed. No realised trading outcome is supplied.'})+'\n' for c in selected),encoding='utf-8')
print(f'Prepared {len(selected)} pending development reviews')
