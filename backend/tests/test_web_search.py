import asyncio
import json
from urllib.parse import parse_qs,urlsplit
import pytest
from fastapi.testclient import TestClient
import app as service
from funkbot import tools
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls,get_events


def configure(c):
    assert c.put('/api/settings/web-policy',json={'allow':['search.example.com','other.example.com'],'deny':[]}).status_code==200
    assert c.put('/api/settings/search-provider',json={'endpoint':'https://search.example.com/search'}).status_code==200


def test_search_configuration_auth_requires_allowed_public_https_and_no_secrets():
    with TestClient(service.app) as c:
        assert c.get('/api/settings/search-provider').status_code==401
        setup(c)
        assert c.put('/api/settings/search-provider',json={'endpoint':'https://search.example.com/search'}).status_code==400
        c.put('/api/settings/web-policy',json={'allow':['search.example.com'],'deny':[]})
        for url in ['http://search.example.com/search','https://search.example.com/search?key=x','https://user:pass@search.example.com/','https://127.0.0.1/search','https://search.example.com/#frag']:
            assert c.put('/api/settings/search-provider',json={'endpoint':url}).status_code==400,url
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com','key':'private-key-abcdefgh12345'})
        assert c.put('/api/settings/search-provider',json={'endpoint':'https://search.example.com/private-key-abcdefgh12345'}).status_code==400
        assert c.put('/api/settings/search-provider',json={'endpoint':'https://search.example.com/search'}).status_code==200
        assert c.get('/api/settings/search-provider').json()['endpoint']=='https://search.example.com/search'
        assert c.put('/api/settings/search-provider',json={'endpoint':''}).status_code==200


@pytest.mark.asyncio
async def test_searx_json_bounded_safe_encoding_and_invalid_response(monkeypatch):
    calls=[]
    async def fetch(args,allow,deny):
        calls.append(args.url)
        return {'content_type':'application/json','text':json.dumps({'results':[{'url':'javascript:alert(1)','title':'bad'}, {'url':'https://example.org/','title':'Good','content':'Untrusted info'},*({'url':f'https://example.org/{i}','title':'x'*500,'content':'y'*2000} for i in range(30))]})}
    monkeypatch.setattr(tools,'web_fetch',fetch)
    result=await tools.web_search(tools.WebSearchArgs(query='a & b ? hello',endpoint='https://search.example.com/search'),['search.example.com'],[])
    assert parse_qs(urlsplit(calls[0]).query)=={'q':['a & b ? hello'],'format':['json']}
    assert len(result['results'])==8 and result['results'][0]['title']=='Good' and len(result['results'][1]['title'])==300 and len(result['results'][1]['snippet'])==1000
    assert 'untrusted' in result['notice']
    async def invalid(*args): return {'content_type':'text/html','text':'<html>'}
    monkeypatch.setattr(tools,'web_fetch',invalid)
    with pytest.raises(tools.ToolError,match='JSON'): await tools.web_search(tools.WebSearchArgs(query='a',endpoint='https://search.example.com/search'),['search.example.com'],[])
    with pytest.raises(tools.ToolError,match='long'): await tools.web_search(tools.WebSearchArgs(query='😀'*500,endpoint='https://search.example.com/search'),['search.example.com'],[])


