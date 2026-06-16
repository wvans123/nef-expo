# -*- coding: utf-8 -*-
"""6G NEF 能力开放平台 — FastAPI 后端"""
import os
import random
import secrets
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from skills import (CAPABILITIES, CAP_INDEX, PACKAGES, PKG_INDEX, CATEGORIES,
                    AGENTS, Capability, CapParam, agent_for_capability)
from stubs import invoke_stub
from intent import process_intent, intent_status
from registry import (THIRD_PARTY, THIRD_PARTY_META, REVERSE_CALLS,
                      record_reverse_call, caller_agent_for)

app = FastAPI(title="6G NEF Capability Exposure Platform", version="0.9.0-demo")

# ===== 内存存储（Demo 用途，无持久化） =====
API_KEYS = {}       # api_key -> {"account": str, "subscriptions": set, "packages": set, "created": ts}
ACCOUNT_KEYS = {}   # account -> api_key
PIPELINES = {}      # pipe_id -> pipeline def
PER_CALL_BILLS = {}  # account -> [ {capability, price, ts, request_id} ] 按次计费账单
PLAN_TIERS = {  # 账号等级 → 免订阅可直接使用的能力层级
    "free": set(),
    "pro": {"basic"},
    "max": {"basic", "advanced"},
}
DEFAULT_SCOPES = {
    "capabilities:invoke",
    "mcp:tools",
    "intent:submit",
    "pipeline:manage",
    "af:register",
}


# ===== 请求模型 =====
class SubscribeReq(BaseModel):
    account: str
    capability_ids: list[str] = []
    package_ids: list[str] = []
    plan: str = "free"


class PlanReq(BaseModel):
    plan: str


class IntentReq(BaseModel):
    text: str


class AfPlanReq(BaseModel):
    text: str


class ComposeReq(BaseModel):
    name: str
    steps: list[str]            # capability ids，按顺序


