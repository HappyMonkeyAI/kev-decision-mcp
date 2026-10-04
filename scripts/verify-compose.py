"""Run inside the MCP container; report checks without printing credentials."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    url='http://localhost:8765/mcp'
    token=os.environ.get('KEV_MCP_AUTH_TOKEN','').strip()
    unauthenticated_status=None
    if token:
        async with httpx.AsyncClient() as client:
            response=await client.get(url)
            assert response.status_code==401
            unauthenticated_status=response.status_code
    headers={'Authorization':'Bearer '+token} if token else {}
    async with httpx.AsyncClient(headers=headers) as client:
        async with streamable_http_client(url,http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert 'kev_review_trade' in {t.name for t in tools.tools}
                models=await session.call_tool('kev_list_models',{})
                assert not models.isError
                now=datetime.now(timezone.utc)
                market={'symbol':'PAPER_TEST','source':'synthetic installation fixture',
                        'observed_at':now.isoformat(),'features':{'synthetic':True}}
                proposal={'symbol':'PAPER_TEST','side':'long','rationale':'Installation test, no live instrument', 'horizon_seconds':60}
                risk={'max_market_age_seconds':120,'rules':['Simulation only; missing real market facts means insufficient information']}
                def arguments(): return {'market_context':market,'proposed_trade':proposal,'risk_constraints':risk}
                missing=await session.call_tool('kev_review_trade',{'market_context':{},'proposed_trade':{},'risk_constraints':{}})
                assert not missing.isError and 'missing_required_context' in str(missing)
                market['observed_at']=(now-timedelta(hours=1)).isoformat()
                stale=await session.call_tool('kev_review_trade',arguments())
                assert not stale.isError and 'stale_market_context' in str(stale)
                market['observed_at']=now.isoformat()
                live=await session.call_tool('kev_review_trade',arguments())
                assert not live.isError
                print(json.dumps({'mcp_authentication_enabled':bool(token),'unauthenticated_status':unauthenticated_status,'trade_tool_discovered':True,
                                  'model_listing':models.structuredContent,'missing_context_check':'passed',
                                  'stale_context_check':'passed','synthetic_live_review':live.structuredContent}),flush=True)


asyncio.run(main())
