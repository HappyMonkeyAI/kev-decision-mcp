"""Verify actual stdio MCP discovery without calling the Kev endpoint."""
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parameters = StdioServerParameters(command=sys.executable, args=['-m','kev_mcp_server.server'])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next(t for t in tools.tools if t.name == 'kev_review_trade')
            required = tool.inputSchema['required']
            assert set(required) == {'market_context','proposed_trade','risk_constraints'}
            print(json.dumps({'tool':tool.name,'required':required,'discovered':True}))


asyncio.run(main())
