# -*- coding: utf-8 -*-
"""场景级一键调用（REST + MCP）与鉴权回执测试"""
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def _subscribe_pkg(account="scn_tester", pkg="live_offload"):
    r = client.post("/api/v1/subscribe", json={"account": account, "capability_ids": [], "package_ids": [pkg]})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["api_key"]}


def test_packages_featured_first():
    pkgs = client.get("/api/v1/packages").json()["packages"]
    featured = [p["id"] for p in pkgs if p.get("featured")]
    assert featured == [p["id"] for p in pkgs[:len(featured)]]
    assert len(featured) == 3


def test_scenario_run_returns_trace_and_auth():
    h = _subscribe_pkg()
    r = client.post("/api/v1/scenarios/live_offload/run", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["auth"]["status"] == "verified"
    stages = [s["stage"] for s in body["pipeline"]]
    assert stages[0] == "auth_verify" and "partner_execute" in stages
    trace = body["execution_trace"]
    assert len(trace) >= 4
    assert any(s["narrative"] for s in trace)  # story_steps 出现在轨迹中
    assert all(s["capability"] for s in trace if not s["narrative"])


def test_scenario_run_requires_package_subscription():
    h = _subscribe_pkg(account="scn_other", pkg="xr_render")
    r = client.post("/api/v1/scenarios/live_offload/run", headers=h)
    assert r.status_code == 403
    assert client.post("/api/v1/scenarios/nope/run", headers=h).status_code == 404


def test_mcp_lists_and_calls_scenario_tool():
    h = _subscribe_pkg(account="scn_mcp", pkg="robot_patrol")
    tools = client.post("/api/v1/mcp/tools/list", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=h).json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "scenario_robot_patrol" in names
    r = client.post("/api/v1/mcp/tools/call",
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "scenario_robot_patrol", "arguments": {}}}, headers=h)
    assert r.status_code == 200 and not r.json()["result"]["isError"]
    # 未订阅的场景 tool 拒绝
    r2 = client.post("/api/v1/mcp/tools/call",
                     json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "scenario_live_offload", "arguments": {}}}, headers=h)
    assert "error" in r2.json()


def test_invoke_and_mcp_call_carry_auth_stamp():
    r = client.post("/api/v1/subscribe", json={"account": "scn_auth", "capability_ids": ["qos_guarantee"], "package_ids": []})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    inv = client.post("/api/v1/capabilities/qos_guarantee/invoke", json={"device_id": "imsi-001"}, headers=h)
    assert inv.status_code == 200 and inv.json()["nef_auth"]["status"] == "verified"
    call = client.post("/api/v1/mcp/tools/call",
                       json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "qos_guarantee", "arguments": {"device_id": "imsi-001"}}}, headers=h)
    assert "nef_auth" in call.json()["result"]["content"][0]["text"]
