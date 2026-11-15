"""Disposable browser test backend. Never run on a real Funk Bot workspace.

This substitutes the external MCP service only; the production network policy
is independently tested in test_connectors.py and is NOT disabled by the app.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
import app

async def list_tools(url,token):
    if url!='https://example.com/mcp' or token!='fixture-connector-secret': raise ValueError('Invalid fixture configuration')
    return [{'name':'send_message','description':'Send a fixture message','input_schema':{'type':'object','properties':{'text':{'type':'string'}}}}]

async def call_tool(url,token,name,args):
    if (url,token,name,args)!=('https://example.com/mcp','fixture-connector-secret','send_message',{'text':'Hello fixture'}): raise ValueError('Invalid fixture call')
    return {'content':[{'type':'text','text':'Fixture connector delivered the message.'}]}

app.mcp_http.list_tools=list_tools
app.mcp_http.call_tool=call_tool
uvicorn.run(app.app,host='0.0.0.0',port=8040)
