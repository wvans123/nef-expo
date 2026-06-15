# -*- coding: utf-8 -*-
"""CAPIF 鉴权流水线 + NEF 路由分发表"""
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def _hdr(account, plan="free"):
    r = client.post("/api/v1/register", json={"account": account, "plan": plan})
    return {"Authorization": "Bearer " + r.json()["api_key"]}


def test_invoke_authorized_has_full_pipeline_allow():
    h = _hdr("pl_pro", plan="pro")  # basic 层免订阅
    r = client.post("/api/v1/capabilities/target_detection/invoke",
                    json={"area": "A"}, headers=h)
    assert r.status_code == 200
    na = r.json()["nef_auth"]
    codes = [s["code"] for s in na["pipeline"]]
    assert codes == ["access", "credential", "token", "invoker", "scope", "authz", "audit"]
    assert na["decision"] == "allow"
    assert all(s["status"] == "passed" for s in na["pipeline"])
    assert na["quota"]["limit"] == 120


def test_402_payload_carries_pipeline_with_authz_denied():
    h = _hdr("pl_free")  # free，未订阅
    r = client.post("/api/v1/capabilities/target_detection/invoke",
                    json={"area": "A"}, headers=h)
    assert r.status_code == 402
    na = r.json()["detail"]["nef_auth"]
    assert na["decision"] == "deny_authz"
    authz = next(s for s in na["pipeline"] if s["code"] == "authz")
    assert authz["status"] == "denied"
    # 审计仍然落账（结果：拒绝）
    audit = next(s for s in na["pipeline"] if s["code"] == "audit")
    assert audit["status"] == "passed"


def test_pay_per_call_passes_authz_and_routes_nef_ref():
    h = _hdr("pl_pay")
    r = client.post("/api/v1/capabilities/target_detection/invoke",
                    json={"area": "A", "_confirm_pay": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["nef_auth"]["decision"] == "allow"
    assert r.json()["routing"]["target"] == "nef-ref"
    assert r.json()["routing"]["tool_id"] == "target_detection"


def test_dispatch_table_tool_vs_backend_scenario():
    dt = client.get("/api/v1/dispatch-table").json()
    assert dt["summary"]["backend_scenarios"] == 3
    # 单个 tool 一律 NEF 参考回显
    assert all(t["target"] == "nef-ref" for t in dt["tools"])
    # 三个主推场景命中后台
    backend_ids = {s["id"] for s in dt["scenarios"] if s["target"] == "backend"}
    assert backend_ids == {"robot_patrol", "traffic_forecast_pkg", "uav_track"}


def test_scenario_run_dispatches_to_backend_service_id():
    r = client.post("/api/v1/subscribe", json={"account": "pl_scene",
                                               "capability_ids": [], "package_ids": ["robot_patrol"]})
    h = {"Authorization": "Bearer " + r.json()["api_key"]}
    sr = client.post("/api/v1/scenarios/robot_patrol/run", headers=h).json()
    assert sr["dispatch"]["target"] == "backend"
    assert sr["dispatch"]["service_id"] == "robot_patrol"
    assert sr["dispatch"]["envelope"]["service_id"] == "robot_patrol"
    # 鉴权回执含流水线
    assert sr["auth"]["decision"] == "allow"
    assert len(sr["auth"]["pipeline"]) == 7


def test_intent_carries_pipeline():
    h = _hdr("pl_intent")
    res = client.post("/api/v1/intent", json={"text": "机器狗巡检，雾天也要看得清"},
                      headers=h).json()
    assert res["auth"]["decision"] == "allow"
    assert [s["code"] for s in res["auth"]["pipeline"]][0] == "access"