def test_search_approval_exact_query_each_time_and_audited(monkeypatch):
    calls=[];payloads=[]
    async def fetch(args,allow,deny):
        calls.append(args.url);return {'content_type':'application/json','text':json.dumps({'results':[{'title':'Page','url':'https://example.org','content':'Data'}]})}
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(tools,'web_fetch',fetch);monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    FakeClient.responses=[tool_reply('web_search',{'query':'actual query'}),final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);configure(c);bot=c.post('/api/bots',json={'name':'Researcher'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Search for a topic'}).json()['job_id'];call=until_calls(c,run)[0]
        assert any(t['function']['name']=='web_search' for t in payloads[0]['tools'])
        assert call['risk']=='send' and call['arguments']=={'query':'actual query','endpoint':'https://search.example.com/search'} and calls==[]
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==400
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(c,run)[-1]['type']=='done';call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='completed' and call['result']['results'][0]['title']=='Page' and len(calls)==1
        assert parse_qs(urlsplit(calls[0]).query)['q']==['actual query']
        assert 'actual query' in c.get('/api/tool-audit/export').text
        FakeClient.responses=[tool_reply('web_search',{'query':'another query'}),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Search again'}).json()['job_id'];call=until_calls(c,run)[0]
        assert call['status']=='pending';c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'deny'});get_events(c,run)
        assert len(calls)==1


@pytest.mark.parametrize('change',['endpoint','host-policy','tool-policy'])
def test_search_changed_endpoint_or_policy_never_sends(monkeypatch,change):
    async def never(*args): pytest.fail('search must not dispatch')
    monkeypatch.setattr(tools,'web_fetch',never);monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    FakeClient.responses=[tool_reply('web_search',{'query':'private question'}),final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);configure(c);bot=c.post('/api/bots',json={'name':'Researcher'}).json()['id'];run=c.post(f'/api/bots/{bot}/chat',json={'content':'Look it up'}).json()['job_id'];call=until_calls(c,run)[0]
        if change=='endpoint': c.put('/api/settings/search-provider',json={'endpoint':'https://other.example.com/search'})
        elif change=='host-policy': c.put('/api/settings/web-policy',json={'allow':['search.example.com'],'deny':['search.example.com']})
        else: c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'ask','create_followup':'ask','web_search':'deny'})
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'});get_events(c,run)
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0];assert call['status']=='denied' and any(a['action']=='policy_denied' for a in call['audit'])


@pytest.mark.asyncio
async def test_search_uses_pinned_https_transport_and_does_not_forward_private_dns(monkeypatch):
    import socket
    from test_tools_foundation import Writer
    loop=asyncio.get_running_loop();writer=Writer();calls=[]
    async def resolve(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
    async def connect(ip,port,**kwargs):
        calls.append((ip,port,kwargs));body=b'{"results":[{"url":"https://example.org","title":"Actual","content":"Fixture"}]}'
        reader=asyncio.StreamReader();reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body);reader.feed_eof();return reader,writer
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(asyncio,'open_connection',connect)
    result=await tools.web_search(tools.WebSearchArgs(query='safe words',endpoint='https://search.example.com/search'),['search.example.com'],[])
    assert result['results'][0]['title']=='Actual' and calls[0][0]=='93.184.216.34' and calls[0][2]['server_hostname']=='search.example.com'
    assert b'GET /search?q=safe+words&format=json HTTP/1.1' in writer.data
    async def mixed(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    monkeypatch.setattr(loop,'getaddrinfo',mixed)
    with pytest.raises(tools.ToolError,match='Private'): await tools.web_search(tools.WebSearchArgs(query='safe',endpoint='https://search.example.com/search'),['search.example.com'],[])
    assert len(calls)==1


def test_each_query_in_one_response_requires_individual_approval(monkeypatch):
    import time
    calls=[]
    async def fetch(args,allow,deny): calls.append(args.url);return {'content_type':'application/json','text':'{"results":[]}'}
    monkeypatch.setattr(tools,'web_fetch',fetch);monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    FakeClient.responses=[tool_reply('web_search',{'query':'first','endpoint':'https://evil.example.com/search'}),tool_reply('web_search',{'query':'second'}),final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);configure(c);bot=c.post('/api/bots',json={'name':'Researcher'}).json()['id'];run=c.post(f'/api/bots/{bot}/chat',json={'content':'Search twice'}).json()['job_id']
        first=until_calls(c,run)[0];assert first['arguments']['endpoint']=='https://search.example.com/search'
        c.post(f'/api/jobs/{run}/tool-calls/{first["id"]}/decision',json={'decision':'approve_once'})
        for _ in range(150):
            rows=c.get(f'/api/jobs/{run}/tool-calls').json()
            if len(rows)==2: break
            time.sleep(.02)
        else: pytest.fail('Second approval was not proposed')
        second=next(row for row in rows if row['id']!=first['id'])
        assert second['status']=='pending' and second['arguments']['query']=='second' and len(calls)==1
        c.post(f'/api/jobs/{run}/tool-calls/{second["id"]}/decision',json={'decision':'deny'});get_events(c,run);assert len(calls)==1
