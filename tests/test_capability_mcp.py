"""The TRF-advertised NEF endpoint exposes exactly one real, authorized capability."""
import json

import pytest
from fastapi.testclient import TestClient

import server
from skills import CAPABILITIES, TRF_TOOL_TYPES, capability_tool_type, trf_catalog_capabilities


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    return TestClient(server.app)


def test_homepage_taxonomy_is_total_and_excludes_roadmap_and_ecosystem():
    assert all(capability_tool_type(c) in TRF_TOOL_TYPES for c in CAPABILITIES)
    offered = {c.id: capability_tool_type(c) for c in trf_catalog_capabilities()}
    assert not any(c.id in offered for c in CAPABILITIES if c.status != "available" or c.category == "ecosystem")
    assert offered["target_detection"] == "sensing tool"
    assert offered["ai_inference"] == "computing tool"
    assert offered["network_analytics"] == "nf tool"
    assert offered["precision_location"] == "nf tool"
    assert set(TRF_TOOL_TYPES) == {"nf tool", "computing tool", "sensing tool", "third-party tool"}


def test_single_tool_route_auth_discovery_and_live_call(client, monkeypatch):
    account = client.post("/api/v1/register", json={"account": "single-tool", "plan": "pro"}).json()
    auth = {"Authorization": "Bearer " + account["api_key"]}
    path = "/mcp/capabilities/target_detection"
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post(path, json=message).status_code == 401
    tools = client.post(path, headers=auth, json=message).json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["target_detection"]
    assert tools[0]["subscribed"] is True
    calls = []
    monkeypatch.setattr(server.exhibition, "forward", lambda kind, value: calls.append((kind, value)) or {"text": "live-test-receipt"})
    invocation = {"jsonrpc": "2.0", "id": "test", "method": "tools/call",
                  "params": {"name": "target_detection", "arguments": {"area": "test-area"}}}
    result = client.post(path, headers={**auth, "X-NEF-Execution": "demo"}, json=invocation).json()
    assert "live-test-receipt" in result["result"]["content"][0]["text"]
    assert len(calls) == 1 and calls[0][1]["capability_id"] == "target_detection"
    assert calls[0][1]["arguments"] == {"area": "test-area"}
    invocation["params"]["name"] = "compute_offload"
    assert client.post(path, headers=auth, json=invocation).json()["error"]["code"] == -32602
    invocation["params"]["name"] = "target_detection"
    invocation.pop("id")
    assert client.post(path, headers=auth, json=invocation).status_code == 202
    assert len(calls) == 1
    for excluded in ("capability_register", "vital_sign_detection", "unknown"):
        assert client.post("/mcp/capabilities/" + excluded, headers=auth, json=message).status_code == 404
    server.API_KEYS[account["api_key"]]["scopes"].discard("mcp:tools")
    assert client.post(path, headers=auth, json=message).status_code == 403


def test_registered_does_not_mean_entitled_or_execution_ready(client, monkeypatch):
    account = client.post("/api/v1/register", json={"account": "no-grant"}).json()
    auth = {"Authorization": "Bearer " + account["api_key"]}
    def unavailable(*args):
        raise server.HTTPException(503, "测试：真实执行地址未配置")
    monkeypatch.setattr(server.exhibition, "forward", unavailable)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "target_detection", "arguments": {"area": "test"}}}
    path = "/mcp/capabilities/target_detection"
    unpaid = client.post(path, headers=auth, json=request).json()["result"]
    assert unpaid["payment_required"] is True
    client.post("/api/v1/account/plan", headers=auth, json={"plan": "pro"})
    unavailable_result = client.post(path, headers=auth, json=request).json()["result"]
    assert unavailable_result["isError"] is True
    assert json.loads(unavailable_result["content"][0]["text"])["http_status"] == 503
