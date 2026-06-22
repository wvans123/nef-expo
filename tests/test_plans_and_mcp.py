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


def test_taxonomy_has_ai_and_security_categories():
    d = client.get("/api/v1/capabilities").json()
    cats = d["categories"]
    assert "ai" in cats and "security" in cats
    bycat = {}
    for c in d["capabilities"]:
        bycat.setdefault(c["category"], []).append(c["id"])
    assert set(bycat["ai"]) == {"ai_inference", "edge_agent_hosting", "federated_learning", "network_analytics"}
    assert set(bycat["security"]) == {"identity_service", "security_posture"}
    assert "traffic_forecast" in bycat["isac"] and "sensing_fence" in bycat["isac"]


def test_new_capabilities_invokable():
    r = client.post("/api/v1/subscribe", json={"account": "tax",
                                               "capability_ids": ["sensing_fence", "security_posture"],
                                               "package_ids": []})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    sf = client.post("/api/v1/capabilities/sensing_fence/invoke", json={"area": "厂区A"}, headers=h)
    assert sf.status_code == 200 and "breach_detected" in sf.json()["result"]
    sp = client.post("/api/v1/capabilities/security_posture/invoke", json={"target_id": "dev-1"}, headers=h)
    assert sp.status_code == 200 and "trust_score" in sp.json()["result"]


def test_auth_info_intent_eligible_matches_intent_gate():
    # 一致性：auth/info 的 intent_eligible 必须与 intent 第一道闸口径一致
    h = _hdr("elig_free")  # 免费裸账号
    info = client.get("/api/v1/auth/info", headers=h).json()
    assert info["intent_eligible"] is False
    assert client.post("/api/v1/intent", json={"text": "机器狗巡检"}, headers=h).json()["status"] == "rejected"
    # 升级 PRO 后两者同时变 True / dispatched
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=h)
    info2 = client.get("/api/v1/auth/info", headers=h).json()
    assert info2["intent_eligible"] is True
    assert client.post("/api/v1/intent", json={"text": "机器狗巡检"}, headers=h).json()["status"] == "dispatched"


