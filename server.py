# -*- coding: utf-8 -*-
"""6G NEF 能力开放平台 — FastAPI 后端"""
import random
import secrets
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
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


class IntentReq(BaseModel):
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


def _payment_required_payload(cap, channel: str) -> dict:
    price = _per_call_price(cap)
    return {
        "status": "payment_required",
        "capability": cap.id, "name": cap.name,
        "message": f"NEF 鉴权通过，但账号未订阅「{cap.name}」。请选择计费方式后重试。",
        "options": [
            {"type": "monthly", "price": cap.unit_price,
             "how": "POST /api/v1/subscribe 订阅后调用"},
            {"type": "per_call", "price": f"¥{price}/次",
             "how": ("再次调用并在参数中携带 \"_confirm_pay\": true（需主人确认授权）"
                     if channel == "REST" else
                     "在 arguments 中携带 \"_confirm_pay\": true 重新调用（需主人确认授权）")},
        ],
    }


def _bill_per_call(rec, cap, request_id):
    price = _per_call_price(cap)
    PER_CALL_BILLS.setdefault(rec["account"], []).append(
        {"capability": cap.id, "name": cap.name, "price": price,
         "ts": time.time(), "request_id": request_id})
    return price


def _subscribed_caps(rec) -> set:
    caps = set(rec["subscriptions"])
    for pid in rec["packages"]:
        caps |= set(PKG_INDEX[pid]["capabilities"])
    return caps


# ===== 能力目录 =====
@app.get("/api/v1/capabilities")
def list_capabilities():
    caps = [c.to_dict() for c in CAPABILITIES] + [c.to_dict() for c in THIRD_PARTY]
    return {"count": len(caps), "categories": CATEGORIES, "capabilities": caps}


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
    per_call_fee = None
    if cap_id not in _subscribed_caps(rec) and cap.source != "third_party":
        if not confirm_pay:
            raise HTTPException(402, _payment_required_payload(cap, "REST"))
        stamp = _auth_stamp(key, rec, "capabilities:invoke")
        per_call_fee = _bill_per_call(rec, cap, stamp["request_id"])
    missing = [p.name for p in cap.params if p.required and p.name not in params]
    if missing:
        raise HTTPException(422, f"缺少必填参数: {', '.join(missing)}")
    result = invoke_stub(cap_id, params)
    result["nef_auth"] = _auth_stamp(key, rec, "capabilities:invoke")
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
    auth = _auth_stamp(key, rec, "capabilities:invoke")
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
    pipeline = [
        {"stage": "auth_verify", "label": "NEF 鉴权",
         "detail": f"Bearer API Key 已验证，账号 {rec['account']} 已订阅场景「{pkg['name']}」"},
        {"stage": "nef_accept", "label": "NEF 受理",
         "detail": f"场景调用（{channel}）已受理，审计请求 ID {auth['request_id']}"},
        {"stage": "partner_route", "label": "转交网络 Agent",
         "detail": f"场景请求转交 网络内部 Network Agent，网络内部任务 {task_id}"},
        {"stage": "partner_execute", "label": "网络内部编排执行",
         "detail": f"网络内部 Network Agent 按场景 Skill 编排 {len(steps)} 个步骤并执行"},
        {"stage": "aggregate", "label": "回执返回",
         "detail": "NEF 将网络内部执行回执（含执行轨迹）返回 AF"},
    ]
    return {
        "scenario_id": pkg["id"], "scenario": pkg["name"],
        "status": "completed", "task_id": task_id,
        "partner_agent": "网络内部 Network Agent",
        "auth": auth, "pipeline": pipeline,
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


# ===== 订阅 / 鉴权 =====
@app.post("/api/v1/subscribe")
def subscribe(req: SubscribeReq):
    bad = [c for c in req.capability_ids if c not in CAP_INDEX]
    bad += [p for p in req.package_ids if p not in PKG_INDEX]
    if bad:
        raise HTTPException(404, f"不存在: {', '.join(bad)}")
    planned = [c for c in req.capability_ids if CAP_INDEX[c].status == "planned"]
    if planned:
        raise HTTPException(403, f"能力规划中，暂未开放订阅: {', '.join(planned)}")
    key = ACCOUNT_KEYS.get(req.account)
    if not key:
        key = "nef_" + secrets.token_hex(16)
        API_KEYS[key] = {"account": req.account, "subscriptions": set(),
                         "packages": set(), "scopes": set(DEFAULT_SCOPES),
                         "created": time.time()}
        ACCOUNT_KEYS[req.account] = key
    rec = API_KEYS[key]
    rec["subscriptions"] |= set(req.capability_ids)
    rec["packages"] |= set(req.package_ids)
    return {"account": req.account, "api_key": key,
            "subscriptions": sorted(rec["subscriptions"]),
            "packages": sorted(rec["packages"]),
            "message": "订阅成功，已生成 API Key" }


@app.get("/api/v1/auth/info")
def auth_info(authorization: str = Header(None)):
    key, rec = _auth(authorization)
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
            "per_call_charges": {
                "count": len(PER_CALL_BILLS.get(rec["account"], [])),
                "total": round(sum(b["price"] for b in PER_CALL_BILLS.get(rec["account"], [])), 2),
                "recent": PER_CALL_BILLS.get(rec["account"], [])[-5:][::-1],
            },
            "authentication": {
                **_auth_evidence(key, rec, "auth:info", "req_" + uuid.uuid4().hex[:12]),
                "scopes": sorted(rec.get("scopes", DEFAULT_SCOPES)),
            }}


