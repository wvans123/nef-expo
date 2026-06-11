# -*- coding: utf-8 -*-
"""6G NEF 能力开放平台 — FastAPI 后端"""
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
from intent import process_intent
from registry import (THIRD_PARTY, THIRD_PARTY_META, REVERSE_CALLS,
                      record_reverse_call, caller_agent_for)

app = FastAPI(title="6G NEF Capability Exposure Platform", version="0.9.0-demo")

# ===== 内存存储（Demo 用途，无持久化） =====
API_KEYS = {}       # api_key -> {"account": str, "subscriptions": set, "packages": set, "created": ts}
ACCOUNT_KEYS = {}   # account -> api_key
PIPELINES = {}      # pipe_id -> pipeline def


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
def _auth(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少 Authorization: Bearer <api_key> 头")
    key = authorization.removeprefix("Bearer ").strip()
    rec = API_KEYS.get(key)
    if not rec:
        raise HTTPException(401, "无效的 API Key")
    return key, rec


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
    key, rec = _auth(authorization)
    cap = CAP_INDEX.get(cap_id) or next((c for c in THIRD_PARTY if c.id == cap_id), None)
    if not cap:
        raise HTTPException(404, f"能力 {cap_id} 不存在")
    if cap.status == "planned":
        raise HTTPException(403, f"能力 {cap_id} 规划中，暂未开放调用")
    if cap_id not in _subscribed_caps(rec) and cap.source != "third_party":
        raise HTTPException(403, f"账号 {rec['account']} 未订阅能力 {cap_id}")
    try:
        params = await request.json()
    except Exception:
        params = {}
    missing = [p.name for p in cap.params if p.required and p.name not in params]
    if missing:
        raise HTTPException(422, f"缺少必填参数: {', '.join(missing)}")
    return invoke_stub(cap_id, params)


# ===== 套餐 =====
@app.get("/api/v1/packages")
def list_packages():
    out = []
    for p in PACKAGES:
        out.append({**p, "capability_details": [CAP_INDEX[c].to_dict() for c in p["capabilities"]]})
    return {"count": len(out), "packages": out}


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
                         "packages": set(), "created": time.time()}
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
            "estimated_monthly_cost": round(est, 1)}


# ===== Intent =====
@app.post("/api/v1/intent")
def intent(req: IntentReq, authorization: str = Header(None)):
    _auth(authorization)
    return process_intent(req.text)


# ===== Pipeline 编排 =====
@app.post("/api/v1/compose")
def compose(req: ComposeReq, authorization: str = Header(None)):
    key, rec = _auth(authorization)
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
    key, rec = _auth(authorization)
    mine = [p for p in PIPELINES.values() if p["owner"] == rec["account"]]
    return {"count": len(mine), "pipelines": mine}


@app.post("/api/v1/pipelines/{pipe_id}/run")
def run_pipeline(pipe_id: str, authorization: str = Header(None)):
    key, rec = _auth(authorization)
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
    key, rec = _auth(authorization)
    subscribed = _subscribed_caps(rec)
    tools = [c.mcp_tool() for c in CAPABILITIES
             if c.id in subscribed and c.status == "available"]
    tools += [c.mcp_tool() for c in THIRD_PARTY]
    return {"jsonrpc": "2.0", "id": (req.id if req else 1), "result": {"tools": tools}}


@app.post("/api/v1/mcp/tools/call")
def mcp_tools_call(req: McpCallReq, authorization: str = Header(None)):
    key, rec = _auth(authorization)
    name = req.params.get("name")
    args = req.params.get("arguments", {})
    cap = CAP_INDEX.get(name) or next((c for c in THIRD_PARTY if c.id == name), None)
    if not cap:
        return {"jsonrpc": "2.0", "id": req.id,
                "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
    if name not in _subscribed_caps(rec) and cap.source != "third_party":
        return {"jsonrpc": "2.0", "id": req.id,
                "error": {"code": -32001, "message": f"未订阅 Tool: {name}"}}
    result = invoke_stub(name, args)
    import json as _json
    return {"jsonrpc": "2.0", "id": req.id,
            "result": {"content": [{"type": "text",
                                    "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                       "isError": False}}


# ===== AF 注册（双向开放） =====
@app.post("/api/v1/register-af")
def register_af(req: RegisterAfReq, authorization: str = Header(None)):
    key, rec = _auth(authorization)
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
    key, rec = _auth(authorization)
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
    key, rec = _auth(authorization)
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
    return {"count": len(out), "capabilities": out}


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
    """内部视图的 Agent 调度结构"""
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
           f"也可直接通过 Intent 接口用自然语言触发整个场景：`POST /api/v1/intent`。",
           ""]
    return "\n".join(md)


def build_internal_skill(pkg):
    """内部 Skill：面向 Planning Agent 的编排蓝图"""
    flow = agent_flow(pkg)
    md = [f"# Skill: {pkg['name']}（内部版 / Agent 编排蓝图）",
          "",
          f"> 触发条件：AF Intent 命中本场景，或 AF 显式调用套餐能力组合  ",
          f"> 编排者：Planning Agent（NEF 内）",
          "",
          "## 执行流程图",
          "",
          "```",
          "  AF (Intent/API/Tool)",
          "        │",
          "        ▼",
          "  ┌───────────┐",
          "  │    NEF    │ 鉴权 · 语义解析 · Skill 匹配",
          "  └─────┬─────┘",
          "        ▼",
          "  ┌──────────────┐",
          "  │ Planning Agent│ 按本 Skill 分派",
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
           "- 任一步骤失败：Planning Agent 重试 1 次，仍失败则向 AF 返回部分结果 + 失败原因",
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
