"""Paired fixed-case CPU Gutsy/GPU Kev comparison; labels are not trading outcomes."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import statistics
import time
from dotenv import load_dotenv
from kev_mcp_server import server

logging.getLogger('httpx').setLevel(logging.WARNING)
load_dotenv()
root=Path('benchmarks/private/project23')
data=(root/'cases.jsonl').read_bytes()
cases=[json.loads(line) for line in data.decode().splitlines()]
manifest=json.loads((root/'manifest.json').read_text())
assert hashlib.sha256(data).hexdigest()==manifest['dataset_sha256']
backends={'kev4b':('http://127.0.0.1:8008','kev','kev-latest'),
          'gutsy':('http://127.0.0.1:8009','gutsy','gutsy-0.8b-v04')}


def switch(name):
    url,backend,model=backends[name]
    os.environ['KEV_API_BASE_URL']=url
    os.environ['KEV_BACKEND']=backend
    os.environ['KEV_API_MODEL']=model


models={}
for name in backends:
    switch(name)
    models[name]=server.kev_list_models()
    server.kev_evaluate(cases[0]['state'],cases[0]['questions'])
rows=[]
for i,case in enumerate(cases):
    row={'id':case['id'],'split':case['split'],'target':case['expected']['action']}
    for name in (('kev4b','gutsy') if i%2==0 else ('gutsy','kev4b')):
        switch(name)
        start=time.perf_counter()
        try:
            answer=server.kev_evaluate(case['state'],case['questions'])['answers']['action']
            probs=answer['probabilities']
            assert set(probs)==set(case['questions']['action']['criteria'])
            assert all(type(p) in (int,float) and math.isfinite(p) and 0<=p<=1 for p in probs.values())
            assert abs(sum(probs.values())-1)<.02 and probs[answer['choice']]==max(probs.values())
            rejection=server._rejection_metadata(answer)
            decision='__reject__' if rejection.get('rejection_dominates') else answer['choice']
            row[name]={'choice':answer['choice'],'decision_with_rejection':decision,'probabilities':probs,
                       'ms':(time.perf_counter()-start)*1000,**rejection}
        except Exception as exc:
            row[name]={'error_type':type(exc).__name__}
    rows.append(row)
    if (i+1)%50==0:
        (root/'gutsy-comparison.partial.json').write_text(json.dumps(rows),encoding='utf-8')
        print(f'Completed {i+1}/{len(cases)} paired cases',flush=True)
summary={}
for split in ('dev','test'):
    summary[split]={}
    for name in backends:
        group=[r for r in rows if r['split']==split]
        good=[r for r in group if 'choice' in r[name]]
        accepted=[r for r in good if r[name]['decision_with_rejection']!='__reject__']
        summary[split][name]={'cases':len(group),'completed':len(good),'errors':len(group)-len(good),
            'conditional_label_agreement':sum(r[name]['choice']==r['target'] for r in good)/len(good) if good else None,
            'reject_count':len(good)-len(accepted),'accepted_count':len(accepted),
            'agreement_among_accepted':sum(r[name]['choice']==r['target'] for r in accepted)/len(accepted) if accepted else None,
            'correct_accepted_over_all':sum(r[name]['choice']==r['target'] for r in accepted)/len(group),
            'median_ms':statistics.median(r[name]['ms'] for r in good) if good else None,
            'p95_ms':sorted(r[name]['ms'] for r in good)[math.ceil(.95*len(good))-1] if good else None,
            'confusion_including_reject':dict(Counter(r['target']+' -> '+r[name]['decision_with_rejection'] for r in good)),
            'conditional_brier_sum_mean':statistics.mean(sum((p-(k==r['target']))**2 for k,p in r[name]['probabilities'].items()) for r in good) if good else None}
print(json.dumps(summary,indent=2),flush=True)
report={'created_at':datetime.now(timezone.utc).isoformat(),'summary':summary,'models':models,
        'dataset_sha256':hashlib.sha256(data).hexdigest(),'adapter_sha256':hashlib.sha256(Path(server.__file__).read_bytes()).hexdigest(),
        'rows':rows,'scope':'Same fixed cases/prompts; no tuning. Conditional scores exclude Gutsy rejection; accepted scores use largest unconditional mass including reject. No reject ground truth or trading outcomes. CPU 4 threads versus CUDA 4B; latency is not hardware-normalized.'}
(root/'gutsy-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
