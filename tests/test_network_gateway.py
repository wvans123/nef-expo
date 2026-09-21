"""Internal caller -> NEF -> real local AF MCP; published URLs never bypass NEF."""
import json
import pytest
from test_network_registry import (
    client, clean_state, http_fixture, configure, headers, register_server,
    json_response, MCP_PROTOCOL_VERSION,
)


def provision(client, http_fixture, monkeypatch, *, tool_error=False, publish_service=True):
    monkeypatch.setenv("TEST_AF_TOKEN", "af-only-secret")
    monkeypatch.setenv("TEST_NW_TOKEN", "network-only-secret")
    calls=[]
    schema={"type":"object","properties":{"frame":{"type":"string"}},"required":["frame"],"additionalProperties":False}
    tool={"name":"inspect_frame","description":"Inspect a frame","inputSchema":schema,
          "annotations":{"readOnlyHint":True}}
    def af(request):
        message=json.loads(request['body']);calls.append((message,request['headers']))
        assert request['headers'].get('authorization')=='Bearer af-only-secret'
        if message['method']=='initialize':
            status,hs,body=json_response({'jsonrpc':'2.0','id':message['id'],'result':{
                'protocolVersion':MCP_PROTOCOL_VERSION,'capabilities':{'tools':{}},
                'serverInfo':{'name':'AF-vision','version':'1.0'}}})
            return status,{**hs,'Mcp-Session-Id':'af-session'},body
        assert request['headers'].get('mcp-session-id')=='af-session'
        if message['method']=='notifications/initialized':return 202,{},b''
        if message['method']=='tools/list':result={'tools':[tool]}
        elif message['method']=='tools/call':result={'content':[{'type':'text','text':'AF result: '+message['params']['arguments']['frame']}],'isError':tool_error}
        else:raise AssertionError('unexpected AF method')
        return json_response({'jsonrpc':'2.0','id':message['id'],'result':result})
    http_fixture.add('POST','/af',af)
    published=[]
    def publish(request):
        published.append(json.loads(request['body']));return json_response({'accepted':True})
    http_fixture.add('POST','/publish',publish)
    cfg=configure(monkeypatch,publish_url=http_fixture.url('/publish'),
        mcp_servers={http_fixture.url('/af'):{'token_env':'TEST_AF_TOKEN'}})
    cfg['network_clients']={'nw-agent':{'token_env':'TEST_NW_TOKEN','af_accounts':['account-a']}}
    monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    server=register_server(client,http_fixture.url('/af'))
    result=client.post('/api/v1/network/servers/'+server['id']+'/discover',headers=headers())
    assert result.status_code==200, result.text
    path=result.json()['gateway_path']
    if publish_service:
        assert client.post('/api/v1/network/servers/'+server['id']+'/publish',headers=headers()).status_code==200
    return server,path,cfg,tool,calls,published


def rpc(client,path,method,params=None,key='network-only-secret',rid=7):
    return client.post(path,headers={'Authorization':'Bearer '+key},json={
        'jsonrpc':'2.0','id':rid,'method':method,'params':params or {}})


def test_publication_advertises_nef_not_af(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,published=provision(client,http_fixture,monkeypatch)
    result=client.post('/api/v1/network/servers/'+server['id']+'/sync',headers={**headers(),'Host':'attacker.invalid'})
    assert result.status_code==200 and result.json()['sync_status']=='synced'
    payload=published[0]
    assert payload['source']=='AF' and payload['source_account']=='account-a'
    assert payload['registration_id']==server['id']
    assert payload['server']['url']=='http://nef.test:8069'+path
    assert payload['server']['access_via']=='NEF'
    assert payload['server']['origin_server_info']=={'name':'AF-vision','version':'1.0'}
    assert payload['server']['tools']==[tool]
    text=json.dumps(payload)
    assert http_fixture.url('/af') not in text and 'attacker.invalid' not in text
    assert 'af-only-secret' not in text and 'network-only-secret' not in text
    assert payload['server']['serverInfo']['name']=='nef-af-'+server['id']


@pytest.mark.parametrize('tool_error',[False,True])
def test_gateway_preserves_af_result_session_schema_and_separates_keys(client,http_fixture,monkeypatch,tool_error):
    server,path,cfg,tool,calls,_=provision(client,http_fixture,monkeypatch,tool_error=tool_error)
    assert rpc(client,path,'initialize',{'protocolVersion':MCP_PROTOCOL_VERSION}).json()['result']['capabilities']=={'tools':{}}
    assert client.post(path,headers={'Authorization':'Bearer network-only-secret'},json={'jsonrpc':'2.0','method':'notifications/initialized'}).status_code==202
    assert rpc(client,path,'tools/list').json()['result']['tools']==[tool]
    before=len(calls)
    response=rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{'frame':'frame-01'}},rid='nw-123')
    assert response.json()=={'jsonrpc':'2.0','id':'nw-123','result':{'content':[{'type':'text','text':'AF result: frame-01'}],'isError':tool_error}}
    assert [m['method'] for m,h in calls[before:]]==['initialize','notifications/initialized','tools/call']
    assert all(h['authorization']=='Bearer af-only-secret' for m,h in calls)
    stored=client.get('/api/v1/network/servers',headers=headers()).json()['servers'][0]
    assert stored['last_call']['status']==('tool_error' if tool_error else 'returned')
    assert stored['last_call']['caller']=='nw-agent' and stored['last_call']['via']=='NEF'
    assert stored['last_call']['elapsed_ms']>=0
    assert 'arguments' not in stored['last_call'] and 'frame-01' not in json.dumps(stored)


