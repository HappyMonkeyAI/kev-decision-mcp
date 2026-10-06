"""Synthetic missing-evidence smoke fixtures, not trading performance tests."""
from datetime import datetime,timezone
import json
from pathlib import Path
import os
from dotenv import load_dotenv
from kev_mcp_server import server

load_dotenv()
fixtures=[('missing_spread',{'price':100,'spread_bps':None},'Assessment requires a measured spread; absent evidence means insufficient information.'),
          ('missing_exposure',{'price':100,'account_exposure_quote':None},'Assessment requires current account exposure; absent evidence means insufficient information.'),
          ('missing_costs',{'price':100,'fees_and_slippage_quote':None},'Assessment requires fees and slippage estimates; absent evidence means insufficient information.')]
rows=[]
for name,features,rule in fixtures:
    for backend,url,model in [('kev','http://127.0.0.1:8008','kev-latest'),('gutsy','http://127.0.0.1:8009','gutsy-0.8b-v04')]:
        os.environ['KEV_BACKEND']=backend
        os.environ['KEV_API_BASE_URL']=url
        os.environ['KEV_API_MODEL']=model
        result=server.kev_review_trade({'symbol':'PAPER_TEST','source':'synthetic incomplete evidence fixture',
            'observed_at':datetime.now(timezone.utc).isoformat(),'features':features},
            {'symbol':'PAPER_TEST','side':'long','rationale':'Installation comparison only, no tradable instrument','horizon_seconds':60},
            {'max_market_age_seconds':60,'rules':[rule,'No orders; simulation only.']})
        rows.append({'fixture':name,'backend':backend,'expected':'insufficient_information','result':result})
root=Path('benchmarks/private/project23')
(root/'gutsy-missing-evidence.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps([{'fixture':r['fixture'],'backend':r['backend'],'suggestion':r['result']['suggestion'],
                   'reject':r['result'].get('rejection_probability')} for r in rows],indent=2))
