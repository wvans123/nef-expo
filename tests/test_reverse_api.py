# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
import registry
from server import app

client = TestClient(app)


def setup_function():
    registry.THIRD_PARTY.clear()
    registry.THIRD_PARTY_META.clear()
    registry.REVERSE_CALLS.clear()


def _key(account="af_tester"):
    r = client.post("/api/v1/subscribe",
                    json={"account": account, "capability_ids": ["network_diagnosis"], "package_ids": []})
    return r.json()["api_key"]


def _hdr(key):
    return {"Authorization": f"Bearer {key}"}


def _register(key, name="工业缺陷识别模型", keywords=None):
    body = {"name": name, "cap_type": "ai_model", "description": "缺陷识别",
            "endpoint": "https://my-af.com/api/detect"}
    if keywords is not None:
        body["intent_keywords"] = keywords
    r = client.post("/api/v1/register-af", json=body, headers=_hdr(key))
    assert r.status_code == 200
    return r.json()["registration_id"]


def test_register_af_stores_keywords_and_owner():
    key = _key()
    cap_id = _register(key, keywords=["质检", "缺陷"])
    cap = next(c for c in registry.THIRD_PARTY if c.id == cap_id)
    assert cap.intent_keywords == ["质检", "缺陷"]
    meta = registry.THIRD_PARTY_META[cap_id]
    assert meta["owner"] == "af_tester"
    assert meta["cap_type"] == "ai_model"


def test_register_af_default_keywords_is_name():
    key = _key()
    cap_id = _register(key)  # 不传 keywords
    cap = next(c for c in registry.THIRD_PARTY if c.id == cap_id)
    assert cap.intent_keywords == ["工业缺陷识别模型"]


def test_registered_cap_visible_in_marketplace():
    key = _key()
    cap_id = _register(key)
    r = client.get("/api/v1/capabilities")
    ids = [c["id"] for c in r.json()["capabilities"]]
    assert cap_id in ids


def test_simulate_call_creates_ledger_record():
    key = _key()
    cap_id = _register(key)
    r = client.post(f"/api/v1/third-party/{cap_id}/simulate-call", headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    assert body["record"]["trigger"] == "manual"
    assert body["record"]["caller_agent"] == "Computing Agent"  # ai_model → Computing
    assert body["response_payload"]["result"]["provided_by"] == "third_party_af"


def test_simulate_call_404_unknown():
    key = _key()
    r = client.post("/api/v1/third-party/tp_nonexist/simulate-call", headers=_hdr(key))
    assert r.status_code == 404


def test_simulate_call_403_not_owner():
    key1 = _key("owner_a")
    cap_id = _register(key1)
    key2 = _key("other_b")
    r = client.post(f"/api/v1/third-party/{cap_id}/simulate-call", headers=_hdr(key2))
    assert r.status_code == 403


def test_my_calls_summary():
    key = _key()
    cap_id = _register(key)
    client.post(f"/api/v1/third-party/{cap_id}/simulate-call", headers=_hdr(key))
    client.post(f"/api/v1/third-party/{cap_id}/simulate-call", headers=_hdr(key))
    r = client.get("/api/v1/third-party/my-calls", headers=_hdr(key))
    assert r.status_code == 200
    caps = r.json()["capabilities"]
    assert len(caps) == 1
    c = caps[0]
    assert c["id"] == cap_id
    assert c["call_count"] == 2
    assert c["total_fee"] == 0.1
    assert c["discovered"] is True
    assert len(c["recent_calls"]) == 2
    # 倒序：最新在前
    assert c["recent_calls"][0]["ts"] >= c["recent_calls"][1]["ts"]


def test_intent_triggers_reverse_call():
    key = _key()
    cap_id = _register(key, keywords=["质检", "缺陷识别"])
    r = client.post("/api/v1/intent", json={"text": "帮我对产线做质检"}, headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True
    tp_steps = [e for e in body["executions"] if e.get("source") == "third_party"]
    assert len(tp_steps) == 1
    assert tp_steps[0]["direction"] == "reverse"
    assert tp_steps[0]["capability"] == cap_id
    assert tp_steps[0]["agent"] == "Computing Agent"
    # 台账同步写入，触发源为 intent
    calls = registry.REVERSE_CALLS[cap_id]
    assert len(calls) == 1
    assert calls[0]["trigger"] == "intent"


def test_intent_package_match_keeps_third_party_step():
    key = _key()
    cap_id = _register(key, keywords=["质检"])
    # “检测”+“质检”命中 smart_factory 套餐的两个能力，同时命中第三方能力
    r = client.post("/api/v1/intent", json={"text": "帮我检测产线并做质检"}, headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    assert body["scenario_id"] == "smart_factory"
    tp_steps = [e for e in body["executions"] if e.get("source") == "third_party"]
    assert len(tp_steps) == 1
    assert tp_steps[0]["capability"] == cap_id


def test_register_af_blank_name_422():
    key = _key()
    r = client.post("/api/v1/register-af",
                    json={"name": "  ", "cap_type": "tool", "endpoint": "https://x.com"},
                    headers=_hdr(key))
    assert r.status_code == 422


def test_planned_cap_blocked():
    r = client.post("/api/v1/subscribe",
                    json={"account": "p_tester", "capability_ids": ["vital_sign_detection"], "package_ids": []})
    assert r.status_code == 403
    key = _key("p_tester2")
    r = client.post("/api/v1/capabilities/vital_sign_detection/invoke", json={"area": "a"}, headers=_hdr(key))
    assert r.status_code == 403


def test_mcp_list_only_subscribed():
    key = _key("mcp_tester")   # 订阅了 network_diagnosis
    r = client.post("/api/v1/mcp/tools/list", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers=_hdr(key))
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert names == ["network_diagnosis"]


def test_intent_pipeline_baseline_stages():
    key = _key()
    r = client.post("/api/v1/intent", json={"text": "帮我诊断一下网络"}, headers=_hdr(key))
    stages = [s["stage"] for s in r.json()["pipeline"]]
    assert stages == ["nef_accept", "forward_planning", "semantic_parse", "skill_match", "agent_dispatch", "tool_exec", "aggregate"]


def test_intent_live_offload_scenario():
    key = _key()
    r = client.post("/api/v1/intent", json={"text": "我要直播AI换脸，算力和网络都不能卡顿"}, headers=_hdr(key))
    assert r.json()["scenario_id"] == "live_offload"


def test_intent_xr_render_scenario():
    key = _key()
    r = client.post("/api/v1/intent", json={"text": "XR 会议把渲染放到边缘 GPU，画面不能卡顿"}, headers=_hdr(key))
    assert r.json()["scenario_id"] == "xr_render"
