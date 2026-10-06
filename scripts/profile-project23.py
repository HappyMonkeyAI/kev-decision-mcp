"""Read-only profile of Project23 chat datasets; outputs aggregate metadata only."""
import collections
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
profiles = []
for path in sorted((root / 'trade_data').glob('*.jsonl')):
    labels = collections.Counter()
    reasons = collections.Counter()
    states = collections.defaultdict(set)
    keys = collections.Counter()
    rows = malformed = invalid_targets = timestamps = state_rows = 0
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        rows += 1
        try:
            record = json.loads(line)
            messages = record['messages']
            user = next(m['content'] for m in messages if m['role'] == 'user')
            answer = next(m['content'] for m in messages if m['role'] == 'assistant')
        except (ValueError, KeyError, StopIteration, TypeError):
            malformed += 1
            continue
        state = None
        if user.startswith('Market State: '):
            try:
                state = json.loads(user[len('Market State: '):])
                state_rows += 1
                keys.update(state.keys())
                timestamps += any(k.lower() in ('timestamp', 'time', 'date', 'datetime', 'created_at', 'observed_at', 'decision_at') or k.lower().endswith('_timestamp') for k in state)
            except ValueError:
                pass
        try:
            target = json.loads(answer)
            tools = [k for k in target if k in ('execute_entry', 'trigger_circuit_breaker', 'set_regime_bias', 'close_position')]
            label = tools[0] if len(tools) == 1 else target.get('outcome', 'unclassified')
            if label == 'trigger_circuit_breaker':
                reasons.update([str(target[label].get('reason'))])
        except (ValueError, TypeError, AttributeError):
            invalid_targets += 1
            label = 'non_json_answer'
        labels.update([label])
        if state is not None:
            states[json.dumps(state, sort_keys=True)].add(label)
    profiles.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'rows': rows, 'malformed_records': malformed, 'non_json_answers': invalid_targets,
                     'labels': dict(labels), 'circuit_breaker_reasons': dict(reasons),
                     'state_fields': dict(keys), 'timestamped_states': timestamps,
                     'unique_states': len(states),
                     'repeated_states': state_rows - len(states),
                     'conflicting_state_labels': sum(len(v) > 1 for v in states.values())})
print(json.dumps(profiles, indent=2))