# ===== Intent =====
@app.post("/api/v1/intent")
def intent(req: IntentReq, authorization: str = Header(None)):
    request_id = "req_" + uuid.uuid4().hex[:12]
    key, rec = _auth(authorization, required_scope="intent:submit")
    auth = _auth_evidence(key, rec, "intent:submit", request_id)
    return process_intent(req.text, auth)


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


# ===== Pipeline 编排 =====
@app.post("/api/v1/compose")
def compose(req: ComposeReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="pipeline:manage")
    bad = [s for s in req.steps if s not in CAP_INDEX]
    if bad:
        raise HTTPException(404, f"能力不存在: {', '.join(bad)}")
    unsub = [s for s in req.steps if s not in _subscribed_caps(rec)]
    if unsub:
        raise HTTPException(403, f"未订阅能力: {', '.join(unsub)}")
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


@app.post("/api/v1/pipelines/{pipe_id}/run")
def run_pipeline(pipe_id: str, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="pipeline:manage")
    pipe = PIPELINES.get(pipe_id)
    if not pipe:
        raise HTTPException(404, f"Pipeline {pipe_id} 不存在")
    results = []
    for i, cid in enumerate(pipe["steps"], 1):
        cap = CAP_INDEX[cid]
        params = {p.name: (p.default if p.default is not None else _demo_value(p))
                  for p in cap.params}
        akey, agent = agent_for_capability(cid)
        results.append({"step": i, "capability": cid, "capability_name": cap.name,
                        "agent": agent["name"], "params": params,
                        "result": invoke_stub(cid, params)})
    return {"pipeline_id": pipe_id, "name": pipe["name"],
            "status": "success", "steps_executed": len(results), "results": results}


def _demo_value(p: CapParam):
    if p.enum:
        return p.enum[0]
    return {"string": "demo_" + p.name, "integer": 1, "number": 1.0,
            "array": [], "boolean": True}.get(p.type, "demo")


# ===== MCP 模拟 =====
@app.post("/api/v1/mcp/tools/list")
def mcp_tools_list(req: McpCallReq = None, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="mcp:tools")
    subscribed = _subscribed_caps(rec)
    tools = []
    for c in CAPABILITIES:
        if c.status != "available":
            continue
        t = c.mcp_tool()
        if c.id not in subscribed:
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
                      "inputSchema": {"type": "object", "properties": {}, "required": []}})
    return {"jsonrpc": "2.0", "id": (req.id if req else 1), "result": {"tools": tools}}


@app.post("/api/v1/mcp/tools/call")
def mcp_tools_call(req: McpCallReq, authorization: str = Header(None)):
    key, rec = _auth(authorization, required_scope="mcp:tools")
    name = req.params.get("name")
    args = req.params.get("arguments", {})
    import json as _json
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
    per_call_fee = None
    if name not in _subscribed_caps(rec) and cap.source != "third_party":
        if not confirm_pay:
            payload = _payment_required_payload(cap, "MCP")
            return {"jsonrpc": "2.0", "id": req.id,
                    "result": {"content": [{"type": "text",
                                            "text": _json.dumps(payload, ensure_ascii=False, indent=2)}],
                               "isError": False, "payment_required": True}}
        stamp = _auth_stamp(key, rec, "mcp:tools")
        per_call_fee = _bill_per_call(rec, cap, stamp["request_id"])
    result = invoke_stub(name, args)
    result["nef_auth"] = _auth_stamp(key, rec, "mcp:tools")
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
        intent_keywords=keywords, unit_price="第三方计费", source="third_party",
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
