import json
import time
import pytest
from fastapi.testclient import TestClient
import app as service
from funkbot import mcp_http
from funkbot.tools import ToolError
from test_app import setup,configure_budget,FakeClient,FakeStream
from test_live_tools import final_reply,until_calls,get_events


def call_reply(connector,tool='send_message',args='{}'):
    invocation={'connector_id':connector,'tool_name':tool,'arguments_json':args,'endpoint':'https://forged.invalid','connector_revision':'forged'}
    chunks=[{'choices':[{'delta':{'tool_calls':[{'index':0,'id':'mcp-1','function':{'name':'mcp_call','arguments':json.dumps(invocation)}}]},'finish_reason':'tool_calls'}]}, {'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}}]
    return FakeStream(200,['data: '+json.dumps(chunk) for chunk in chunks]+['data: [DONE]'])


def test_connector_config_redaction_and_authenticated_test(monkeypatch):
    calls=[]
    async def mock_list(url,token): calls.append((url,token));return [{'name':'send_message','description':'secret-connector-value-12345'}]
    monkeypatch.setattr(mcp_http,'list_tools',mock_list)
    with TestClient(service.app) as c:
        assert c.get('/api/connectors').status_code==401
        setup(c)
        assert c.put('/api/connectors/new',json={'name':'Local','url':'http://127.0.0.1:3000'}).status_code==400
        assert c.put('/api/connectors/new',json={'name':'Bad','url':'https://example.com/mcp?key=bad'}).status_code==400
        assert c.put('/api/connectors/new',json={'name':'Bad','url':'https://example.com/mcp','allowed_tools':['../bad']}).status_code==400
        token='secret-connector-value-12345'
        body={'name':'Messages','url':'https://example.com/mcp','key':token,'enabled':True,'allowed_tools':['send_message']}
        connector=c.put('/api/connectors/new',json=body).json()['id']
        assert token not in service.config('mcp_connectors') and token not in c.get('/api/connectors').text
        result=c.post(f'/api/connectors/{connector}/test');assert result.status_code==200 and token not in result.text
        assert calls==[('https://example.com/mcp',token)]
        assert c.delete(f'/api/connectors/{connector}').status_code==200


def test_mcp_tool_is_exactly_reviewed_and_never_run_granted(monkeypatch):
    calls=[];payloads=[]
    async def mock_call(url,token,name,args): calls.append((url,token,name,args));return {'content':[{'type':'text','text':'server-result'}]}
    class Client(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Client);monkeypatch.setattr(mcp_http,'call_tool',mock_call)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        token='connector-secret-value-12345'
        connector=c.put('/api/connectors/new',json={'name':'Messages','url':'https://example.com/mcp','key':token,'enabled':True,'allowed_tools':['send_message']}).json()['id']
        FakeClient.responses=[call_reply(connector,args=json.dumps({'text':'hello','nested':{'key':token}})),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Send a message'}).json()['job_id']
        call=until_calls(c,run)[0];assert call['status']=='pending' and not calls
        assert call['arguments']['endpoint']=='https://example.com/mcp' and call['arguments']['connector_revision']!='forged'
        assert token not in json.dumps(call) and '[redacted]' in call['arguments']['arguments_json']
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==400
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(c,run)[-1]['type']=='done'
        assert calls==[('https://example.com/mcp',token,'send_message',{'text':'hello','nested':{'key':'[redacted]'}})]
        assert connector in payloads[0]['messages'][0]['content'] and token not in json.dumps(payloads)
        audit=c.get(f'/api/jobs/{run}/tool-calls').json()[0];assert audit['status']=='completed' and any(a['action']=='started' for a in audit['audit'])


def test_connector_allowlist_and_policy_change_block_call(monkeypatch):
    calls=[]
    async def mock_call(*args): calls.append(args);return {}
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient);monkeypatch.setattr(mcp_http,'call_tool',mock_call)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        body={'name':'Messages','url':'https://example.com/mcp','enabled':True,'allowed_tools':['send_message']}
        connector=c.put('/api/connectors/new',json=body).json()['id']
        FakeClient.responses=[call_reply(connector,'unknown'),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Do it'}).json()['job_id'];get_events(c,run)
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='denied' and not calls
        FakeClient.responses=[call_reply(connector),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Do it'}).json()['job_id'];call=until_calls(c,run)[0]
        body['url']='https://example.org/mcp';assert c.put(f'/api/connectors/{connector}',json=body).status_code==200
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'});get_events(c,run)
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='denied' and not calls


@pytest.mark.asyncio
async def test_mcp_exchange_protocol_and_private_network_rejection(monkeypatch):
    calls=[]
    async def fake_request(url,token,payload,session_id=None,protocol_version=None):
        calls.append((url,token,payload,session_id,protocol_version))
        if payload['method']=='initialize': return json.dumps({'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2025-03-26'}}).encode(),{'mcp-session-id':'session-1'}
        if payload['method']=='notifications/initialized': return b'',{}
        return json.dumps({'jsonrpc':'2.0','id':2,'result':{'tools':[{'name':'read','description':'Useful'}]}}).encode(),{}
    monkeypatch.setattr(mcp_http,'request',fake_request)
    tools=await mcp_http.list_tools('https://example.com/mcp','token')
    assert tools==[{'name':'read','description':'Useful','input_schema':{}}]
    assert calls[1][3:] == ('session-1','2025-03-26') and calls[2][2]['method']=='tools/list'
    for url in ('http://127.0.0.1/mcp','https://127.0.0.1/mcp','https://localhost/mcp','https://user:pass@example.com/mcp'):
        with pytest.raises(ToolError): mcp_http.validate_endpoint(url)


@pytest.mark.asyncio
async def test_connector_dns_mixed_private_answers_are_blocked_before_connect(monkeypatch):
    import asyncio,socket
    loop=asyncio.get_running_loop();called=[]
    async def resolve(*args,**kwargs):
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    async def connect(*args,**kwargs): called.append(args);raise AssertionError('private DNS must never connect')
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(asyncio,'open_connection',connect)
    with pytest.raises(ToolError,match='Private'): await mcp_http._request('https://example.com/mcp','',{'jsonrpc':'2.0'})
    assert not called


def test_two_connector_calls_require_two_decisions(monkeypatch):
    calls=[]
    async def mock_call(*args): calls.append(args);return {'content':[]}
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient);monkeypatch.setattr(mcp_http,'call_tool',mock_call)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        connector=c.put('/api/connectors/new',json={'name':'Messages','url':'https://example.com/mcp','enabled':True,'allowed_tools':['send_message']}).json()['id']
        FakeClient.responses=[call_reply(connector),call_reply(connector),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Send two messages'}).json()['job_id']
        first=until_calls(c,run)[0];c.post(f'/api/jobs/{run}/tool-calls/{first["id"]}/decision',json={'decision':'approve_once'})
        for _ in range(150):
            found=c.get(f'/api/jobs/{run}/tool-calls').json()
            if len(found)==2 and found[1]['status']=='pending': break
            time.sleep(.02)
        else: raise AssertionError(found)
        assert len(calls)==1
        c.post(f'/api/jobs/{run}/tool-calls/{found[1]["id"]}/decision',json={'decision':'deny'});get_events(c,run)
        assert len(calls)==1 and c.get(f'/api/jobs/{run}/tool-calls').json()[1]['status']=='denied'


@pytest.mark.asyncio
@pytest.mark.parametrize('streamed',[False,True])
async def test_real_https_wire_protocol_with_fixture_ca_and_pinned_address(tmp_path,monkeypatch,streamed):
    import asyncio,datetime,ipaddress,socket,ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'example.com')])
    cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)).not_valid_after(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('example.com')]),critical=False).sign(key,hashes.SHA256()))
    certfile=tmp_path/'cert.pem';keyfile=tmp_path/'key.pem'
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM));keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()))
    serverctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);serverctx.load_cert_chain(certfile,keyfile)
    clientctx=ssl.create_default_context(cafile=str(certfile));received=[]
    async def handler(reader,writer):
        import h11
        conn=h11.Connection(h11.SERVER);body=bytearray();headers={}
        while True:
            event=conn.next_event()
            if event is h11.NEED_DATA: conn.receive_data(await reader.read(8192));continue
            if isinstance(event,h11.Request): headers=dict(event.headers)
            elif isinstance(event,h11.Data): body.extend(event.data)
            elif isinstance(event,h11.EndOfMessage): break
        payload=json.loads(body);received.append((headers,payload))
        if payload['method']=='initialize': reply={'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2025-03-26'}};status=200
        elif payload['method']=='notifications/initialized': reply=None;status=202
        else: reply={'jsonrpc':'2.0','id':2,'result':{'content':[{'type':'text','text':'ok'}]}};status=200
        output=json.dumps(reply).encode() if reply else b''
        hdr=[('Content-Type','text/event-stream' if streamed and reply else 'application/json'),('Connection','close')]
        if payload['method']=='initialize': hdr.append(('Mcp-Session-Id','fixture-session'))
        if streamed and reply:
            # Hold the stream open after the matching frame: the client must
            # finish on the response rather than waiting for connection EOF.
            output=b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r\n'+b'data: '+output+b'\r\n\r\n'
            writer.write(conn.send(h11.Response(status_code=status,headers=hdr)))
            for chunk in (output[:13],output[13:37],output[37:]):
                writer.write(conn.send(h11.Data(data=chunk)));await writer.drain();await asyncio.sleep(0)
            await reader.read()
        else:
            hdr.append(('Content-Length',str(len(output))))
            writer.write(conn.send(h11.Response(status_code=status,headers=hdr))+conn.send(h11.Data(data=output))+conn.send(h11.EndOfMessage()));await writer.drain()
        writer.close();await writer.wait_closed()
    server=await asyncio.start_server(handler,'127.0.0.1',0,ssl=serverctx);port=server.sockets[0].getsockname()[1];loop=asyncio.get_running_loop()
    async def resolve(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',port))]
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(mcp_http,'public_address',lambda address:True);monkeypatch.setattr(mcp_http.ssl,'create_default_context',lambda:clientctx)
    try:
        result=await mcp_http.call_tool(f'https://example.com:{port}/mcp','fixture-token','send_message',{'text':'hello'})
        assert result['content'][0]['text']=='ok' and len(received)==3
        assert received[2][0][b'authorization']==b'Bearer fixture-token'
        assert received[2][0][b'mcp-session-id']==b'fixture-session'
        assert received[2][0][b'mcp-protocol-version']==b'2025-03-26'
        assert received[2][1]['params']=={'name':'send_message','arguments':{'text':'hello'}}
    finally: server.close();await server.wait_closed()


def test_connector_endpoint_change_needs_credential_decision():
    with TestClient(service.app) as c:
        setup(c)
        body={'name':'Messages','url':'https://example.com/mcp','key':'old-token-secret','enabled':True,'allowed_tools':['send_message']}
        connector=c.put('/api/connectors/new',json=body).json()['id']
        body.update(url='https://example.org/mcp',key='')
        assert c.put(f'/api/connectors/{connector}',json=body).status_code==400
        body['clear_key']=True
        assert c.put(f'/api/connectors/{connector}',json=body).status_code==200
        assert not c.get('/api/connectors').json()[0]['has_key']


def test_bounded_sse_parser_handles_partial_frames_and_rejects_server_requests():
    parser=mcp_http._SSEReply(2)
    assert parser.feed(b': heartbeat\r\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r') is None
    assert parser.feed(b'\ndata: {"jsonrpc":"2.0",\n') is None
    reply=parser.feed(b'data: "id":2,"result":{"content":[]}}\n\n')
    assert mcp_http.parse_rpc(reply,2)=={'content':[]}
    assert mcp_http.parse_rpc(mcp_http._SSEReply(2).feed(b'data: {\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{}}\r\r'),2)=={}
    with pytest.raises(ToolError,match='ID'):
        mcp_http._SSEReply(1).feed(b'data: {\"jsonrpc\":\"2.0\",\"id\":true,\"result\":{}}\n\n')
    with pytest.raises(ToolError,match='server requests'):
        mcp_http._SSEReply(2).feed(b'data: {"jsonrpc":"2.0","id":3,"method":"do_something"}\n\n')
    with pytest.raises(ToolError,match='ID'):
        mcp_http._SSEReply(2).feed(b'data: {"jsonrpc":"2.0","id":4,"result":{}}\n\n')
    with pytest.raises(ToolError,match='large'):
        mcp_http._SSEReply(2).feed(b'a'*(mcp_http.MAX_RESPONSE+1))
    with pytest.raises(ToolError,match='Invalid'):
        mcp_http._SSEReply(2).feed(b'data: not-json\n\n')
    with pytest.raises(ToolError,match='Unexpected'):
        mcp_http._SSEReply(None)
