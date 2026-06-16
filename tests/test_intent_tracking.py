# -*- coding: utf-8 -*-
"""Intent 状态跟踪与按次计费（402）测试"""
from fastapi.testclient import TestClient

from registry import INTENTS
from server import app

client = TestClient(app)


def _key(account="trk_tester"):
    r = client.post("/api/v1/subscribe", json={"account": account, "capability_ids": ["network_diagnosis"], "package_ids": []})
    return {"Authorization": "Bearer " + r.json()["api_key"]}


def test_intent_status_progresses_to_completed():
    # 订阅机器狗巡检套餐 → 意图解析出的能力均已授权 → 第二道鉴权通过 → 转发并推进
    rr = client.post("/api/v1/subscribe", json={"account": "trk_done",
                                                "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + rr.json()["api_key"]}
    r = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"}, headers=h)
    assert r.json()["status"] == "dispatched"
    iid = r.json()["intent_id"]
    assert r.json()["handoff"]["status_endpoint"].endswith(iid)
    st = client.get(f"/api/v1/intent/{iid}", headers=h).json()
    assert st["status"] == "accepted" and st["progress"] < 100
    assert [s["state"] for s in st["stages"]][0] == "active"
    # 把提交时间拨回 20 秒前 → 状态推进为 completed，回传执行轨迹
    INTENTS[iid]["submitted_ts"] -= 20
    st = client.get(f"/api/v1/intent/{iid}", headers=h).json()
    assert st["status"] == "completed" and st["progress"] == 100
    assert st.get("execution_trace") and st.get("scenario")


def test_intent_status_owner_and_missing():
    h = _key()
    iid = client.post("/api/v1/intent", json={"text": "test"}, headers=h).json()["intent_id"]
    other = _key("trk_other")
    assert client.get(f"/api/v1/intent/{iid}", headers=other).status_code == 403
    assert client.get("/api/v1/intent/intent_nope", headers=h).status_code == 404


def test_unsubscribed_invoke_402_then_per_call_billing():
    h = _key("pay_tester")
    r = client.post("/api/v1/capabilities/target_detection/invoke", json={"area": "A"}, headers=h)
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert detail["status"] == "payment_required" and len(detail["options"]) == 2
    r2 = client.post("/api/v1/capabilities/target_detection/invoke",
                     json={"area": "A", "_confirm_pay": True}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["billing"]["mode"] == "per_call"
    info = client.get("/api/v1/auth/info", headers=h).json()
    assert info["per_call_charges"]["count"] == 1
    assert info["per_call_charges"]["total"] > 0


def test_mcp_payment_reminder_flow():
    h = _key("pay_mcp")
    call = lambda args: client.post("/api/v1/mcp/tools/call",
                                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                          "params": {"name": "target_detection", "arguments": args}}, headers=h).json()
    r = call({"area": "A"})
    assert r["result"].get("payment_required") is True
    assert "payment_required" in r["result"]["content"][0]["text"]
    r2 = call({"area": "A", "_confirm_pay": True})
    assert "billing" in r2["result"]["content"][0]["text"]


def test_register_issues_key_without_subscription():
    r = client.post("/api/v1/register", json={"account": "fresh_af"})
    assert r.status_code == 200
    key = r.json()["api_key"]
    h = {"Authorization": "Bearer " + key}
    info = client.get("/api/v1/auth/info", headers=h).json()
    assert info["subscribed_capabilities"] == []
    # 未订阅也能走按次付费
    r2 = client.post("/api/v1/capabilities/target_detection/invoke",
                     json={"area": "A", "_confirm_pay": True}, headers=h)
    assert r2.status_code == 200 and r2.json()["billing"]["mode"] == "per_call"
    # 再注册同名账号返回同一个 Key
    assert client.post("/api/v1/register", json={"account": "fresh_af"}).json()["api_key"] == key