def test_subscription_alone_does_not_grant_intent_eligibility():
    # 收紧后：仅 PRO/MAX 可发意图，小额订阅/套餐不再解锁
    r = client.post("/api/v1/subscribe", json={"account": "sub_no_intent",
                                               "capability_ids": ["network_diagnosis"],
                                               "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    assert client.get("/api/v1/auth/info", headers=h).json()["intent_eligible"] is False
    assert client.post("/api/v1/intent", json={"text": "机器狗巡检"}, headers=h).json()["status"] == "rejected"
    # 升级 PRO 后即可
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=h)
    assert client.post("/api/v1/intent", json={"text": "机器狗巡检"}, headers=h).json()["status"] == "dispatched"


def test_free_plan_cannot_submit_intent():
    # 第一道：免费套餐（无任何订阅）不支持意图编排 → NEF 不受理、不转发
    h = _hdr("plan_intent")
    r = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"}, headers=h).json()
    assert r["status"] == "rejected"
    assert r["auth"]["decision"] == "deny_authz"
    assert r["intent_id"] is None
    assert r["handoff"]["status"] == "rejected"


def test_subscriber_intent_authorized_per_capability_at_runtime():
    # 订阅套餐后可发起；第二道由网络侧 Planning Agent 在执行中逐能力鉴权
    r = client.post("/api/v1/subscribe", json={"account": "plan_intent_sub",
                                               "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=h)  # 仅 PRO/MAX 可发意图
    sub = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"}, headers=h).json()
    assert sub["status"] == "dispatched" and sub["intent_id"]
    INTENTS[sub["intent_id"]]["submitted_ts"] -= 20
    st = client.get(f"/api/v1/intent/{sub['intent_id']}", headers=h).json()
    assert st["status"] == "completed"
    assert st["network_authz"]["by"] == "网络侧 Planning Agent"
    assert st["network_authz"]["authorized_count"] >= 1


def test_scenario_run_accepts_params_and_fills_defaults():
    r = client.post("/api/v1/subscribe", json={"account": "scn_param",
                                               "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    # 传入 area，其余由后端用逼真默认值补齐
    res = client.post("/api/v1/scenarios/robot_patrol/run",
                      json={"params": {"area": "变电站-3号院"}}, headers=h).json()
    assert res["params"]["area"] == "变电站-3号院"
    assert res["dispatch"]["envelope"]["params"]["area"] == "变电站-3号院"
    # 未传的必填项被默认值补上，而非缺失（precision_location 的 device_id）
    assert res["params"].get("device_id")


def test_mcp_scenario_tool_exposes_param_schema():
    r = client.post("/api/v1/subscribe", json={"account": "scn_sch",
                                               "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    tools = client.post("/api/v1/mcp/tools/list", json={"jsonrpc": "2.0", "id": 1,
                                                        "method": "tools/list", "params": {}},
                        headers=h).json()["result"]["tools"]
    scen = next(t for t in tools if t["name"] == "scenario_robot_patrol")
    props = scen["inputSchema"]["properties"]
    assert "area" in props and props["area"].get("default")  # 预填默认值


def test_intent_status_carries_pa_placeholder():
    r = client.post("/api/v1/subscribe", json={"account": "pa_ph",
                                               "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    client.post("/api/v1/account/plan", json={"plan": "pro"}, headers=h)  # 仅 PRO/MAX 可发意图
    sub = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"}, headers=h).json()
    INTENTS[sub["intent_id"]]["submitted_ts"] -= 6  # 推进到 orchestrating 之后
    st = client.get(f"/api/v1/intent/{sub['intent_id']}", headers=h).json()
    assert st["pa"]["integrated"] is False  # 网络侧 PA 尚未对接，当前为模拟占位
    assert any(s.get("nf_tool") for s in st["pa"]["selected"])  # 标注各 Agent 选用的 NF Tool


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


def test_third_party_invoke_charges_caller_and_credits_provider():
    # BUG 修复：另一个 AF 调用第三方 tool 必须按次计费（之前第三方恒为 entitled → 不扣钱）
    owner = _hdr("tp_bill_owner")
    tp = client.post("/api/v1/register-af",
                     json={"name": "高精检测模型", "cap_type": "ai_model",
                           "endpoint": "https://b.example.com/api", "price": "0.8/次"},
                     headers=owner).json()["registration_id"]
    caller = client.post("/api/v1/register", json={"account": "tp_bill_caller"}).json()
    ch = {"Authorization": "Bearer " + caller["api_key"]}
    res = client.post(f"/api/v1/capabilities/{tp}/invoke", json={"payload": {}}, headers=ch).json()
    # 调用方被按次计费（0.8/次 → 0.8）
    assert res["billing"]["mode"] == "per_call" and res["billing"]["charged"] == 0.8
    info = client.get("/api/v1/auth/info", headers=ch).json()
    assert info["per_call_charges"]["count"] == 1 and info["per_call_charges"]["total"] == 0.8
    # 提供方收到一笔分成收益（北向调用记入反向台账）
    board = client.get("/api/v1/third-party/my-calls", headers=owner).json()
    cap = next(c for c in board["capabilities"] if c["id"] == tp)
    assert cap["call_count"] == 1 and cap["total_fee"] == 0.8
    assert cap["recent_calls"][0]["trigger"] == "north_invoke"


def test_third_party_monthly_requires_subscription_no_per_call():
    # 包月第三方能力：未订阅 → 402；订阅后调用不再按次扣费
    owner = _hdr("tp_monthly_owner")
    tp = client.post("/api/v1/register-af",
                     json={"name": "包月数据源", "endpoint": "https://m.example.com/api",
                           "price": "9.9/月"},
                     headers=owner).json()
    assert tp["billing_mode"] == "monthly"
    cid = tp["registration_id"]
    caller = client.post("/api/v1/register", json={"account": "tp_monthly_caller"}).json()
    ch = {"Authorization": "Bearer " + caller["api_key"]}
    # 未订阅 → 402
    r = client.post(f"/api/v1/capabilities/{cid}/invoke", json={"payload": {}}, headers=ch)
    assert r.status_code == 402
    # 订阅后 → 200 且不按次计费
    client.post("/api/v1/subscribe", json={"account": "tp_monthly_caller",
                                           "capability_ids": [cid], "package_ids": []})
    r2 = client.post(f"/api/v1/capabilities/{cid}/invoke", json={"payload": {}}, headers=ch).json()
    assert "billing" not in r2
    info = client.get("/api/v1/auth/info", headers=ch).json()
    assert info["per_call_charges"]["count"] == 0


def test_monthly_third_party_subscription_credits_provider_income():
    # 包月第三方能力：他人订阅后，提供方看板按「订阅人数 × 月价」显示月收入
    owner = _hdr("tp_inc_owner")
    tp = client.post("/api/v1/register-af",
                     json={"name": "包月路况源", "endpoint": "https://i.example.com/api",
                           "price": "9.9/月"},
                     headers=owner).json()["registration_id"]
    # 注册当下还没订阅 → 月收入 0
    board0 = client.get("/api/v1/third-party/my-calls", headers=owner).json()
    c0 = next(c for c in board0["capabilities"] if c["id"] == tp)
    assert c0["billing_mode"] == "monthly" and c0["subscriber_count"] == 0 and c0["total_fee"] == 0.0
    # 两个不同账号包月订阅
    client.post("/api/v1/subscribe", json={"account": "buyer_1", "capability_ids": [tp], "package_ids": []})
    client.post("/api/v1/subscribe", json={"account": "buyer_2", "capability_ids": [tp], "package_ids": []})
    board = client.get("/api/v1/third-party/my-calls", headers=owner).json()
    c = next(c for c in board["capabilities"] if c["id"] == tp)
    assert c["subscriber_count"] == 2 and c["total_fee"] == 19.8
    assert board["billing"]["total_subscribers"] == 2 and board["billing"]["gross_revenue"] == 19.8


def test_tool_dispatch_carries_sbi_target():
    # 调用去向：tool 级在鉴权回执里给出落到的 SBI 接口；不再暴露后台 service_id / 路由细节
    h = _hdr("sbi_acct", plan="max")
    res = client.post("/api/v1/capabilities/target_detection/invoke",
                      json={"area": "A"}, headers=h).json()
    assert "routing" not in res  # 不再向 AF 暴露内部路由表
    sbi = res["nef_auth"]["sbi_target"]
    assert sbi["kind"] == "sbi"
    assert any("Nsensf" in x for x in sbi["interfaces"])


def test_pipeline_run_via_rest_carries_auth_pipeline():
    # API 直调 pipeline 也要带 CAPIF 鉴权回执（修复"鉴权不太正常"）
    r = client.post("/api/v1/subscribe", json={"account": "pipe_auth",
                                               "capability_ids": ["target_detection", "ai_inference"],
                                               "package_ids": []})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    pid = client.post("/api/v1/compose", json={"name": "鉴权流水线",
                                               "steps": ["target_detection", "ai_inference"]},
                      headers=h).json()["id"]
    run = client.post(f"/api/v1/pipelines/{pid}/run", json={"params": {}}, headers=h).json()
    assert run["nef_auth"]["decision"] == "allow"
    assert len(run["nef_auth"]["pipeline"]) >= 6
