# -*- coding: utf-8 -*-
"""账号等级授权、意图权限检查、pipeline MCP 工具、标准 /mcp 端点、第三方定价订阅"""
from fastapi.testclient import TestClient

from registry import INTENTS
from server import app

client = TestClient(app)


def _hdr(account, plan="free"):
    r = client.post("/api/v1/register", json={"account": account, "plan": plan})
    return {"Authorization": "Bearer " + r.json()["api_key"]}


def test_plan_entitles_tiers_without_subscription():
    h = _hdr("plan_free")
    # free：basic 能力未授权 → 402
    assert client.post("/api/v1/capabilities/target_detection/invoke",
                       json={"area": "A"}, headers=h).status_code == 402
    # 升级 pro → basic 直接可用；advanced 仍 402
    r = client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=h)
    assert r.json()["plan"] == "pro"
    assert client.post("/api/v1/capabilities/target_detection/invoke",
                       json={"area": "A"}, headers=h).status_code == 200
    assert client.post("/api/v1/capabilities/target_tracking/invoke",
                       json={"target_id": "t1"}, headers=h).status_code == 402
    # max → advanced 也可用
    client.post("/api/v1/account/plan", json={"plan": "max"}, headers=h)
    assert client.post("/api/v1/capabilities/target_tracking/invoke",
                       json={"target_id": "t1"}, headers=h).status_code == 200
    info = client.get("/api/v1/auth/info", headers=h).json()
    assert info["plan"] == "max" and len(info["entitled_capabilities"]) > 5


def test_intent_all_unauthorized_is_rejected():
    # free 账号未订阅任何能力：第二道（网络侧业务鉴权）全未授权 → NEF 不予转发
    h = _hdr("plan_intent")
    r = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"}, headers=h).json()
    assert r["status"] == "rejected"
    assert r["network_authz"]["decision"] == "rejected"
    assert r["network_authz"]["authorized_count"] == 0
    assert all(not c["authorized"] for c in r["network_authz"]["checks"])
    # 状态查询同样是 rejected，执行轨迹全部 denied
    st = client.get(f"/api/v1/intent/{r['intent_id']}", headers=h).json()
    assert st["status"] == "rejected"
    assert all(s["status"] == "denied" for s in st["execution_trace"])


def test_pipeline_exposed_and_callable_via_mcp():
    r = client.post("/api/v1/subscribe", json={"account": "pipe_af",
                                               "capability_ids": ["target_detection", "ai_inference"],
                                               "package_ids": []})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    pid = client.post("/api/v1/compose", json={"name": "检测流水线",
                                               "steps": ["target_detection", "ai_inference"]},
                      headers=h).json()["id"]
    tools = client.post("/api/v1/mcp/tools/list", json={"jsonrpc": "2.0", "id": 1,
                                                        "method": "tools/list", "params": {}},
                        headers=h).json()["result"]["tools"]
    assert f"pipeline_{pid}" in [t["name"] for t in tools]
    call = client.post("/api/v1/mcp/tools/call",
                       json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": f"pipeline_{pid}", "arguments": {}}}, headers=h)
    assert not call.json()["result"]["isError"]
    assert "steps_executed" in call.json()["result"]["content"][0]["text"]


def test_standard_mcp_endpoint():
    h = _hdr("mcp_std")
    init = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                     "params": {"protocolVersion": "2025-03-26"}}, headers=h)
    assert init.json()["result"]["serverInfo"]["name"] == "6g-nef-exposure"
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                       headers=h).status_code == 202
    lst = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                      headers=h)
    assert len(lst.json()["result"]["tools"]) > 10


def test_register_af_with_price_and_subscribable():
    h = _hdr("tp_seller")
    tp = client.post("/api/v1/register-af",
                     json={"name": "缺陷识别模型", "cap_type": "ai_model",
                           "endpoint": "https://x.example.com/api", "price": "0.8/次"},
                     headers=h).json()["registration_id"]
    cap = client.get(f"/api/v1/capabilities/{tp}").json()
    assert cap["unit_price"] == "0.8/次"
    # 其他 AF 可订阅第三方能力
    r = client.post("/api/v1/subscribe", json={"account": "tp_buyer",
                                               "capability_ids": [tp], "package_ids": []})
    assert r.status_code == 200 and tp in r.json()["subscriptions"]


def test_internal_mcp_discovery_and_reverse_call():
    h = _hdr("tp_owner2")
    tp = client.post("/api/v1/register-af",
                     json={"name": "路况数据源", "cap_type": "data_source",
                           "endpoint": "https://y.example.com/api", "price": "0.3/次"},
                     headers=h).json()["registration_id"]
    # 内部 Agent 免 AF 鉴权发现
    lst = client.post("/internal/mcp", json={"jsonrpc": "2.0", "id": 1,
                                             "method": "tools/list", "params": {}})
    tools = lst.json()["result"]["tools"]
    mine = [t for t in tools if t["name"] == tp]
    assert mine and "提供方 tp_owner2" in mine[0]["description"]
    # 内部调用 → 反向台账
    call = client.post("/internal/mcp",
                       json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": tp, "arguments": {"_caller": "Planning Agent"}}})
    assert "reverse_call" in call.json()["result"]["content"][0]["text"]
    board = client.get("/api/v1/third-party/my-calls", headers=h).json()
    cap = next(c for c in board["capabilities"] if c["id"] == tp)
    assert cap["call_count"] == 1
    assert cap["recent_calls"][0]["trigger"] == "internal_mcp"


def test_other_account_can_see_and_invoke_third_party():
    h = _hdr("tp_owner3")
    tp = client.post("/api/v1/register-af",
                     json={"name": "包装检测模型", "cap_type": "ai_model",
                           "endpoint": "https://z.example.com/api"},
                     headers=h).json()["registration_id"]
    other = _hdr("tp_consumer")
    caps = client.get("/api/v1/capabilities").json()["capabilities"]
    assert tp in [c["id"] for c in caps]
    r = client.post(f"/api/v1/capabilities/{tp}/invoke", json={"payload": {}}, headers=other)
    assert r.status_code == 200
