"""Manual browser integration fixture. Local synthetic peer, never production configuration.
Run: python tests/workbench_fixture.py --port 8071
Stop the process after browser verification. Files only in a temporary directory.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class Peer(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,value,status=200):
        body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/latest':return self.respond({'final_result':'Local fixture perception result'})
        self.respond({'items':[{'id':'fixture.vision','name':'联调视觉工具','kind':'tool','description':'本地验证目录，不是生产网络数据','inputSchema':{'type':'object','properties':{}}},{'id':'fixture.patrol','name':'联调巡检套餐','kind':'package','description':'本地目录契约验证'}]})
    def do_DELETE(self):
        self.respond({'deleted':True})
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path=='/robot-intent':
            assert self.headers.get('Content-Type')=='text/plain; charset=utf-8'
            return self.respond({'text':raw.decode('utf-8')})
        body=json.loads(raw)
        if self.path=='/plans':return self.respond({'accepted':True,'subscriberId':body['subscriberId']})
        if self.path=='/publish':return self.respond({'accepted':True})
        if self.path=='/intent':return self.respond({'text':'【本地联调回执】已收到意图原文：'+body['text']})
        if self.path=='/invoke':return self.respond({'text':'【本地联调回执】已收到 API / Tool 参数。','arguments':body})
        if body.get('method')=='notifications/initialized':
            self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
        if body.get('method')=='initialize':result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'local-fixture-mcp','version':'1.0'}}
        elif body.get('method')=='tools/list':result={'tools':[{'name':'inspect_frame','description':'本地联调图像检查工具','inputSchema':{'type':'object','properties':{'frame_ref':{'type':'string','description':'图像引用'}},'required':['frame_ref']}}]}
        elif body.get('method')=='tools/call':result={'content':[{'type':'text','text':'【本地 AF 回执】'+json.dumps(body['params']['arguments'],ensure_ascii=False)}],'isError':False}
        else:return self.respond({'jsonrpc':'2.0','id':body.get('id'),'error':{'code':-32601,'message':'Unsupported fixture method'}})
        self.respond({'jsonrpc':'2.0','id':body.get('id'),'result':result})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8071);args=parser.parse_args()
    os.chdir(ROOT)
    peer=ThreadingHTTPServer(('127.0.0.1',0),Peer);threading.Thread(target=peer.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{peer.server_port}'
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workbench-fixture-',dir=runtime) as folder:
        registry=Path(folder)/'registry.json';registry.write_text(json.dumps({'catalog_url':base+'/catalog','publish_url':base+'/publish','mcp_servers':{base+'/mcp':{}},'nef_base_url':f'http://127.0.0.1:{args.port}','network_clients':{}}),encoding='utf-8')
        routes={id:{'intent':{'url':base+'/intent','body':{'text':'$text'}},'invoke':{'url':base+'/invoke','body':'$arguments'}} for id in ['robot_patrol','traffic_flow_detection','collaborative_tracking']}
        routes['robot_patrol'].update(intent={'url':base+'/robot-intent','content_type':'text/plain','body':'$text'},result={'url':base+'/latest','method':'GET'})
        bridge=Path(folder)/'bridge.json';bridge.write_text(json.dumps({'capabilities':{'target_detection':{'url':base+'/invoke','body':'$arguments'}},'scenes':routes}),encoding='utf-8')
        subscriptions=Path(folder)/'subscriptions.json';subscriptions.write_text(json.dumps({'callback_url':base+'/plans','discount':0.8,'account_ids':None,'reset_partner_plans_on_start':False}),encoding='utf-8')
        os.environ['NEF_REGISTRY_CONFIG']=str(registry);os.environ['NEF_BRIDGE_CONFIG']=str(bridge)
        os.environ['NEF_SUBSCRIPTION_CONFIG']=str(subscriptions)
        os.environ['NEF_INTEGRATION_CONFIG']=str(Path(folder)/'missing.json')
        print('LOCAL_FIXTURE_MCP='+base+'/mcp',flush=True)
        import uvicorn
        try:uvicorn.run('server:app',host='127.0.0.1',port=args.port,log_level='warning')
        finally:peer.shutdown();peer.server_close()