class McpCallReq(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = 1
    method: str = "tools/call"
    params: dict = {}


class RegisterAfReq(BaseModel):
    name: str
    cap_type: str               # ai_model / tool / data_source
    description: str = ""
    endpoint: str
    intent_keywords: list[str] = []
    price: str = "0.5/次"


# ===== 鉴权 =====
def _auth(authorization: str | None, required_scope: str | None = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少 Authorization: Bearer <api_key> 头")
    key = authorization.removeprefix("Bearer ").strip()
    rec = API_KEYS.get(key)
    if not rec:
        raise HTTPException(401, "无效的 API Key")
    scopes = rec.get("scopes", DEFAULT_SCOPES)
    if required_scope and required_scope not in scopes:
        raise HTTPException(403, f"API Key 缺少权限范围: {required_scope}")
    return key, rec


def _auth_evidence(key: str, rec: dict, scope: str, request_id: str) -> dict:
    masked_key = f"{key[:8]}...{key[-4:]}"
    return {
        "status": "verified",
        "scheme": "Bearer API Key",
        "account": rec["account"],
        "credential": masked_key,
        "scope": scope,
        "request_id": request_id,
        "checks": [
            {"step": "credential", "label": "凭证格式", "status": "passed",
             "detail": "已读取 Authorization: Bearer <api_key>"},
            {"step": "identity", "label": "身份识别", "status": "passed",
             "detail": f"API Key 对应账号 {rec['account']}"},
            {"step": "scope", "label": "权限范围", "status": "passed",
             "detail": f"已授权 {scope}"},
            {"step": "audit", "label": "审计追踪", "status": "passed",
             "detail": f"请求审计 ID: {request_id}"},
        ],
    }


def _auth_stamp(key: str, rec: dict, scope: str) -> dict:
    """附在调用结果上的精简鉴权回执，证明 NEF 对本次请求完成了鉴权"""
    return {
        "status": "verified",
        "scheme": "Bearer API Key",
        "account": rec["account"],
        "credential": f"{key[:8]}...{key[-4:]}",
        "scope": scope,
        "request_id": "req_" + uuid.uuid4().hex[:12],
    }


def _per_call_price(cap) -> float:
    """按次价格：从月价推一个演示用单次价"""
    try:
        monthly = float(str(cap.unit_price).split("/")[0])
        return max(0.5, round(monthly / 20, 1))
    except ValueError:
        return 0.5


def _payment_required_payload(cap, channel: str, pipeline: dict | None = None) -> dict:
    price = _per_call_price(cap)
    payload = {
        "status": "payment_required",
        "capability": cap.id, "name": cap.name,
        "message": f"身份认证通过，但未授权：账号未订阅「{cap.name}」且当前等级不含 {cap.tier} 层级。可订阅 / 升级账号 / 按次支付。",
        "options": [
            {"type": "monthly", "price": cap.unit_price,
             "how": "POST /api/v1/subscribe 订阅后调用"},
            {"type": "per_call", "price": f"¥{price}/次",
             "how": ("再次调用并在参数中携带 \"_confirm_pay\": true（确认支付后调用）"
                     if channel == "REST" else
                     "在 arguments 中携带 \"_confirm_pay\": true 重新调用（确认支付后调用）")},
        ],
    }
    if pipeline:
        payload["nef_auth"] = {"request_id": pipeline["request_id"], "decision": pipeline["decision"],
                               "pipeline": pipeline["stages"]}
    return payload


def _bill_per_call(rec, cap, request_id):
    price = _per_call_price(cap)
    PER_CALL_BILLS.setdefault(rec["account"], []).append(
        {"capability": cap.id, "name": cap.name, "price": price,
         "ts": time.time(), "request_id": request_id})
    return price


def _result_envelope(cap, payload: dict) -> dict:
    """NEF 标准结果信封：在原始业务数据之上加一行业务结论(summary)与关键指标(metrics)。
    真实对接时 summary/metrics 由业务侧按 schema 返回，NEF 透传；Demo 中由通用规则生成。"""
    res = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
    metrics, parts = {}, []
    for k, v in res.items():
        if isinstance(v, list) and v:
            parts.append(f"{k.replace('_', ' ')} {len(v)} 项")
            metrics[k + "_count"] = len(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            if k.endswith("_ms"):
                metrics[k] = v
                parts.append(f"{k} {v}ms")
            elif k.endswith(("_score", "_rate", "_mbps", "_pct")):
                metrics[k] = v
        elif isinstance(v, str) and k in ("served_at", "node", "state", "qos_class", "slice_id"):
            metrics[k] = v
    payload["summary"] = f"「{cap.name}」执行成功" + ("：" + "、".join(parts[:3]) if parts else "")
    payload["metrics"] = metrics
    return payload


def _subscribed_caps(rec) -> set:
    caps = set(rec["subscriptions"])
    for pid in rec["packages"]:
        caps |= set(PKG_INDEX[pid]["capabilities"])
    return caps


def _entitled(rec, cap) -> bool:
    """授权判定：已订阅，或账号等级（pro/max）覆盖该能力层级，或第三方能力"""
    if cap.source == "third_party":
        return True
    if cap.id in _subscribed_caps(rec):
        return True
    return cap.tier in PLAN_TIERS.get(rec.get("plan", "free"), set())


# ===== 路由分发：化解 tool 粒度 ↔ 后台场景粒度 的错配 =====
# 演示初值：后台同事按场景粒度交付，已声明实现的 service_id。
# 未列出的单个 tool / 场景由 NEF 参考回显兜底——NEF 绝不把后台未声明的 id 转发出去，
# 后台只会收到自己注册过的 service_id，靠它无歧义分发，不会收到"看不懂的 tool 请求"。
BACKEND_SERVICES = {
    "robot_patrol": "机器狗巡检-感知融合",
    "traffic_forecast_pkg": "城市车流量预测",
    "uav_track": "无人机识别追踪",
}


def _dispatch(kind: str, ident: str, params: dict | None = None, request_id: str = "") -> dict:
    """NEF 分发判定。kind: 'tool' | 'scenario'。
    返回落地目标 + 转发请求信封（后台靠 service_id 分发，无歧义）。"""
    if kind == "scenario" and ident in BACKEND_SERVICES:
        return {
            "target": "backend", "service_id": ident, "tool_id": None,
            "backend_name": BACKEND_SERVICES[ident],
            "note": f"命中后台 service_id「{ident}」→ NEF 出向转发并回传业务结果",
            "envelope": {"request_id": request_id, "service_id": ident,
                         "tool_id": None, "params": params or {}},
        }
    return {
        "target": "nef-ref",
        "service_id": ident if kind == "scenario" else None,
        "tool_id": ident if kind == "tool" else None,
        "backend_name": None,
        "note": "后台未声明实现 → NEF 参考回显（mock）；真实业务按契约接入即替换",
        "envelope": {"request_id": request_id,
                     "service_id": ident if kind == "scenario" else None,
                     "tool_id": ident if kind == "tool" else None, "params": params or {}},
    }


# ===== NEF 鉴权流水线（每次调用都逐级执行；用大白话讲得清） =====
# 依据 3GPP CAPIF（网络对调用方逐次鉴权）的思路，但只保留能一句话讲明白的步骤。
def _capif_pipeline(key, rec, *, scope, scope_ok=True, entitled=True, paid=False,
                    cap=None, request_id=None,
                    authz_label="判定能力授权", authz_pass_detail=None,
                    authz_deny_detail=None) -> dict:
    """逐级计算鉴权状态，供前端逐级点亮。decision: allow / deny_scope / deny_authz。
    authz_label / authz_pass_detail 用于定制最后一步语义（如意图的『受理鉴权』）。"""
    request_id = request_id or ("req_" + uuid.uuid4().hex[:12])
    acct, plan = rec["account"], rec.get("plan", "free").upper()
    masked = f"{key[:8]}…{key[-4:]}"
    stages = []

    def add(code, label, status, detail):
        stages.append({"seq": len(stages) + 1, "code": code, "label": label,
                       "status": status, "latency_ms": random.randint(1, 5), "detail": detail})

    def done(decision):
        return {"request_id": request_id, "decision": decision, "stages": stages}

    add("credential", "取出凭证", "passed", f"从请求头取出 API Key（Bearer {masked}）")
    add("validate", "校验密钥", "passed", "确认这把 Key 真实有效、未过期、未被吊销")
    add("identify", "识别身份", "passed", f"这把 Key 属于 AF 账号「{acct}」（等级 {plan}）")
    if not scope_ok:
        add("scope", "检查接口权限", "denied", f"该 Key 不允许调用这类接口（缺 scope：{scope}）")
        add("audit", "记录审计", "passed", f"写审计日志 {request_id}（结果：拒绝 · 接口权限不足）")
        return done("deny_scope")
    add("scope", "检查接口权限", "passed", f"该 Key 允许调用这类接口（scope：{scope}）")
    capname = cap.name if cap else "本次调用"
    if entitled:
        add("authorize", authz_label, "passed",
            authz_pass_detail or f"账号已获「{capname}」授权（订阅 / 账号等级 / 第三方）")
    elif paid:
        add("authorize", "判定能力授权", "passed", f"「{capname}」未订阅，已确认按次付费 → 准许本次调用")
    else:
        tier = getattr(cap, "tier", "?") if cap else "?"
        add("authorize", authz_label, "denied",
            authz_deny_detail or f"账号没订阅「{capname}」、等级也不含 {tier} 层 → 拒绝（可订阅 / 升级 / 按次付费）")
        add("audit", "记录审计", "passed", f"写审计日志 {request_id}（结果：拒绝 · 未授权）")
        return done("deny_authz")
    add("audit", "记录审计", "passed", f"写审计日志 {request_id}（记下谁/何时/调了什么/放行）")
    return done("allow")


def _nef_auth(key, rec, scope, pipeline, dispatch=None) -> dict:
    """挂在调用结果上的 NEF 鉴权回执：精简 stamp + 流水线 + 配额 + 路由（保留旧字段兼容）。"""
    out = {**_auth_stamp(key, rec, scope),
           "request_id": pipeline["request_id"], "decision": pipeline["decision"],
           "pipeline": pipeline["stages"]}
    if dispatch:
        out["dispatch"] = {"target": dispatch["target"], "service_id": dispatch["service_id"],
                           "backend_name": dispatch.get("backend_name"), "note": dispatch["note"]}
    return out


# ===== 能力目录 =====
@app.get("/api/v1/capabilities")
def list_capabilities():
    caps = [c.to_dict() for c in CAPABILITIES] + [c.to_dict() for c in THIRD_PARTY]
    return {"count": len(caps), "categories": CATEGORIES, "capabilities": caps}


@app.get("/api/v1/dispatch-table")
def dispatch_table():
    """NEF 路由分发表：每个暴露能力落地到 后台 service_id 或 NEF 参考回显。
    讲清 tool 粒度 ↔ 后台场景粒度 的错配如何在 NEF 这一层被消化。"""
    scenarios = []
    for pkg in PACKAGES:
        d = _dispatch("scenario", pkg["id"])
        scenarios.append({"id": pkg["id"], "name": pkg["name"], "kind": "scenario",
                          "target": d["target"], "service_id": d["service_id"],
                          "backend_name": d.get("backend_name"), "note": d["note"]})
    tools = []
    for c in CAPABILITIES:
        if c.status != "available":
            continue
        d = _dispatch("tool", c.id)
        tools.append({"id": c.id, "name": c.name, "kind": "tool",
                      "target": d["target"], "tier": c.tier, "note": d["note"]})
    backend_n = sum(1 for s in scenarios if s["target"] == "backend")
    return {"backend_services": BACKEND_SERVICES,
            "summary": {"scenarios": len(scenarios), "backend_scenarios": backend_n,
                        "tools": len(tools), "tools_nef_ref": len(tools)},
            "scenarios": scenarios, "tools": tools}


@app.get("/api/v1/capabilities/{cap_id}")
def get_capability(cap_id: str):
    cap = CAP_INDEX.get(cap_id) or next((c for c in THIRD_PARTY if c.id == cap_id), None)
    if not cap:
        raise HTTPException(404, f"能力 {cap_id} 不存在")
    if cap.source == "third_party":
        agent_name, _ = caller_agent_for(cap.id)
    else:
        akey, agent = agent_for_capability(cap.id)
        agent_name = agent["name"]
    return {**cap.to_dict(), "mcp_tool": cap.mcp_tool(),
            "internal_agent": agent_name,
            "rest_endpoint": f"POST /api/v1/capabilities/{cap.id}/invoke"}


@app.post("/api/v1/capabilities/{cap_id}/invoke")
async def invoke_capability(cap_id: str, request: Request, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="capabilities:invoke")
    cap = CAP_INDEX.get(cap_id) or next((c for c in THIRD_PARTY if c.id == cap_id), None)
    if not cap:
        raise HTTPException(404, f"能力 {cap_id} 不存在")
    if cap.status == "planned":
        raise HTTPException(403, f"能力 {cap_id} 规划中，暂未开放调用")
    try:
        params = await request.json()
    except Exception:
        params = {}
    confirm_pay = bool(params.pop("_confirm_pay", False))
    # 先做参数校验：调用失败（422）绝不计费
    missing = [p.name for p in cap.params if p.required and p.name not in params]
    if missing:
        raise HTTPException(422, f"缺少必填参数: {', '.join(missing)}")
    entitled = _entitled(rec, cap)
    pipeline = _capif_pipeline(key, rec, scope="capabilities:invoke",
                               entitled=entitled, paid=confirm_pay, cap=cap)
    request_id = pipeline["request_id"]
    per_call_fee = None
    if not entitled:
        if not confirm_pay:
            raise HTTPException(402, _payment_required_payload(cap, "REST", pipeline))
    dispatch = _dispatch("tool", cap_id, params, request_id)
    result = _result_envelope(cap, invoke_stub(cap_id, params))
    # 调用成功后才计费（按次）
    if not entitled and confirm_pay:
        per_call_fee = _bill_per_call(rec, cap, request_id)
    result["nef_auth"] = _nef_auth(key, rec, "capabilities:invoke", pipeline, dispatch)
    result["routing"] = dispatch
    if per_call_fee is not None:
        result["billing"] = {"mode": "per_call", "charged": per_call_fee,
                             "message": f"按次计费 ¥{per_call_fee}，已记入账号 {rec['account']} 账单"}
    return result


# ===== 套餐 =====
@app.get("/api/v1/packages")
def list_packages():
    out = []
    for p in sorted(PACKAGES, key=lambda x: not x.get("featured")):
        out.append({**p, "capability_details": [CAP_INDEX[c].to_dict() for c in p["capabilities"]]})
    return {"count": len(out), "packages": out}


# ===== 场景级一键调用（一个请求跑完整场景，网络内部 Agent 编排并回传执行轨迹） =====
def _scenario_run(pkg, key, rec, channel: str):
    pipeline = _capif_pipeline(key, rec, scope="capabilities:invoke", entitled=True, cap=None)
    request_id = pipeline["request_id"]
    dispatch = _dispatch("scenario", pkg["id"], {}, request_id)
    auth = _nef_auth(key, rec, "capabilities:invoke", pipeline, dispatch)
    task_id = "partner_task_" + uuid.uuid4().hex[:12]
    steps, n = [], 0
    for grp in agent_flow(pkg):
        for cap in grp["steps"]:
            n += 1
            steps.append({"step": n, "agent": grp["agent"], "agent_color": grp["color"],
                          "capability": cap["capability"], "name": cap["name"],
                          "latency_ms": random.randint(15, 60), "status": "ok",
                          "narrative": False})
    for s in pkg.get("story_steps", []):
        n += 1
        steps.append({"step": n, "agent": "网络内部 Network Agent", "agent_color": "#bc8cff",
                      "capability": None, "name": s["name"], "detail": s["detail"],
                      "latency_ms": None, "status": "ok", "narrative": True})
    if dispatch["target"] == "backend":
        route_detail = (f"命中后台 service_id「{pkg['id']}」（{dispatch['backend_name']}）→ "
                        f"NEF 出向转发，信封含 request_id/service_id，网络内部任务 {task_id}")
    else:
        route_detail = (f"后台未声明该场景 → NEF 参考回显（mock）编排执行，网络内部任务 {task_id}")
    biz_pipeline = [
        {"stage": "auth_verify", "label": "NEF 鉴权",
         "detail": f"CAPIF 流水线 7 级通过，账号 {rec['account']} 已订阅场景「{pkg['name']}」"},
        {"stage": "nef_accept", "label": "NEF 受理",
         "detail": f"场景调用（{channel}）已受理，审计请求 ID {request_id}"},
        {"stage": "partner_route", "label": "路由判定 · 转交网络 Agent",
         "detail": route_detail},
        {"stage": "partner_execute", "label": "网络内部编排执行",
         "detail": f"网络内部 Network Agent 按场景 Skill 编排 {len(steps)} 个步骤并执行"},
        {"stage": "aggregate", "label": "回执返回",
         "detail": "NEF 将网络内部执行回执（含执行轨迹）返回 AF"},
    ]
    return {
        "scenario_id": pkg["id"], "scenario": pkg["name"],
        "status": "completed", "task_id": task_id,
        "partner_agent": "网络内部 Network Agent",
        "auth": auth, "dispatch": dispatch, "pipeline": biz_pipeline,
        "execution_trace": steps,
        "total_latency_ms": sum(s["latency_ms"] or 0 for s in steps),
        "message": "场景由网络内部 Agent 编排执行，NEF 负责鉴权、受理、审计与回执转发。",
    }


@app.post("/api/v1/scenarios/{pkg_id}/run")
def run_scenario(pkg_id: str, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="capabilities:invoke")
    pkg = PKG_INDEX.get(pkg_id)
    if not pkg:
        raise HTTPException(404, f"场景 {pkg_id} 不存在")
    if pkg_id not in rec["packages"]:
        raise HTTPException(403, f"账号 {rec['account']} 未订阅场景套餐 {pkg_id}")
    return _scenario_run(pkg, key, rec, channel="REST")


@app.get("/api/v1/packages/{pkg_id}/skill")
def get_skill(pkg_id: str):
    pkg = PKG_INDEX.get(pkg_id)
    if not pkg:
        raise HTTPException(404, f"套餐 {pkg_id} 不存在")
    return {
        "package": pkg,
        "external_markdown": build_external_skill(pkg),
        "internal_markdown": build_internal_skill(pkg),
        "steps": skill_steps(pkg),
        "agent_flow": agent_flow(pkg),
    }


# ===== 账号注册 / 订阅 / 鉴权 =====
def _ensure_account(account: str, plan: str = "free") -> str:
    """注册即发凭证：账号不存在则创建并签发 API Key（订阅只记录权益）"""
    key = ACCOUNT_KEYS.get(account)
    if not key:
        key = "nef_" + secrets.token_hex(16)
        API_KEYS[key] = {"account": account, "subscriptions": set(),
                         "packages": set(), "scopes": set(DEFAULT_SCOPES),
                         "plan": plan if plan in PLAN_TIERS else "free",
                         "created": time.time()}
        ACCOUNT_KEYS[account] = key
    return key


@app.post("/api/v1/register")
def register_account(req: SubscribeReq):
    """开发者注册：立即签发 API Key（无需任何订阅，可按次调用或后续订阅）"""
    if not req.account.strip():
        raise HTTPException(422, "账号名称不能为空")
    existed = req.account in ACCOUNT_KEYS
    key = _ensure_account(req.account, req.plan)
    rec = API_KEYS[key]
    return {"account": req.account, "api_key": key, "plan": rec.get("plan", "free"),
            "scopes": sorted(rec["scopes"]),
            "message": ("账号已存在，返回现有 API Key" if existed else
                        "注册成功，已签发 API Key。订阅能力/套餐可包月计费，未订阅能力可按次付费调用")}


@app.post("/api/v1/account/plan")
def change_plan(req: PlanReq, authorization: str = Header(None)):
    """账号等级变更：free / pro（含 basic 层级）/ max（含 basic+advanced 层级）"""
    key, rec = _auth(authorization)
    if req.plan not in PLAN_TIERS:
        raise HTTPException(422, f"未知等级: {req.plan}（可选 free/pro/max）")
    rec["plan"] = req.plan
    tiers = sorted(PLAN_TIERS[req.plan])
    return {"account": rec["account"], "plan": req.plan,
            "included_tiers": tiers,
            "message": f"已切换至 {req.plan}，" + (("免订阅可用层级：" + "、".join(tiers)) if tiers else "所有能力均需订阅或按次付费")}


@app.post("/api/v1/subscribe")
def subscribe(req: SubscribeReq):
    tp_ids = {c.id for c in THIRD_PARTY}
    bad = [c for c in req.capability_ids if c not in CAP_INDEX and c not in tp_ids]
    bad += [p for p in req.package_ids if p not in PKG_INDEX]
    if bad:
        raise HTTPException(404, f"不存在: {', '.join(bad)}")
    planned = [c for c in req.capability_ids if c in CAP_INDEX and CAP_INDEX[c].status == "planned"]
    if planned:
        raise HTTPException(403, f"能力规划中，暂未开放订阅: {', '.join(planned)}")
    key = _ensure_account(req.account)
    rec = API_KEYS[key]
    rec["subscriptions"] |= set(req.capability_ids)
    rec["packages"] |= set(req.package_ids)
    return {"account": req.account, "api_key": key,
            "subscriptions": sorted(rec["subscriptions"]),
            "packages": sorted(rec["packages"]),
            "message": "订阅成功，权益已记录到账号（API Key 不变）"}


@app.get("/api/v1/auth/info")
def auth_info(authorization: str = Header(None)):
    key, rec = _auth(authorization)
    _pl = _capif_pipeline(key, rec, scope="auth:info", entitled=True, cap=None)
    caps = sorted(_subscribed_caps(rec))
    est = 0.0
    for cid in rec["subscriptions"]:
        price = CAP_INDEX[cid].unit_price
        if "/月" in price:
            try:
                est += float(price.split("/")[0])
            except ValueError:
                pass
    for pid in rec["packages"]:
        est += float(PKG_INDEX[pid]["price"].split("/")[0])
    return {"account": rec["account"], "api_key": key,
            "subscribed_capabilities": caps,
            "direct_subscriptions": sorted(rec["subscriptions"]),
            "packages": sorted(rec["packages"]),
            "estimated_monthly_cost": round(est, 1),
            "plan": rec.get("plan", "free"),
            "plan_included_tiers": sorted(PLAN_TIERS.get(rec.get("plan", "free"), set())),
            "entitled_capabilities": sorted([c.id for c in CAPABILITIES
                                             if c.status == "available" and _entitled(rec, c)]),
            "per_call_charges": {
                "count": len(PER_CALL_BILLS.get(rec["account"], [])),
                "total": round(sum(b["price"] for b in PER_CALL_BILLS.get(rec["account"], [])), 2),
                "recent": PER_CALL_BILLS.get(rec["account"], [])[-5:][::-1],
            },
            "authentication": {
                **_auth_evidence(key, rec, "auth:info", _pl["request_id"]),
                "scopes": sorted(rec.get("scopes", DEFAULT_SCOPES)),
                "pipeline": _pl["stages"], "decision": _pl["decision"],
            }}


# ===== Intent =====
@app.post("/api/v1/intent")
def intent(req: IntentReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="intent:submit")
    # 第一道：NEF 受理鉴权 —— 按套餐/等级判定能否发起意图。
    # 免费且无任何订阅的账号不支持意图编排（会触发网络侧多步编排，开销大）；
    # PRO/MAX 或已订阅能力/套餐的账号可发起。具体能用哪些 tool 留给第二道——
    # 由网络侧 Planning Agent 在执行过程中逐能力鉴权并反馈。
    can_submit = (rec.get("plan", "free") in ("pro", "max")
                  or bool(rec["subscriptions"]) or bool(rec["packages"]))
    pipeline = _capif_pipeline(
        key, rec, scope="intent:submit", entitled=can_submit, cap=None,
        authz_label="受理鉴权",
        authz_pass_detail="账号具备意图编排权限，准许发起；具体能力由网络侧 Planning Agent 在执行中逐项鉴权",
        authz_deny_detail="免费套餐不支持意图编排（意图触发网络侧多步编排，开销较大）。"
                          "请升级 PRO/MAX 或订阅能力/套餐；也可改用 API/MCP 单能力直调")
    request_id = pipeline["request_id"]
    auth = _auth_evidence(key, rec, "intent:submit", request_id)
    auth["pipeline"] = pipeline["stages"]
    auth["decision"] = pipeline["decision"]
    if pipeline["decision"] != "allow":   # 第一道未过：NEF 不受理、不转发
        return {
            "intent_id": None, "intent": req.text, "status": "rejected",
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "auth": auth,
            "pipeline": [{"stage": "auth_verify", "label": "NEF 受理鉴权（第一道）",
                          "detail": "免费套餐不支持意图编排，NEF 未受理"}],
            "handoff": {"status": "rejected", "partner_agent": "网络内部 Network Agent",
                        "task_id": None, "status_owner": "nef", "status_endpoint": None,
                        "message": "免费套餐不支持意图编排，请升级 PRO/MAX 或订阅能力/套餐后重试；"
                                   "也可改用 API 直调 / MCP 单能力调用。"},
        }
    entitled = {c.id for c in CAPABILITIES if c.status == "available" and _entitled(rec, c)}
    entitled |= {c.id for c in THIRD_PARTY}
    return process_intent(req.text, auth, entitled)


@app.get("/api/v1/intent/{intent_id}")
def get_intent_status(intent_id: str, authorization: str = Header(None)):
    """按 Intent ID 查询执行状态（NEF 代理查询网络内部任务）"""
    key, rec = _auth(authorization, required_scope="intent:submit")
    st = intent_status(intent_id)
    if not st:
        raise HTTPException(404, f"Intent {intent_id} 不存在（服务重启后任务记录会清空）")
    if st["account"] != rec["account"]:
        raise HTTPException(403, "只能查询本账号提交的 Intent")
    return st


# ===== AF Agent 规划（智能终端用：把用户的话映射到该调哪些 NEF 工具） =====
_META_PATTERNS = ["多少", "几个", "几种", "列出", "有哪些", "哪些", "都有什么", "有什么",
                  "能做什么", "可以做什么", "做什么", "做啥", "干什么", "能干", "支持哪些",
                  "能力", "功能", "本事", "你能", "你会", "会做", "会什么", "清单", "列表",
                  "菜单", "介绍", "帮助", "help", "工具列表", "tools", "怎么用"]


def _meta_answer():
    avail = [c for c in CAPABILITIES if c.status == "available"]
    by_cat = {}
    for c in avail:
        by_cat.setdefault(c.category, []).append(c)
    cat_summary = " · ".join(f"{CATEGORIES[k]['name']} {len(v)} 个" for k, v in by_cat.items())
    return {"mode": "meta", "plan": [],
            "answer": f"我的工具箱（NEF tools/list）共 {len(avail)} 个可用能力：{cat_summary}。",
            "examples": ["检测仓库里有没有异常物体", "预测早高峰的车流量",
                         "追踪这架无人机的位置", "把直播流转码卸载到边缘"]}


def _rule_plan(text: str, top=2):
    """规则规划：关键词命中打分，取前若干个能力（与意图/场景的匹配口径一致）。"""
    low = text.lower()
    scored = []
    for c in CAPABILITIES:
        if c.status != "available":
            continue
        hits = [kw for kw in c.intent_keywords if kw.lower() in low]
        if hits:
            scored.append((c, hits))
    scored.sort(key=lambda x: -len(x[1]))
    return [{"capability": c.id, "name": c.name, "reason": "命中关键词：" + "、".join(h)}
            for c, h in scored[:top]]


def _llm_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def _llm_plan(text: str):
    """可选 LLM 规划：把 NEF 可用能力当作 function-calling 的工具集喂给模型，
    让模型按用户原话选工具。仅在配置了 ANTHROPIC_API_KEY 且安装了 anthropic 时启用。"""
    import anthropic
    tools = []
    for c in CAPABILITIES:
        if c.status != "available":
            continue
        t = c.mcp_tool()
        tools.append({"name": c.id, "description": t["description"],
                      "input_schema": t.get("inputSchema", {"type": "object", "properties": {}})})
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-8", max_tokens=1024, tools=tools,
        tool_choice={"type": "any"},
        system=("你是 AF（第三方应用）的 AI Agent。用户会用自然语言描述需求，"
                "你只能通过调用下列 NEF 网络能力工具来满足需求。选择最合适的 1-3 个工具并给出参数。"),
        messages=[{"role": "user", "content": text}],
    )
    plan = []
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            cap = CAP_INDEX.get(block.name)
            if cap:
                plan.append({"capability": cap.id, "name": cap.name,
                             "reason": "LLM 选择（基于工具描述与你的需求）", "args": block.input or {}})
    return plan


@app.post("/api/v1/af-agent/plan")
def af_agent_plan(req: AfPlanReq, authorization: str = Header(None)):
    """AF 的 AI Agent 规划入口：把终端用户的话 → 该调哪些 NEF 工具。
    1) 元查询（问工具箱本身）直接作答；2) 规则匹配兜底；3) 配了 LLM 则用 LLM 基于 tools/list 选工具。"""
    key, rec = _auth(authorization, required_scope="mcp:tools")
    text = req.text.strip()
    low = text.lower()
    biz = _rule_plan(text)
    is_meta = any(p in low for p in _META_PATTERNS)
    # 业务没命中、但像是在问“你有什么能力 / 几个工具” → 直接列能力（元查询兜底）
    if not biz and is_meta:
        return _meta_answer()
    plan, mode = biz, "rule"
    if _llm_available():
        try:
            llm = _llm_plan(text)
            if llm:
                plan, mode = llm, "llm"
        except Exception:
            mode = "rule"
    if not plan:
        if is_meta:
            return _meta_answer()
        cats = "、".join(CATEGORIES[k]["name"] for k in CATEGORIES)
        return {"mode": mode, "plan": [],
                "suggestion": f"没匹配到能完成「{text}」的网络能力。我覆盖这些类别：{cats}；"
                              f"可试试含「检测 / 转码 / 车流量 / 追踪 / 定位 / 切片」等业务词的说法。",
                "examples": ["检测仓库里有没有异常物体", "预测早高峰的车流量", "追踪这架无人机的位置"]}
    return {"mode": mode, "plan": plan, "llm_enabled": _llm_available()}


# ===== Pipeline 编排 =====
@app.post("/api/v1/compose")
def compose(req: ComposeReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="pipeline:manage")
    bad = [s for s in req.steps if s not in CAP_INDEX]
    if bad:
        raise HTTPException(404, f"能力不存在: {', '.join(bad)}")
    unauth = [c for c in req.steps if not _entitled(rec, CAP_INDEX[c])]
    if unauth:
        raise HTTPException(403, f"未授权能力（未订阅且等级不足）: {', '.join(unauth)}")
    pid = "pipe_" + uuid.uuid4().hex[:8]
    PIPELINES[pid] = {"id": pid, "name": req.name, "steps": req.steps,
                      "owner": rec["account"], "created": time.time(),
                      "endpoint": f"POST /api/v1/pipelines/{pid}/run"}
    return PIPELINES[pid]


@app.get("/api/v1/pipelines")
def list_pipelines(authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="pipeline:manage")
    mine = [p for p in PIPELINES.values() if p["owner"] == rec["account"]]
    return {"count": len(mine), "pipelines": mine}


def _exec_pipeline(pipe):
    results = []
    for i, cid in enumerate(pipe["steps"], 1):
        cap = CAP_INDEX[cid]
        params = {p.name: (p.default if p.default is not None else _demo_value(p))
                  for p in cap.params}
        akey, agent = agent_for_capability(cid)
        results.append({"step": i, "capability": cid, "capability_name": cap.name,
                        "agent": agent["name"], "params": params,
                        "result": invoke_stub(cid, params)})
    return {"pipeline_id": pipe["id"], "name": pipe["name"],
            "status": "success", "steps_executed": len(results), "results": results}


@app.post("/api/v1/pipelines/{pipe_id}/run")
def run_pipeline(pipe_id: str, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="pipeline:manage")
    pipe = PIPELINES.get(pipe_id)
    if not pipe:
        raise HTTPException(404, f"Pipeline {pipe_id} 不存在")
    return _exec_pipeline(pipe)


def _demo_value(p: CapParam):
    if p.enum:
        return p.enum[0]
    return {"string": "demo_" + p.name, "integer": 1, "number": 1.0,
            "array": [], "boolean": True}.get(p.type, "demo")


# ===== MCP 模拟 =====
@app.post("/api/v1/mcp/tools/list")
def mcp_tools_list(req: McpCallReq = None, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="mcp:tools")
    tools = []
    for c in CAPABILITIES:
        if c.status != "available":
            continue
        t = c.mcp_tool()
        if not _entitled(rec, c):
            t["description"] = f"[未订阅 · {c.unit_price} 或 ¥{_per_call_price(c)}/次] " + t["description"]
            t["subscribed"] = False
        else:
            t["subscribed"] = True
        tools.append(t)
    tools += [c.mcp_tool() for c in THIRD_PARTY]
    for pid in sorted(rec["packages"]):
        pkg = PKG_INDEX[pid]
        tools.append({"name": f"scenario_{pid}",
                      "description": f"一键运行场景「{pkg['name']}」：{pkg['description']}（网络内部 Agent 编排执行并回传执行轨迹）",
                      "inputSchema": {"type": "object", "properties": {}, "required": []},
                      "subscribed": True})
    for pipe in PIPELINES.values():
        if pipe["owner"] == rec["account"]:
            tools.append({"name": f"pipeline_{pipe['id']}",
                          "description": f"运行自助编排 Pipeline「{pipe['name']}」：按序执行 {' → '.join(pipe['steps'])}",
                          "inputSchema": {"type": "object", "properties": {}, "required": []},
                          "subscribed": True})
    return {"jsonrpc": "2.0", "id": (req.id if req else 1), "result": {"tools": tools}}


@app.post("/api/v1/mcp/tools/call")
def mcp_tools_call(req: McpCallReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="mcp:tools")
    name = req.params.get("name")
    args = req.params.get("arguments", {})
    import json as _json
    if name and name.startswith("pipeline_"):
        pipe = PIPELINES.get(name[len("pipeline_"):])
        if not pipe or pipe["owner"] != rec["account"]:
            return {"jsonrpc": "2.0", "id": req.id,
                    "error": {"code": -32001, "message": f"Pipeline 不存在或不属于当前账号: {name}"}}
        result = _exec_pipeline(pipe)
        result["nef_auth"] = _auth_stamp(key, rec, "mcp:tools")
        return {"jsonrpc": "2.0", "id": req.id,
                "result": {"content": [{"type": "text",
                                        "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                           "isError": False}}
    if name and name.startswith("scenario_"):
        pid = name[len("scenario_"):]
        pkg = PKG_INDEX.get(pid)
        if not pkg or pid not in rec["packages"]:
            return {"jsonrpc": "2.0", "id": req.id,
                    "error": {"code": -32001, "message": f"未订阅场景 Tool: {name}"}}
        result = _scenario_run(pkg, key, rec, channel="MCP")
        return {"jsonrpc": "2.0", "id": req.id,
                "result": {"content": [{"type": "text",
                                        "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                           "isError": False}}
    cap = CAP_INDEX.get(name) or next((c for c in THIRD_PARTY if c.id == name), None)
    if not cap:
        return {"jsonrpc": "2.0", "id": req.id,
                "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
    confirm_pay = bool(args.pop("_confirm_pay", False))
    entitled = _entitled(rec, cap)
    pipeline = _capif_pipeline(key, rec, scope="mcp:tools",
                               entitled=entitled, paid=confirm_pay, cap=cap)
    request_id = pipeline["request_id"]
    per_call_fee = None
    if not entitled and not confirm_pay:
        payload = _payment_required_payload(cap, "MCP", pipeline)
        return {"jsonrpc": "2.0", "id": req.id,
                "result": {"content": [{"type": "text",
                                        "text": _json.dumps(payload, ensure_ascii=False, indent=2)}],
                           "isError": False, "payment_required": True}}
    dispatch = _dispatch("tool", name, args, request_id)
    result = _result_envelope(cap, invoke_stub(name, args))
    if not entitled and confirm_pay:   # 调用成功后才计费
        per_call_fee = _bill_per_call(rec, cap, request_id)
    result["nef_auth"] = _nef_auth(key, rec, "mcp:tools", pipeline, dispatch)
    result["routing"] = dispatch
    if per_call_fee is not None:
        result["billing"] = {"mode": "per_call", "charged": per_call_fee,
                             "message": f"按次计费 ¥{per_call_fee}，已记入账号 {rec['account']} 账单"}
    return {"jsonrpc": "2.0", "id": req.id,
            "result": {"content": [{"type": "text",
                                    "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                       "isError": False}}


# ===== AF 注册（双向开放） =====
@app.post("/api/v1/register-af")
def register_af(req: RegisterAfReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="af:register")
    if not req.name.strip():
        raise HTTPException(422, "能力名称不能为空")
    cap_id = "tp_" + uuid.uuid4().hex[:8]
    keywords = [k.strip() for k in req.intent_keywords if k.strip()] or [req.name.strip()]
    cap = Capability(
        id=cap_id, name=req.name, description=req.description or f"第三方能力（{req.cap_type}）",
        category="ecosystem", tier="basic",
        params=[CapParam("payload", "object", "透传给第三方端点的参数")],
        intent_keywords=keywords, unit_price=(req.price.strip() or "0.5/次"), source="third_party",
    )
    THIRD_PARTY.append(cap)
    THIRD_PARTY_META[cap_id] = {"cap_type": req.cap_type, "endpoint": req.endpoint,
                                "owner": rec["account"], "registered_ts": time.time()}
    return {"registration_id": cap_id, "name": req.name, "cap_type": req.cap_type,
            "endpoint": req.endpoint, "registered_by": rec["account"],
            "intent_keywords": keywords, "state": "registered",
            "message": "能力已注册，已出现在能力超市（third_party 标记），可被网络 Agent 发现和调用"}


@app.post("/api/v1/third-party/{cap_id}/simulate-call")
def simulate_reverse_call(cap_id: str, authorization: str = Header(None)):
    """手动模拟一次「网络内部 Agent 反向调用 AF 能力」"""
    key, rec = _auth(authorization, required_scope="af:register")
    meta = THIRD_PARTY_META.get(cap_id)
    if not meta:
        raise HTTPException(404, f"第三方能力 {cap_id} 不存在")
    if meta["owner"] != rec["account"]:
        raise HTTPException(403, f"能力 {cap_id} 不属于账号 {rec['account']}")
    record = record_reverse_call(cap_id, trigger="manual", trigger_detail="手动模拟网络调用")
    request_payload = {"payload": {"source": "nef_outbound_gateway",
                                   "caller": record["caller_agent"],
                                   "task_ref": "demo_task"}}
    return {"record": record,
            "request_payload": request_payload,
            "response_payload": invoke_stub(cap_id, request_payload)}


@app.get("/api/v1/third-party/my-calls")
def my_reverse_calls(authorization: str = Header(None)):
    """当前账号注册的第三方能力 + 各自反向调用台账"""
    key, rec = _auth(authorization, required_scope="af:register")
    out = []
    for cap in THIRD_PARTY:
        meta = THIRD_PARTY_META.get(cap.id, {})
        if meta.get("owner") != rec["account"]:
            continue
        calls = REVERSE_CALLS.get(cap.id, [])
        out.append({
            "id": cap.id, "name": cap.name,
            "cap_type": meta.get("cap_type"), "endpoint": meta.get("endpoint"),
            "call_count": len(calls),
            "last_call_ts": calls[-1]["ts"] if calls else None,
            "total_fee": round(sum(c["fee"] for c in calls), 2),
            "discovered": bool(calls),
            "recent_calls": list(reversed(calls[-10:])),
        })
    gross = round(sum(c["total_fee"] for c in out), 2)
    return {"count": len(out), "capabilities": out,
            "billing": {"total_calls": sum(c["call_count"] for c in out),
                        "gross_revenue": gross,
                        "revenue_share": "70% 归 AF / 30% 归运营商",
                        "af_income": round(gross * 0.7, 2)}}


# ===== 内部发现端点（面向网络内部 Agent / 网元，信任域内免 AF 鉴权） =====
@app.post("/internal/mcp")
async def internal_mcp(request: Request):
    """网络内部 Agent 的能力发现与调用入口（第二个 MCP Server，对内）。
    内部 Agent / 网元通过 tools/list 发现第三方 AF 注册的能力（含端点、定价、提供方），
    通过 tools/call 经 NEF 出向网关反向调用，并自动登记台账与计费。
    生产形态下此接口部署在信任域内（或由内部网元代理查询），Demo 中直接开放。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "需要 JSON-RPC 请求体")
    method, rid = body.get("method"), body.get("id")
    import json as _json
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": body.get("params", {}).get("protocolVersion", "2025-03-26"),
                           "capabilities": {"tools": {"listChanged": True}},
                           "serverInfo": {"name": "6g-nef-internal-discovery", "version": "0.9.0-demo"},
                           "instructions": "面向网络内部 Agent 的第三方能力目录：tools 为外部 AF 注册的能力，调用经 NEF 出向网关（鉴权·计费·审计）。"}}
    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "tools/list":
        tools = []
        for c in THIRD_PARTY:
            meta = THIRD_PARTY_META.get(c.id, {})
            t = c.mcp_tool()
            t["description"] = (f"[第三方 AF 能力 · 提供方 {meta.get('owner','?')} · {c.unit_price} · "
                                f"endpoint {meta.get('endpoint','?')}] ") + t["description"]
            tools.append(t)
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}
    if method == "tools/call":
        params = body.get("params", {})
        name, args = params.get("name"), params.get("arguments", {})
        caller = args.pop("_caller", "Network Agent")
        meta = THIRD_PARTY_META.get(name)
        if not meta:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"第三方能力不存在: {name}"}}
        record = record_reverse_call(name, trigger="internal_mcp",
                                     trigger_detail=f"内部发现调用 · {caller}")
        result = invoke_stub(name, args)
        result["reverse_call"] = {"via": "NEF 出向网关", "caller_agent": record["caller_agent"],
                                  "latency_ms": record["latency_ms"], "fee": record["fee"]}
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text",
                                        "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                           "isError": False}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not supported: {method}"}}


# ===== 标准 MCP 端点（streamable HTTP，可被 Claude Code / Codex 等直连） =====
@app.post("/mcp")
async def mcp_endpoint(request: Request, authorization: str = Header(None)):
    """最小 MCP Server：initialize / tools/list / tools/call（JSON-RPC over HTTP）。
    外部 AI Agent 配置示例：
      claude mcp add --transport http nef http://localhost:8000/mcp \
        --header "Authorization: Bearer <api_key>"
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "需要 JSON-RPC 请求体")
    method, rid = body.get("method"), body.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": body.get("params", {}).get("protocolVersion", "2025-03-26"),
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": "6g-nef-exposure", "version": "0.9.0-demo"},
                           "instructions": "6G NEF 能力开放平台：tools 即网络能力（通感/通算/连接等）。未订阅工具调用会返回计费提醒，携 _confirm_pay=true 按次付费执行。"}}
    if method in ("notifications/initialized", "ping"):
        if method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        return Response(status_code=202)
    if method == "tools/list":
        return mcp_tools_list(McpCallReq(id=rid or 1), authorization)
    if method == "tools/call":
        return mcp_tools_call(McpCallReq(id=rid or 1, params=body.get("params", {})), authorization)
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not supported: {method}"}}


# ===== Skill 双文档生成 =====
def skill_steps(pkg):
    steps = []
    for i, cid in enumerate(pkg["capabilities"], 1):
        cap = CAP_INDEX[cid]
        akey, agent = agent_for_capability(cid)
        steps.append({
            "step": i, "capability": cid, "name": cap.name,
            "description": cap.description,
            "rest_endpoint": f"POST /api/v1/capabilities/{cid}/invoke",
            "mcp_tool": cid,
            "params": [p.to_dict() for p in cap.params],
            "agent": agent["name"], "agent_key": akey, "agent_color": agent["color"],
            "nf_tools": agent["nf_tools"],
        })
    return steps


def agent_flow(pkg):
    """网络内部视图的 Agent 调度结构"""
    groups = {}
    for i, cid in enumerate(pkg["capabilities"], 1):
        akey, agent = agent_for_capability(cid)
        g = groups.setdefault(akey, {"agent": agent["name"], "color": agent["color"],
                                     "nf_tools": agent["nf_tools"], "steps": []})
        g["steps"].append({"step": i, "capability": cid, "name": CAP_INDEX[cid].name})
    return list(groups.values())


def _params_table(cap):
    rows = ["| 参数 | 类型 | 必填 | 说明 |", "|---|---|---|---|"]
    for p in cap.params:
        rows.append(f"| `{p.name}` | {p.type} | {'是' if p.required else '否'} | {p.description} |")
    return "\n".join(rows)


def _example_params(cap):
    import json
    d = {}
    for p in cap.params:
        d[p.name] = p.default if p.default is not None else (p.enum[0] if p.enum else _demo_value(p))
    return json.dumps(d, ensure_ascii=False, indent=2)


def build_external_skill(pkg):
    """外部 Skill：面向 AF 的 API/Tool 调用指南"""
    md = [f"# Skill: {pkg['name']}（外部版 / AF 调用指南）",
          "",
          f"> 场景：{pkg['scenario']}  ",
          f"> 套餐价格：{pkg['price']}  ",
          f"> 调用方式：REST API / MCP Tool（二选一，效果等价）",
          "",
          "## 前置条件",
          "",
          "1. 已订阅本套餐并获得 API Key（`nef_` 开头）",
          "2. 所有请求携带请求头：`Authorization: Bearer <api_key>`",
          "",
          "## 编排流程",
          "",
          "```",
          "  " + "  →  ".join(f"[{i}] {CAP_INDEX[c].name}" for i, c in enumerate(pkg["capabilities"], 1)),
          "```",
          ""]
    for i, cid in enumerate(pkg["capabilities"], 1):
        cap = CAP_INDEX[cid]
        md += [f"## Step {i}: {cap.name} (`{cid}`)",
               "",
               cap.description,
               "",
               f"- **REST 端点**: `POST /api/v1/capabilities/{cid}/invoke`",
               f"- **MCP Tool**: `{cid}`",
               "",
               "### 参数 Schema",
               "",
               _params_table(cap),
               "",
               "### Python 示例（REST）",
               "",
               "```python",
               "import requests",
               f'resp = requests.post(',
               f'    "https://nef.example.com/api/v1/capabilities/{cid}/invoke",',
               '    headers={"Authorization": f"Bearer {API_KEY}"},',
               f'    json={_example_params(cap)}',
               ')',
               "print(resp.json())",
               "```",
               "",
               "### MCP JSON-RPC 示例",
               "",
               "```json",
               '{',
               '  "jsonrpc": "2.0", "id": ' + str(i) + ', "method": "tools/call",',
               f'  "params": {{"name": "{cid}", "arguments": {_example_params(cap)}}}',
               '}',
               "```",
               ""]
    md += ["## 编排建议",
           "",
           f"按上述顺序依次调用。前一步的输出（如 target_id、task_id）可作为后一步的输入参数。",
           "如使用 `POST /api/v1/intent`，NEF 仅完成鉴权、受理和转发；具体场景编排由网络内部 Network Agent 负责。",
           ""]
    return "\n".join(md)


def build_internal_skill(pkg):
    """网络内部 Skill：面向网络内部 Agent 的编排蓝图"""
    flow = agent_flow(pkg)
    md = [f"# Skill: {pkg['name']}（网络内部 / Agent 编排蓝图）",
          "",
          f"> 触发条件：网络内部 Network Agent 接收 NEF 转发的 Intent，或 AF 显式调用套餐能力组合  ",
          f"> 编排者：网络内部 Network Agent（NEF 信任域内的网络 Agent 体系）",
          "",
          "## 执行流程图",
          "",
          "```",
          "  AF (Intent/API/Tool)",
          "        │",
          "        ▼",
          "  ┌───────────┐",
          "  │    NEF    │ 鉴权 · 受理 · 审计 · 路由",
          "  └─────┬─────┘",
          "        ▼",
          "  ┌──────────────┐",
          "  │ Partner Agent │ 语义理解 · 按本 Skill 分派",
          "  └─────┬────────┘"]
    for g in flow:
        md.append(f"        ├──▶ {g['agent']}: " +
                  ", ".join(f"[{s['step']}]{s['name']}" for s in g["steps"]))
    md += ["        ▼",
           "   结果聚合 → 返回 AF",
           "```",
           "",
           "## Agent 职责与 NF Tool 映射",
           ""]
    for g in flow:
        md += [f"### {g['agent']}",
               "",
               "**分配步骤**：" + "、".join(f"Step {s['step']} {s['name']} (`{s['capability']}`)"
                                            for s in g["steps"]),
               "",
               "**可调用 NF Tool（SBI 映射）**：",
               "",
               "| NF Tool | SBI Interface |",
               "|---|---|"]
        md += [f"| `{t['tool']}` | {t['sbi']} |" for t in g["nf_tools"]]
        md.append("")
    md += ["## Agent 间依赖关系",
           ""]
    caps = pkg["capabilities"]
    for i in range(1, len(caps)):
        prev, cur = CAP_INDEX[caps[i - 1]], CAP_INDEX[caps[i]]
        _, pa = agent_for_capability(prev.id)
        _, ca = agent_for_capability(cur.id)
        md.append(f"- Step {i} **{prev.name}**（{pa['name']}）输出 → Step {i+1} **{cur.name}**（{ca['name']}）输入")
    md += ["",
           "## 异常处理",
           "",
           "- 任一步骤失败：网络内部 Agent 重试 1 次，仍失败则向 AF 返回部分结果 + 失败原因",
           "- QoS 类步骤失败不阻断感知/计算类步骤（弱依赖）",
           ""]
    return "\n".join(md)


# ===== 静态文件 =====
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
