# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
import registry
import server
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
    assert body["record"]["caller_agent"] == "网络侧 Network Agent"  # 统一网络侧 Agent
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


def test_internal_rest_discovery_lists_registered_capability():
    key = _key()
    cap_id = _register(key, name="路面缺陷识别", keywords=["路面"])
    cat = client.get("/internal/v1/third-party-capabilities").json()
    assert cat["server"] == "6g-nef-internal-discovery" and cat["trust_domain"] is True
    mine = next(c for c in cat["capabilities"] if c["id"] == cap_id)
    assert mine["owner"] == "af_tester"
    assert mine["endpoint"] == "https://my-af.com/api/detect"
    assert mine["internal_agent"]  # 内部承接 Agent 已映射
    assert mine["invoke_via"].endswith("tools/call")


def test_internal_rest_discovery_since_incremental():
    key = _key()
    old = _register(key, name="旧能力")
    cutoff = next(c["registered_ts"] for c in
                  client.get("/internal/v1/third-party-capabilities").json()["capabilities"]
                  if c["id"] == old) + 0.001
    new = _register(key, name="新能力")
    inc = client.get("/internal/v1/third-party-capabilities", params={"since": cutoff}).json()
    ids = [c["id"] for c in inc["capabilities"]]
    assert new in ids and old not in ids


def test_intent_is_authenticated_and_handed_to_partner_agent():
    key = _key()   # 已订阅 network_diagnosis
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=_hdr(key))  # 仅 PRO/MAX 可发意图
    # 用账号已授权的能力对应的意图，第二道鉴权才会放行转发
    r = client.post("/api/v1/intent", json={"text": "帮我诊断一下网络"}, headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "dispatched"
    assert body["intent_id"].startswith("intent_")
    assert body["auth"]["status"] == "verified"
    assert body["auth"]["account"] == "af_tester"
    assert body["auth"]["scope"] == "intent:submit"
    assert [c["status"] for c in body["auth"]["checks"]] == ["passed"] * 4
    assert body["handoff"]["partner_agent"] == "网络内部 Network Agent"
    assert body["handoff"]["task_id"].startswith("partner_task_")
    assert body["handoff"]["status_owner"] == "internal_network_agent"
    assert body["handoff"]["status_endpoint"].endswith(body["intent_id"])
    assert "matched" not in body
    assert "executions" not in body


def test_intent_does_not_match_or_execute_local_capabilities():
    key = _key()
    cap_id = _register(key, keywords=["质检"])
    r = client.post("/api/v1/intent", json={"text": "帮我检测产线并做质检"}, headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    # 关键不变量：意图链路绝不直接反向调用第三方能力（无论受理或拒绝）
    assert body["status"] in ("dispatched", "rejected")
    assert cap_id not in registry.REVERSE_CALLS


def test_subscriber_of_third_party_has_working_auth_info_and_composer():
    # 回归：A 注册第三方能力，B 订阅后 auth/info 不再 500，且第三方能力进入可编排池
    owner = _key("tp_owner_x")
    cap_id = _register(owner, name="摄像头数据采集", keywords=["摄像头"])
    r = client.post("/api/v1/subscribe", json={"account": "tp_buyer_x",
                                               "capability_ids": [cap_id], "package_ids": []})
    kb = {"Authorization": "Bearer " + r.json()["api_key"]}
    info = client.get("/api/v1/auth/info", headers=kb)
    assert info.status_code == 200
    assert cap_id in info.json()["entitled_capabilities"]  # 可在自助编排中使用
    # 第三方能力可被编排进 Pipeline 并执行
    pid = client.post("/api/v1/compose", json={"name": "cam", "steps": [cap_id]},
                      headers=kb).json()["id"]
    run = client.post(f"/api/v1/pipelines/{pid}/run", headers=kb).json()
    assert run["steps_executed"] == 1


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


def test_mcp_list_marks_subscription():
    key = _key("mcp_tester")   # 订阅了 network_diagnosis
    r = client.post("/api/v1/mcp/tools/list", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers=_hdr(key))
    tools = r.json()["result"]["tools"]
    by_name = {t["name"]: t for t in tools}
    # 全量可用能力都可见（用于"调用时再提醒订阅"的故事），订阅状态用 subscribed 标记
    assert by_name["network_diagnosis"]["subscribed"] is True
    unsub = [t for t in tools if t.get("subscribed") is False]
    assert unsub and all(t["description"].startswith("[未订阅") for t in unsub)


def test_intent_pipeline_baseline_stages():
    key = _key()   # 订阅 network_diagnosis；"诊断"意图命中它 → 第二道放行
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=_hdr(key))  # 仅 PRO/MAX 可发意图
    r = client.post("/api/v1/intent", json={"text": "帮我诊断一下网络"}, headers=_hdr(key))
    stages = [s["stage"] for s in r.json()["pipeline"]]
    # 第一道在受理时鉴权；第二道（逐能力）改由网络侧 Planning Agent 运行时进行，不在提交流水线里
    assert stages == ["auth_verify", "nef_accept", "partner_route", "partner_accept"]


def test_intent_rejects_missing_api_key_before_handoff():
    r = client.post("/api/v1/intent", json={"text": "我要直播AI换脸"})
    assert r.status_code == 401
    assert "Authorization" in r.json()["detail"]


def test_intent_rejects_api_key_without_required_scope():
    key = _key("limited_scope")
    server.API_KEYS[key]["scopes"].remove("intent:submit")
    r = client.post("/api/v1/intent", json={"text": "我要直播AI换脸"}, headers=_hdr(key))
    assert r.status_code == 403
    assert "intent:submit" in r.json()["detail"]


def test_auth_info_exposes_authentication_method_and_scopes():
    key = _key()
    r = client.get("/api/v1/auth/info", headers=_hdr(key))
    assert r.status_code == 200
    body = r.json()
    assert body["authentication"]["scheme"] == "Bearer API Key"
    assert body["authentication"]["status"] == "verified"
    assert "intent:submit" in body["authentication"]["scopes"]