def test_gateway_auth_revocation_validation_and_notifications_fail_closed(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,_=provision(client,http_fixture,monkeypatch)
    before=len(calls)
    for key in ['caller-a','af-only-secret','bad']:
        assert rpc(client,path,'tools/list',key=key).status_code==401
    bad=rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{'frame':2}})
    assert bad.json()['error']['code']==-32602
    assert rpc(client,path,'tools/call',{'name':'unknown'}).json()['error']['code']==-32602
    assert rpc(client,path,'unknown').json()['error']['code']==-32601
    assert client.post(path,headers={'Authorization':'Bearer network-only-secret'},json={'jsonrpc':'2.0','method':'tools/call','params':{'name':'inspect_frame','arguments':{'frame':'never'}}}).status_code==202
    assert len(calls)==before
    cfg['network_clients']['nw-agent']['af_accounts']=['account-b']
    monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    assert rpc(client,path,'tools/list').status_code==404
    cfg['network_clients']['nw-agent']['af_accounts']=['account-a'];cfg['mcp_servers']={}
    monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    assert rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{'frame':'no'}}).status_code==403
    assert len(calls)==before


def test_missing_af_secret_never_degrades_to_anonymous(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,_=provision(client,http_fixture,monkeypatch)
    before=len(calls);monkeypatch.delenv('TEST_AF_TOKEN')
    result=rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{'frame':'no'}})
    assert result.json()['error']['code']==-32002
    assert len(calls)==before


def test_publication_requires_operator_nef_endpoint(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,published=provision(client,http_fixture,monkeypatch,publish_service=False)
    cfg['nef_base_url']=None;monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    result=client.post('/api/v1/network/servers/'+server['id']+'/sync',headers=headers())
    assert result.status_code==200 and result.json()['sync_error']['code']=='gateway_not_configured'
    assert result.json()['publication_status']=='published' and result.json()['sync_status']=='failed'
    assert published==[]


def test_schema_external_references_do_not_trigger_fetches(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,_=provision(client,http_fixture,monkeypatch,publish_service=False)
    tool['inputSchema']={'type':'object','$ref':http_fixture.url('/must-not-fetch')}
    discovered=client.post('/api/v1/network/servers/'+server['id']+'/discover',headers=headers())
    assert discovered.status_code==200
    assert client.post('/api/v1/network/servers/'+server['id']+'/publish',headers=headers()).status_code==200
    before=len(calls)
    assert rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{}}).json()['error']['code']==-32602
    assert len(calls)==before
    assert not any(r['path']=='/must-not-fetch' for r in http_fixture.requests)


def test_entire_published_route_over_real_tcp(client,http_fixture,monkeypatch):
    import httpx
    import socket
    import threading
    import time
    import uvicorn
    server,path,cfg,tool,calls,published=provision(client,http_fixture,monkeypatch)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(32)
    base='http://127.0.0.1:'+str(sock.getsockname()[1])
    cfg['nef_base_url']=base;monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    host=uvicorn.Server(uvicorn.Config(client.app,log_level='error'))
    thread=threading.Thread(target=lambda:host.run(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not host.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert host.started
        with httpx.Client(trust_env=False,timeout=5) as network:
            publish=network.post(base+'/api/v1/network/servers/'+server['id']+'/sync',headers=headers())
            assert publish.status_code==200
            endpoint=published[-1]['server']['url']
            assert endpoint==base+path
            def send(method,params):
                return network.post(endpoint,headers={'Authorization':'Bearer network-only-secret'},json={
                    'jsonrpc':'2.0','id':21,'method':method,'params':params})
            assert send('initialize',{'protocolVersion':MCP_PROTOCOL_VERSION}).json()['result']['serverInfo']==published[-1]['server']['serverInfo']
            assert send('tools/list',{}).json()['result']['tools']==published[-1]['server']['tools']
            actual=send('tools/call',{'name':'inspect_frame','arguments':{'frame':'tcp-frame'}})
            assert actual.json()['result']['content'][0]['text']=='AF result: tcp-frame'
            assert actual.json()['result']['isError'] is False
    finally:
        host.should_exit=True;thread.join(timeout=5);sock.close()
        assert not thread.is_alive()


def test_rpc_failure_is_not_success_and_never_retried(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,_=provision(client,http_fixture,monkeypatch)
    original=http_fixture.routes[('POST','/af')]
    def af_error(request):
        message=json.loads(request['body'])
        if message['method']=='tools/call':
            return json_response({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32603,'message':'private internal detail'}})
        return original(request)
    http_fixture.add('POST','/af',af_error)
    response=rpc(client,path,'tools/call',{'name':'inspect_frame','arguments':{'frame':'no-retry'}})
    assert response.json()['error']['code']==-32002
    assert 'private internal detail' not in response.text
    assert sum(json.loads(r['body']).get('method')=='tools/call' for r in http_fixture.requests if r['path']=='/af')==1
    record=client.get('/api/v1/network/servers',headers=headers()).json()['servers'][0]
    assert record['last_call']['status']=='failed'


def test_preview_matches_publication_without_dispatching(client,http_fixture,monkeypatch):
    server,path,cfg,tool,calls,published=provision(client,http_fixture,monkeypatch,publish_service=False)
    endpoint='/api/v1/network/servers/'+server['id']+'/publication'
    preview=client.get(endpoint,headers=headers())
    assert preview.status_code==200 and published==[]
    assert client.get(endpoint,headers=headers('caller-b')).status_code==404
    assert client.post('/api/v1/network/servers/'+server['id']+'/sync',headers=headers()).status_code==200
    assert preview.json()==published[0]
