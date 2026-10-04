"""Paired ToolSelect evaluation of the original choice prompt and actual shadow helper."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
from kev_mcp_server import server

logging.getLogger('httpx').setLevel(logging.WARNING)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('dataset')
parser.add_argument('--url', default='http://127.0.0.1:18008')
parser.add_argument('--output', required=True)
args = parser.parse_args()
os.environ['KEV_API_BASE_URL'] = args.url
raw = Path(args.dataset).read_bytes()
cases = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
if not cases or len({c['id'] for c in cases}) != len(cases):
    raise ValueError('Nonempty dataset with unique IDs required')
deadline = time.monotonic()+240
while True:
    try:
        headers = {'Authorization': 'Bearer '+os.environ['KEV_API_KEY']} if os.environ.get('KEV_API_KEY') else {}
        urllib.request.urlopen(urllib.request.Request(args.url+'/v1/models', headers=headers), timeout=5).close()
        break
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raise
        if time.monotonic() > deadline:
            raise
        time.sleep(2)
models = server.kev_list_models()
first = cases[0]
tools = {name: {'description': desc} for name, desc in first['questions']['tool']['criteria'].items()}
server.kev_evaluate(first['state'], first['questions'])
server.kev_select_tool(first['state'], tools)
rows, failures = [], []
for index, case in enumerate(cases):
    try:
        tools = {name: {'description': desc} for name, desc in case['questions']['tool']['criteria'].items()}
        target = case['expected']['tool']
        results, durations = {}, {}
        # Alternate request order to reduce systematic latency/caching advantage.
        for mode in (('baseline','shadow') if index % 2 == 0 else ('shadow','baseline')):
            started = time.perf_counter()
            results[mode] = server.kev_evaluate(case['state'], case['questions']) if mode == 'baseline' else server.kev_select_tool(case['state'], tools)
            durations[mode] = (time.perf_counter()-started)*1000
        shadow = results['shadow']
        assert shadow['executed'] is False and shadow['mode'] == 'shadow'
        baseline_choice = results['baseline']['answers']['tool']['choice']
        rows.append({'case_id':case['id'], 'target':target, 'baseline_choice':baseline_choice,
                     'shadow_choice':shadow['suggested_tool'], 'baseline_correct':baseline_choice == target,
                     'shadow_correct':shadow['suggested_tool'] == target,
                     'shadow_top_probability':shadow['top_probability'], 'durations_ms':durations})
    except Exception as exc:
        failures.append({'case_id':case['id'],'error_type':type(exc).__name__})
    if (index+1) % 100 == 0:
        print(f'Completed {index+1}/{len(cases)} pairs', flush=True)
summary = {'total_cases':len(cases),'complete_pairs':len(rows),'failures':failures,
           'baseline_correct':sum(r['baseline_correct'] for r in rows),
           'shadow_correct':sum(r['shadow_correct'] for r in rows),
           'regressions':sum(r['baseline_correct'] and not r['shadow_correct'] for r in rows),
           'improvements':sum(not r['baseline_correct'] and r['shadow_correct'] for r in rows),
           'no_tool_suggestions':sum(r['shadow_choice'] is None for r in rows),
           'median_ms':{mode:statistics.median(r['durations_ms'][mode] for r in rows) if rows else None for mode in ('baseline','shadow')}}
report = {'summary':summary, 'models':models,'dataset_sha256':hashlib.sha256(raw).hexdigest(),
          'adapter_sha256':hashlib.sha256(Path(server.__file__).read_bytes()).hexdigest(), 'rows':rows,
          'scope':'Paired exploratory ToolSelect training-corpus adaptation. Does not evaluate no-tool recall or authorization; no tools dispatched.'}
Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
if failures:
    raise SystemExit(1)
