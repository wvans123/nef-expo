import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from server import app
from registry import INTENTS

client = TestClient(app)
ARGS = {"device_id":"terminal-01", "video_source":"camera-01", "target":"moving target"}


def account(plan="free"):
    r=client.post("/api/v1/register",json={"account":"scene-test-"+uuid.uuid4().hex,"plan":plan})
    return {"Authorization":"Bearer "+r.json()["api_key"]}


def grant(h, service):
    assert client.post(f"/api/v1/services/{service}/subscribe",headers=h).status_code==200


def test_three_scene_contracts_and_subscription_separation():
    scenes=client.get("/api/v1/services").json()["services"]
    assert [s["id"] for s in scenes]==["robot_patrol","traffic_flow_detection","collaborative_tracking"]
    assert scenes[0]["modes"]==scenes[1]["modes"]==["intent"]
    assert scenes[2]["modes"]==["intent","api","tool"]
    assert all(s["preferred_mode"] == "intent" and s["intent_example"] for s in scenes)
    h=account("pro")
    r=client.post("/api/v1/services/robot_patrol/intent",headers={**h,"X-NEF-Execution":"demo"},json={"text":"巡检"})
    assert r.status_code==403  # a global PRO plan is not the scene grant
    grant(h,"robot_patrol")
    info=client.get("/api/v1/auth/info",headers=h).json()
    assert info["scene_subscriptions"]==["robot_patrol"]
    assert client.post("/api/v1/services/traffic_flow_detection/intent",headers={**h,"X-NEF-Execution":"demo"},json={"text":"检测"}).status_code==403


@pytest.mark.parametrize("service",["robot_patrol","traffic_flow_detection","collaborative_tracking"])
def test_scene_intent_demo_is_explicit_and_never_creates_partner_tasks(service):
    h=account();grant(h,service);before=len(INTENTS)
    r=client.post(f"/api/v1/services/{service}/intent",headers={**h,"X-NEF-Execution":"demo"},json={"text":"原文业务目标"})
    assert r.status_code==200
    data=r.json()
    assert data["data_source"]=="demo" and data["status"]=="demo_complete"
    assert data["service_id"]==service and data["demo_result"]["data"]
    assert data["demo_result"]["text"].startswith("【演示结果】")
    assert "task_id" not in data and "intent_id" not in data and len(INTENTS)==before
    assert data["nef_auth"]["authorization_target"]["service_id"]==service
    assert data["nef_auth"]["implementation"]["scene_policy"]=="local_scene_entitlement"
    assert data["nef_auth"]["implementation"]["resource_policy"]=="not_implemented"


def test_scene_api_and_mcp_demo_have_same_service_and_authorization():
    h=account();grant(h,"collaborative_tracking");demo={**h,"X-NEF-Execution":"demo"}
    api=client.post("/api/v1/services/collaborative_tracking/invoke",headers=demo,json=ARGS)
    rpc=client.post("/mcp",headers=demo,json={"jsonrpc":"2.0","id":0,"method":"tools/call","params":{"name":"scene_collaborative_tracking","arguments":ARGS}})
    assert api.status_code==rpc.status_code==200
    result=json.loads(rpc.json()["result"]["content"][0]["text"])
    assert result["service_id"]==api.json()["service_id"]=="collaborative_tracking"
    assert result["data_source"]=="demo" and rpc.json()["id"]==0
    tools=client.post("/mcp",headers=h,json={"jsonrpc":"2.0","id":1,"method":"tools/list"}).json()["result"]["tools"]
    assert any(t["name"]=="scene_collaborative_tracking" and t["subscribed"] for t in tools)


def test_scene_real_mode_fails_closed_and_validates_contract(monkeypatch):
    monkeypatch.delenv("NEF_BRIDGE_CONFIG",raising=False)
    h=account();grant(h,"robot_patrol");grant(h,"collaborative_tracking")
    for extra in [{},{"X-NEF-Execution":"live"}]:
        r=client.post("/api/v1/services/robot_patrol/intent",headers={**h,**extra},json={"text":"巡检"})
        assert r.status_code==503 and "demo_result" not in r.text
    assert client.post("/api/v1/services/robot_patrol/invoke",headers=h,json={}).status_code==422
    assert client.post("/api/v1/services/collaborative_tracking/intent",headers=h,json={"text":"test"}).status_code==503
    assert client.post("/api/v1/services/collaborative_tracking/invoke",headers={**h,"X-NEF-Execution":"demo"},json={"device_id":"only-one-field"}).status_code==422
    assert client.post("/api/v1/services/robot_patrol/intent",headers={**h,"X-NEF-Execution":"demo"},json={"text":" "}).status_code==422


def test_scene_real_intent_and_api_tool_reach_http_service(tmp_path,monkeypatch):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path,json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(202);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(b'{"received":true}')
        def log_message(self,*args):
            pass
    upstream=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
    base=f"http://127.0.0.1:{upstream.server_port}"
    cfg={"scenes":{"robot_patrol":{"intent":{"url":base+"/patrol","body":{"goal":"$text","service":"$service_id"}}},"collaborative_tracking":{"invoke":{"url":base+"/track","body":{"input":"$arguments"}}}}}
    path=tmp_path/"scenes.json";path.write_text(json.dumps(cfg),encoding="utf-8");monkeypatch.setenv("NEF_BRIDGE_CONFIG",str(path))
    try:
        h=account();grant(h,"robot_patrol");grant(h,"collaborative_tracking")
        text="  原文不变\n执行巡检  "
        r=client.post("/api/v1/services/robot_patrol/intent",headers=h,json={"text":text})
        assert r.status_code==200 and r.json()["data_source"]=="live" and "demo_result" not in r.json()
        assert client.post("/api/v1/services/collaborative_tracking/invoke",headers=h,json=ARGS).status_code==200
        r=client.post("/mcp",headers=h,json={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scene_collaborative_tracking","arguments":ARGS}})
        assert json.loads(r.json()["result"]["content"][0]["text"])["data_source"]=="live"
        assert seen==[("/patrol",{"goal":text,"service":"robot_patrol"}),("/track",{"input":ARGS}),("/track",{"input":ARGS})]
    finally:
        upstream.shutdown();upstream.server_close();thread.join(timeout=2)
