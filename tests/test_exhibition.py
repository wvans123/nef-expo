"""Real local HTTP forwarding plus authenticated, independent result channels."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient
import exhibition
from server import app

client = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    exhibition.CHANNELS.clear()
    monkeypatch.delenv("NEF_BRIDGE_CONFIG", raising=False)
    yield
    exhibition.CHANNELS.clear()


def headers(plan="pro"):
    import uuid
    key = client.post("/api/v1/register", json={"account": "expo-test-" + uuid.uuid4().hex, "plan": plan}).json()["api_key"]
    return {"Authorization": "Bearer " + key, "X-NEF-Execution": "live"}


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"body": data, "path": self.path, "request_id": self.headers.get("X-NEF-Request-ID")})
            self.send_response(202 if self.path == "/intent" else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"received": True, "echo": data}).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    config = {"intent": {"url": root + "/intent", "body": {"utterance": "$text"}},
              "capabilities": {"target_detection": {"url": root + "/detect", "body": {"input": "$arguments"}}}}
    path = tmp_path / "bridge.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("NEF_BRIDGE_CONFIG", str(path))
    yield seen
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_intent_really_forwards_verbatim_without_partner_id(upstream):
    text = "  原文不改：请对园区A巡检\n发现异常再回传  "
    response = client.post("/api/v1/intent", headers=headers(), json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "forwarded" and data["data_source"] == "live"
    assert data["upstream"]["http_status"] == 202
    assert "intent_id" not in data and "task_id" not in data and "handoff" not in data
    assert upstream[0]["body"] == {"utterance": text}
    assert upstream[0]["request_id"] == data["request_id"]
    assert "Planning Agent" not in response.text


def test_api_and_mcp_share_real_mapping(upstream):
    h = headers()
    api = client.post("/api/v1/capabilities/target_detection/invoke", headers=h, json={"area": "A"})
    rpc = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 0, "method": "tools/call", "params": {"name": "target_detection", "arguments": {"area": "B"}}})
    assert api.status_code == rpc.status_code == 200
    assert api.json()["data_source"] == "live"
    assert rpc.json()["id"] == 0
    assert json.loads(rpc.json()["result"]["content"][0]["text"])["data_source"] == "live"
    assert [r["path"] for r in upstream] == ["/detect", "/detect"]
    assert [r["body"] for r in upstream] == [{"input": {"area": "A"}}, {"input": {"area": "B"}}]


def test_no_subscription_or_intent_permission_does_not_forward(upstream):
    h = headers("free")
    r = client.post("/api/v1/capabilities/target_detection/invoke", headers=h, json={"area": "A"})
    assert r.status_code == 402
    r = client.post("/api/v1/intent", headers=h, json={"text": "巡检"})
    assert r.status_code == 403 and not upstream


def test_unconfigured_never_falls_back_to_mock():
    h = headers()
    for path, body in [("/api/v1/intent", {"text": "巡检"}), ("/api/v1/capabilities/target_detection/invoke", {"area": "A"})]:
        r = client.post(path, headers=h, json=body)
        assert r.status_code == 503
        assert r.json()["detail"]["status"] == "not_configured"


def test_timeout_means_unknown_without_retry(monkeypatch):
    monkeypatch.setattr(exhibition, "config", lambda: {"intent": {"url": "http://localhost:9/intent"}})
    calls = []
    class TimeoutClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, *args, **kwargs):
            calls.append(1)
            raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(exhibition.httpx, "Client", TimeoutClient)
    r = client.post("/api/v1/intent", headers=headers(), json={"text": "巡检"})
    assert r.status_code == 504 and r.json()["detail"]["status"] == "unknown"
    assert len(calls) == 1


def make_channel():
    h = headers()
    response = client.post("/api/v1/exhibition/channels", headers=h, json={"name": "巡检场景"})
    assert response.status_code == 200
    c = response.json()
    return h, c, {"Authorization": "Bearer " + c["receiver_key"]}


def test_callback_data_without_request_or_intent_id():
    h, c, receiver = make_channel()
    endpoint = c["events_endpoint"]
    assert client.post(endpoint, headers=receiver, json={"kind": "status", "title": "处理中"}).status_code == 200
    assert client.post(endpoint, headers=receiver, json={"kind": "data", "data": {"objects": 3}}).status_code == 200
    data = client.get(endpoint, headers=h).json()["events"]
    assert [e["kind"] for e in data] == ["status", "data"]
    assert data[1]["data"]["objects"] == 3 and "request_id" not in data[1]
    assert client.post(endpoint, headers=h, json={"kind": "status"}).status_code == 401
    assert client.get(endpoint, headers=receiver).status_code == 401
    assert client.get(endpoint, headers=headers()).status_code == 404
    assert "receiver_key" not in client.get("/api/v1/exhibition/channels", headers=h).text


def test_image_binary_upload_event_and_owner_read():
    h, c, recv = make_channel()
    uploaded = client.post(c["media_endpoint"], headers={**recv, "Content-Type": "image/png"}, content=PNG)
    assert uploaded.status_code == 200
    aid = uploaded.json()["asset_id"]
    r = client.post(c["events_endpoint"], headers=recv, json={"kind": "image", "asset_id": aid, "title": "场景帧"})
    assert r.status_code == 200
    path = c["media_endpoint"] + "/" + aid
    response = client.get(path, headers=h)
    assert response.content == PNG and response.headers["x-content-type-options"] == "nosniff"
    assert client.get(path, headers=headers()).status_code == 404
    assert client.get(path).status_code == 401
    assert client.post(c["events_endpoint"], headers=recv, json={"kind": "video", "asset_id": aid}).status_code == 422


def test_media_validation_limits_and_untrusted_payload(monkeypatch):
    h, c, recv = make_channel()
    assert client.post(c["media_endpoint"], headers={**recv,"Content-Type":"image/svg+xml"}, content=b"<svg/>").status_code == 415
    assert client.post(c["media_endpoint"], headers={**recv,"Content-Type":"image/png"}, content=b"<script/>").status_code == 415
    assert client.post(c["events_endpoint"], headers=recv, json={"kind":"image","media_url":"https://example.com/a.png"}).status_code == 422
    assert client.post(c["events_endpoint"], headers=recv, json=[]).status_code == 422
    assert client.post(c["events_endpoint"], headers=recv, json={"kind":"status","title":{}}).status_code == 422
    monkeypatch.setattr(exhibition,"MAX_UPLOAD",10)
    assert client.post(c["media_endpoint"], headers={**recv,"Content-Type":"image/png"}, content=PNG).status_code == 413
    monkeypatch.setattr(exhibition,"MAX_JSON",10)
    assert client.post(c["events_endpoint"], headers=recv, json={"kind":"status","text":"too long"}).status_code == 413


def test_live_mcp_does_not_expose_or_execute_composite_demo_tools():
    h = headers()
    result = client.post("/mcp",headers=h,json={"jsonrpc":"2.0","id":0,"method":"tools/list"}).json()
    assert result["id"] == 0
    assert not any(t["name"].startswith(("scenario_","pipeline_")) for t in result["result"]["tools"])
    r = client.post("/mcp",headers=h,json={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scenario_robot_patrol"}})
    assert r.status_code == 200 and r.json()["result"]["isError"] is True
    assert json.loads(r.json()["result"]["content"][0]["text"])["http_status"] == 503


def test_live_forward_failure_preserves_verified_auth_evidence():
    h = headers()
    r = client.post("/api/v1/capabilities/target_detection/invoke", headers=h, json={"area":"A"})
    assert r.status_code == 503
    evidence = r.json()["detail"]["nef_auth"]
    assert evidence["decision"] == "allow"
    assert evidence["implementation"]["authentication"] == "local_api_key"
    assert evidence["implementation"]["standard_compliance"] is False
    assert evidence["implementation"]["resource_policy"] == "not_implemented"
    assert evidence["implementation"]["audit_persistence"] is False
    assert {s["code"] for s in evidence["pipeline"] if s["status"]=="passed"} >= {"identify","validate","scope","authorize"}
    assert "未过期、未被吊销" not in r.text


def test_intent_entry_receipt_does_not_claim_scene_authorization():
    r = client.post("/api/v1/intent", headers=headers(), json={"text":"巡检"})
    assert r.status_code == 503
    evidence = r.json()["detail"]["nef_auth"]
    assert evidence["implementation"]["scene_policy"] == "not_implemented"
    denied = client.post("/api/v1/intent",headers=headers("free"),json={"text":"巡检"})
    assert denied.status_code == 403
    assert any(s["code"]=="authorize" and s["status"]=="denied" for s in denied.json()["detail"]["nef_auth"]["pipeline"])
