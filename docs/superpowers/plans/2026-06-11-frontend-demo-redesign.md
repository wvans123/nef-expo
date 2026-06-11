# 6G NEF Demo 前端优化实施计划（深空电信蓝换肤 + AF 反向调用）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 nef-expo 演示平台整体换肤为「深空电信蓝」，并新增「AF 反向调用」能力（网络内部调用 AF 注册的能力，Intent 联动 + 手动触发）。

**Architecture:** FastAPI 后端 + 无框架单文件前端 `static/index.html`，全部状态内存存储。新增 `registry.py` 模块承载第三方能力注册表与反向调用台账（避免 server.py ↔ intent.py 循环依赖）。规格见 `docs/superpowers/specs/2026-06-11-frontend-demo-redesign-design.md`。

**Tech Stack:** Python 3.10+ / FastAPI / pytest + httpx（测试）/ 原生 HTML+CSS+JS。

**运行环境注意:** Windows。命令以 PowerShell 形式给出；启动 demo 服务用 `python server.py`（端口 8000）。

---

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `registry.py` | 新建 | 第三方能力注册表（THIRD_PARTY / THIRD_PARTY_META）、反向调用台账（REVERSE_CALLS）、`record_reverse_call()`、cap_type→Agent 映射 |
| `stubs.py` | 修改 | `tp_` 前缀能力返回模拟 AF 响应 |
| `server.py` | 修改 | THIRD_PARTY 迁到 registry；register_af 支持 intent_keywords + owner；新增 simulate-call / my-calls 两个端点 |
| `intent.py` | 修改 | 匹配范围扩展到第三方能力；第三方步骤标记 reverse 并写台账 |
| `static/index.html` | 修改 | 全局换肤、超市 hero、AF 注册 Tab 重做、Intent 第三方步骤高亮 |
| `tests/test_registry.py` | 新建 | registry 单元测试 |
| `tests/test_reverse_api.py` | 新建 | 注册/模拟调用/台账/Intent 联动 API 测试 |
| `requirements.txt` | 修改 | 注明测试依赖 |
| `README.md` | 修改 | 新功能说明 + 重启状态清空提示 |

---

### Task 0: git 仓库初始化

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: git init 并写 .gitignore**

```powershell
git init
```

`.gitignore` 内容：

```
__pycache__/
*.pyc
.superpowers/
.claude/settings.local.json
.pytest_cache/
```

- [ ] **Step 2: 初始提交（现状入库，含设计文档）**

```powershell
git add -A
git commit -m "chore: initial commit of nef-expo demo with design spec"
```

---

### Task 1: 测试基础设施

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: 安装并声明测试依赖**

`requirements.txt` 改为：

```
fastapi
uvicorn

# dev/test
pytest
httpx
```

```powershell
pip install pytest httpx
```

- [ ] **Step 2: 写冒烟测试（验证 TestClient 跑通现有端点）**

`tests/test_smoke.py`：

```python
# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_capabilities_list():
    r = client.get("/api/v1/capabilities")
    assert r.status_code == 200
    assert r.json()["count"] >= 17
```

- [ ] **Step 3: 运行测试确认通过**

```powershell
python -m pytest tests/ -v
```

Expected: 1 passed（注意：tests 目录与 server.py 同级，从项目根目录运行）

- [ ] **Step 4: Commit**

```powershell
git add requirements.txt tests/test_smoke.py
git commit -m "test: add pytest infra and smoke test"
```

---

### Task 2: registry.py — 注册表与反向调用台账

**Files:**
- Create: `registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写失败测试**

`tests/test_registry.py`：

```python
# -*- coding: utf-8 -*-
import registry


def setup_function():
    registry.THIRD_PARTY.clear()
    registry.THIRD_PARTY_META.clear()
    registry.REVERSE_CALLS.clear()


def test_caller_agent_mapping():
    registry.THIRD_PARTY_META["tp_x"] = {"cap_type": "ai_model", "owner": "a", "endpoint": "http://x"}
    name, color = registry.caller_agent_for("tp_x")
    assert name == "Computing Agent"

    registry.THIRD_PARTY_META["tp_y"] = {"cap_type": "data_source", "owner": "a", "endpoint": "http://y"}
    assert registry.caller_agent_for("tp_y")[0] == "Data Agent"

    # 未知类型兜底 Data Agent
    registry.THIRD_PARTY_META["tp_z"] = {"cap_type": "unknown", "owner": "a", "endpoint": "http://z"}
    assert registry.caller_agent_for("tp_z")[0] == "Data Agent"


def test_record_reverse_call():
    registry.THIRD_PARTY_META["tp_x"] = {"cap_type": "ai_model", "owner": "a", "endpoint": "http://x"}
    rec = registry.record_reverse_call("tp_x", trigger="manual", trigger_detail="手动模拟")
    assert rec["caller_agent"] == "Computing Agent"
    assert rec["status"] == "success"
    assert rec["fee"] == 0.05
    assert 20 <= rec["latency_ms"] <= 80
    assert registry.REVERSE_CALLS["tp_x"] == [rec]
```

- [ ] **Step 2: 运行确认失败**

```powershell
python -m pytest tests/test_registry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'registry'`

- [ ] **Step 3: 实现 registry.py**

```python
# -*- coding: utf-8 -*-
"""第三方（AF 注册）能力注册表 + 反向调用台账。

server.py 与 intent.py 都依赖本模块，本模块只依赖 skills.py，避免循环导入。
"""
import random
import time

from skills import AGENTS

THIRD_PARTY = []        # list[Capability]，AF 注册进来的能力
THIRD_PARTY_META = {}   # cap_id -> {"cap_type", "endpoint", "owner", "registered_ts"}
REVERSE_CALLS = {}      # cap_id -> [record]

# 反向调用时由哪个域 Agent 出面调用（按能力类型映射）
_CAP_TYPE_AGENT = {"ai_model": "computing", "tool": "data", "data_source": "data"}

REVERSE_FEE = 0.05      # 每次反向调用的模拟计费（元）


def caller_agent_for(cap_id: str):
    """返回 (agent_name, agent_color)"""
    meta = THIRD_PARTY_META.get(cap_id, {})
    akey = _CAP_TYPE_AGENT.get(meta.get("cap_type"), "data")
    ag = AGENTS[akey]
    return ag["name"], ag["color"]


def record_reverse_call(cap_id: str, trigger: str, trigger_detail: str) -> dict:
    """写入一条反向调用台账并返回该记录。trigger: 'manual' | 'intent'"""
    agent_name, color = caller_agent_for(cap_id)
    rec = {
        "ts": time.time(),
        "caller_agent": agent_name,
        "agent_color": color,
        "trigger": trigger,
        "trigger_detail": trigger_detail,
        "latency_ms": random.randint(20, 80),
        "status": "success",
        "fee": REVERSE_FEE,
    }
    REVERSE_CALLS.setdefault(cap_id, []).append(rec)
    return rec
```

- [ ] **Step 4: 运行确认通过**

```powershell
python -m pytest tests/test_registry.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```powershell
git add registry.py tests/test_registry.py
git commit -m "feat: add third-party registry and reverse-call ledger"
```

---

### Task 3: stubs.py — 第三方能力模拟响应

**Files:**
- Modify: `stubs.py:16-23`
- Test: `tests/test_registry.py`（追加）

- [ ] **Step 1: 追加失败测试到 `tests/test_registry.py`**

```python
def test_third_party_stub():
    from stubs import invoke_stub
    out = invoke_stub("tp_abc12345", {"payload": {"image": "x.jpg"}})
    assert out["status"] == "success"
    assert out["result"]["provided_by"] == "third_party_af"
    assert out["result"]["echo_payload"] == {"payload": {"image": "x.jpg"}}
```

- [ ] **Step 2: 运行确认失败**

```powershell
python -m pytest tests/test_registry.py::test_third_party_stub -v
```

Expected: FAIL — KeyError `'provided_by'`（目前走 `_generic`）

- [ ] **Step 3: 修改 `stubs.py`**

`invoke_stub`（第 16-19 行）改为：

```python
def invoke_stub(cap_id: str, params: dict) -> dict:
    if cap_id.startswith("tp_"):
        fn = _third_party
    else:
        fn = _STUBS.get(cap_id, _generic)
    result = fn(params or {})
    return {"status": "success", "capability": cap_id, "timestamp": _ts(), "result": result}
```

在 `_generic` 函数后新增：

```python
def _third_party(p):
    return {"provided_by": "third_party_af",
            "af_task_id": _id("af"),
            "result": "AF 能力执行成功（由第三方端点返回，模拟）",
            "echo_payload": p}
```

- [ ] **Step 4: 运行全部测试确认通过**

```powershell
python -m pytest tests/ -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```powershell
git add stubs.py tests/test_registry.py
git commit -m "feat: simulated AF response for third-party capabilities"
```

---

### Task 4: server.py — 迁移 THIRD_PARTY、register_af 升级

**Files:**
- Modify: `server.py`（多处，见下）
- Test: `tests/test_reverse_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_reverse_api.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

```powershell
python -m pytest tests/test_reverse_api.py -v
```

Expected: FAIL —— registry.THIRD_PARTY 为空（server 仍用自己的局部 THIRD_PARTY），keywords 字段不存在

- [ ] **Step 3: 修改 server.py**

(a) 导入区（第 12-15 行附近）增加：

```python
from registry import (THIRD_PARTY, THIRD_PARTY_META, REVERSE_CALLS,
                      record_reverse_call)
```

(b) 删除第 23 行的局部定义 `THIRD_PARTY = []`（注意保留 API_KEYS / ACCOUNT_KEYS / PIPELINES）。

(c) `RegisterAfReq`（第 49-53 行）增加字段：

```python
class RegisterAfReq(BaseModel):
    name: str
    cap_type: str               # ai_model / tool / data_source
    description: str = ""
    endpoint: str
    intent_keywords: list[str] = []
```

(d) `register_af`（第 262-276 行）改为：

```python
@app.post("/api/v1/register-af")
def register_af(req: RegisterAfReq, authorization: str = Header(None)):
    key, rec = _auth(authorization)
    cap_id = "tp_" + uuid.uuid4().hex[:8]
    keywords = [k.strip() for k in req.intent_keywords if k.strip()] or [req.name]
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
```

其余引用 THIRD_PARTY 的端点（list_capabilities / get_capability / invoke_capability / mcp_tools_list / mcp_tools_call）无需改动——它们现在引用的是 registry 中的同一个列表对象。

- [ ] **Step 4: 运行全部测试确认通过**

```powershell
python -m pytest tests/ -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```powershell
git add server.py tests/test_reverse_api.py
git commit -m "feat: register-af with intent keywords, owner meta via registry"
```

---

### Task 5: server.py — simulate-call 与 my-calls 端点

**Files:**
- Modify: `server.py`（register_af 之后追加）
- Test: `tests/test_reverse_api.py`（追加）

- [ ] **Step 1: 追加失败测试**

追加到 `tests/test_reverse_api.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

```powershell
python -m pytest tests/test_reverse_api.py -v
```

Expected: 新增 4 个测试 FAIL（404 Not Found —— 端点不存在；注意 test_simulate_call_404_unknown 可能"假通过"，以其余 3 个为准）

- [ ] **Step 3: 在 server.py 的 register_af 之后追加两个端点**

```python
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
```

- [ ] **Step 4: 运行全部测试确认通过**

```powershell
python -m pytest tests/ -v
```

Expected: 11 passed

- [ ] **Step 5: Commit**

```powershell
git add server.py tests/test_reverse_api.py
git commit -m "feat: simulate-call and my-calls endpoints for reverse invocation"
```

---

### Task 6: intent.py — 第三方能力联动

**Files:**
- Modify: `intent.py`
- Test: `tests/test_reverse_api.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

```powershell
python -m pytest tests/test_reverse_api.py::test_intent_triggers_reverse_call -v
```

Expected: FAIL —— executions 中没有 third_party 步骤（intent 只匹配 CAPABILITIES）

- [ ] **Step 3: 修改 intent.py**

(a) 导入区改为：

```python
from skills import CAPABILITIES, PACKAGES, agent_for_capability
from stubs import invoke_stub
from registry import THIRD_PARTY, record_reverse_call, caller_agent_for
```

(b) `match_capabilities` 改为遍历全量：

```python
def match_capabilities(text: str):
    """关键词匹配，按相关度排序。返回 [(cap, score, hit_keywords)]"""
    scored = []
    for cap in CAPABILITIES + THIRD_PARTY:
        hits = [kw for kw in cap.intent_keywords if kw.lower() in text.lower()]
        if hits:
            scored.append((cap, len(hits), hits))
    scored.sort(key=lambda x: -x[1])
    return scored
```

(c) `process_intent` 中「Agent 分派计划」一段（第 55-66 行）改为——第三方能力用反向调用 Agent 映射并打标：

```python
    plan, agent_groups = [], {}
    for i, cap in enumerate(exec_caps, 1):
        if cap.source == "third_party":
            agent_name, agent_color = caller_agent_for(cap.id)
            step = {"step": i, "capability": cap.id, "capability_name": cap.name,
                    "agent": agent_name, "agent_key": "third_party",
                    "agent_color": agent_color,
                    "source": "third_party", "direction": "reverse",
                    "nf_tools": ["nef_outbound_gateway"]}
        else:
            akey, agent = agent_for_capability(cap.id)
            step = {"step": i, "capability": cap.id, "capability_name": cap.name,
                    "agent": agent["name"], "agent_key": akey, "agent_color": agent["color"],
                    "nf_tools": [t["tool"] for t in agent["nf_tools"][:2]]}
        plan.append(step)
        agent_groups.setdefault(step["agent"], []).append(cap.name)
```

(d) 执行循环（第 69-74 行）改为——`CAPABILITIES` 换成全量查找，第三方步骤执行后写台账：

```python
    executions = []
    for step in plan:
        cap = next(c for c in CAPABILITIES + THIRD_PARTY if c.id == step["capability"])
        params = {p.name: (p.default if p.default is not None else _demo_value(p)) for p in cap.params}
        result = invoke_stub(cap.id, params)
        if step.get("source") == "third_party":
            record_reverse_call(cap.id, trigger="intent", trigger_detail=text[:40])
        executions.append({**step, "params": params, "result": result})
```

- [ ] **Step 4: 运行全部测试确认通过**

```powershell
python -m pytest tests/ -v
```

Expected: 12 passed

- [ ] **Step 5: Commit**

```powershell
git add intent.py tests/test_reverse_api.py
git commit -m "feat: intent matching includes third-party caps with reverse-call ledger"
```

---

### Task 7: 前端 — 全局换肤（深空电信蓝）+ 超市 hero

**Files:**
- Modify: `static/index.html`（CSS `:root` 与若干样式规则、`loadMarket` 的 banner 部分）

- [ ] **Step 1: 替换 CSS 变量与基础样式**

`:root`（第 8-12 行）替换为：

```css
:root{
  --bg:#050b1f; --panel:#0a142e; --card:#0e1d3f; --border:#2a4a8a;
  --text:#eaf1ff; --muted:#8fa6d9; --accent:#39d2ff;
  --green:#39ffb0; --red:#ff6b6b; --orange:#ffc857; --purple:#bc8cff;
  --grad:linear-gradient(90deg,#1f6feb,#7048e8);
}
```

`body` 规则（第 14 行）的 `background:var(--bg)` 改为：

```css
body{background:linear-gradient(160deg,#050b1f 0%,#0a1733 55%,#06122b 100%) fixed;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5}
```

`pre`（第 16 行）背景色 `#0a0e14` 改为 `#081227`；`input,select,textarea`（第 24 行）背景色同样改为 `#081227`，边框色继承 `var(--border)` 不变。

`button.primary`（第 19-20 行）改为：

```css
button.primary{background:var(--grad);border-color:transparent;color:#fff}
button.primary:hover{filter:brightness(1.15)}
```

`#topbar`（第 28 行）改为玻璃拟态，`#topbar h1` 加渐变文字：

```css
#topbar{position:sticky;top:0;z-index:50;background:#0a142eb8;backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;gap:14px}
#topbar h1{font-size:16px;font-weight:700;background:linear-gradient(90deg,#7cc7ff,#bc8cff);-webkit-background-clip:text;background-clip:text;color:transparent}
```

`.card:hover`（第 47 行）改为青色辉光：

```css
.card:hover{border-color:#39d2ff88;box-shadow:0 0 16px #39d2ff2e;transform:translateY(-1px)}
```

`.cat-dot`（第 48 行）加微光：

```css
.cat-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px;box-shadow:0 0 6px currentColor}
```

新增 hero 样式（追加到 `.banner` 规则之后）：

```css
.hero-title{font-size:26px;font-weight:800;background:linear-gradient(90deg,#7cc7ff,#bc8cff);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero-sub{font-size:13px;color:var(--muted);margin-top:2px}
.method-chip{display:inline-block;border:1px solid #39d2ff55;color:var(--accent);border-radius:14px;padding:2px 12px;font-size:12px;margin-right:8px;background:#39d2ff0d}
```

- [ ] **Step 2: 升级超市 banner 为 hero**

`loadMarket()` 中 `$('#market-banner').innerHTML` 一段（第 309-314 行）替换为：

```javascript
  $('#market-banner').innerHTML = `
    <div style="flex:1 1 100%">
      <div class="hero-title">一张网络，无限调用</div>
      <div class="hero-sub">6G NEF 能力开放平台 —— 网络能力即服务，双向开放生态</div>
      <div style="margin-top:10px">
        <span class="method-chip">REST API</span>
        <span class="method-chip">MCP Tool</span>
        <span class="method-chip">Intent 意图</span>
        <span class="method-chip">Pipeline 编排</span>
        <span class="method-chip">↩ AF 反向开放</span>
      </div>
    </div>
    <div class="stat"><b>${CAPS.length}</b><span>项网络能力</span></div>
    <div class="stat"><b>3</b><span>种调用方式</span></div>
    <div class="stat"><b>${PKGS.length}</b><span>个场景套餐</span></div>
    <div class="stat"><span>API Key 状态</span><b style="font-size:13px" class="${apiKey()?'ok':'muted'}">${apiKey()?'已激活':'未订阅'}</b></div>`;
```

- [ ] **Step 3: 手动验证**

```powershell
python server.py
```

浏览器打开 http://localhost:8000 检查：
1. 整体深蓝渐变背景、顶栏玻璃拟态、平台名渐变文字
2. 超市页 hero 大标题 + 5 个调用方式徽标 + 统计数字
3. 逐个点开 8 个 Tab，确认表格/弹窗/输入框/pre 无白底穿帮、文字可读
4. 订阅流程跑一遍（注册账号 → 订阅套餐 → API 调试发一次请求）确认交互未破坏

- [ ] **Step 4: Commit**

```powershell
git add static/index.html
git commit -m "feat: deep-space telecom blue reskin with marketplace hero"
```

---

### Task 8: 前端 — AF 注册 Tab 重做（反向调用看板）

**Files:**
- Modify: `static/index.html`（pane-afreg 的 HTML、新增 CSS、新增/替换 JS）

- [ ] **Step 1: 新增反向链路与看板样式**

追加到 CSS（`.toast` 规则之前）：

```css
/* AF 反向调用 */
.afflow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:12px}
.afflow .afnode{border:1px solid var(--border);border-radius:8px;padding:5px 12px;background:var(--card);transition:.3s}
.afflow .afnode.af-end{border-color:#39ffb088;color:var(--green)}
.afflow .afnode.nef{border-color:#ffc85788;color:var(--orange)}
.afflow .afnode.lit{box-shadow:0 0 14px #39d2ff88;border-color:var(--accent);color:var(--accent)}
.afflow .afarrow{color:var(--muted);font-size:11px;text-align:center}
.afflow .afarrow small{display:block;font-size:9px}
.tp-card{background:var(--card);border:1px solid var(--border);border-left:4px solid var(--green);border-radius:8px;padding:12px 14px;margin:10px 0}
.tp-card .badge-found{font-size:10px;color:var(--green);border:1px solid #39ffb066;border-radius:8px;padding:0 6px;margin-left:6px}
.tp-card .badge-wait{font-size:10px;color:var(--muted);border:1px solid var(--border);border-radius:8px;padding:0 6px;margin-left:6px}
.tp-log{font-size:11px;background:#081227;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:8px;max-height:180px;overflow:auto}
.tp-log .row{margin:3px 0}
```

- [ ] **Step 2: 替换 pane-afreg 的 HTML**（第 222-235 行整段）：

```html
  <!-- Tab 8 AF 注册 -->
  <div class="tabpane" id="pane-afreg">
    <h3 class="sec">AF 能力注册 · 双向开放</h3>
    <p class="muted" style="max-width:760px;margin-bottom:14px">NEF 不仅将网络能力对外开放，外部 AF 也可以把自己的能力（AI 模型 / 工具 / 数据源）注册进网络。注册后能力上架能力超市，被网络内部 Agent <b>发现并反向调用</b> —— 调用经过 NEF 出向网关完成鉴权、计费与审计。</p>
    <div class="afflow" id="af-flow">
      <span class="afnode af-end" data-fn="0">AF 能力</span>
      <span class="afarrow">─注册─▶</span>
      <span class="afnode nef" data-fn="1">NEF 能力超市</span>
      <span class="afarrow">─发现─▶</span>
      <span class="afnode" data-fn="2">Planning Agent</span>
      <span class="afarrow">─编排─▶</span>
      <span class="afnode nef" data-fn="3">NEF 出向网关<small>鉴权·计费·审计</small></span>
      <span class="afarrow" style="color:var(--green)">─反向调用─▶</span>
      <span class="afnode af-end" data-fn="4">AF Endpoint</span>
    </div>
    <div style="display:grid;grid-template-columns:380px 1fr;gap:16px">
      <div>
        <h3 class="sec" style="margin-top:0">① 注册我的能力</h3>
        <label>能力名称</label><input id="af-name" placeholder="如：工业缺陷识别模型">
        <label>类型</label>
        <select id="af-type"><option value="ai_model">ai_model — AI 模型</option><option value="tool">tool — 工具</option><option value="data_source">data_source — 数据源</option></select>
        <label>描述</label><textarea id="af-desc" rows="2" placeholder="能力说明"></textarea>
        <label>Intent 关键词（逗号分隔，供网络语义调度命中）</label><input id="af-keywords" placeholder="如：质检, 缺陷">
        <label>端点 URL</label><input id="af-endpoint" placeholder="https://your-af.example.com/api/capability">
        <button class="primary" id="af-submit" style="margin-top:14px;width:100%">注册到 NEF</button>
        <div id="af-result" style="margin-top:14px"></div>
      </div>
      <div>
        <h3 class="sec" style="margin-top:0">② 我注册的能力 · 被网络调用看板</h3>
        <div id="af-board"><p class="muted">--</p></div>
      </div>
    </div>
  </div>
```

注意：`@media(max-width:900px)` 下该 grid 不会自动变单列，可接受（演示用宽屏）。

- [ ] **Step 3: 替换/新增 AF 相关 JS**（替换现有 `/* ===== AF 注册 ===== */` 整段，第 663-676 行）：

```javascript
/* ============ AF 注册 · 反向调用 ============ */
let afPollTimer = null, afTotalCalls = -1;

function lightFlow(){
  const nodes = $$('#af-flow .afnode');
  nodes.forEach((n,i)=>{
    setTimeout(()=>n.classList.add('lit'), i*220);
    setTimeout(()=>n.classList.remove('lit'), i*220+1400);
  });
}

function fmtTs(ts){ const d=new Date(ts*1000); return d.toTimeString().slice(0,8); }

async function loadAfBoard(){
  const el = $('#af-board');
  if(!apiKey()){ el.innerHTML = '<p class="muted">请先注册账号并订阅任意能力获得 API Key。</p>'; return; }
  try{
    const res = await api('/api/v1/third-party/my-calls');
    const total = res.capabilities.reduce((s,c)=>s+c.call_count,0);
    if(afTotalCalls >= 0 && total > afTotalCalls) lightFlow();   // 轮询发现新调用 → 点亮链路
    afTotalCalls = total;
    if(!res.capabilities.length){
      el.innerHTML = '<p class="muted">尚未注册任何能力。注册你的第一个能力，让网络发现并调用它 →</p>';
      return;
    }
    el.innerHTML = res.capabilities.map(c=>`
      <div class="tp-card">
        <b>${esc(c.name)}</b>
        ${c.discovered?'<span class="badge-found">✓ 已被网络发现</span>':'<span class="badge-wait">registered · 等待网络调用</span>'}
        <span class="mono muted" style="font-size:11px;margin-left:6px">${c.id}</span>
        <div class="kv" style="margin-top:6px">
          <b>被调用</b>${c.call_count} 次
          <b style="margin-left:12px">最近</b>${c.last_call_ts?fmtTs(c.last_call_ts):'--'}
          <b style="margin-left:12px">累计收益</b><span class="price">¥${c.total_fee.toFixed(2)}</span>
        </div>
        <button class="primary" style="margin-top:8px" onclick="simCall('${c.id}')">⚡ 模拟网络调用</button>
        ${c.recent_calls.length?`<div class="tp-log">${c.recent_calls.map(r=>`
          <div class="row">${fmtTs(r.ts)} <b style="color:${r.agent_color}">${esc(r.caller_agent)}</b>
          → 你的能力 <span class="ok">✓ ${r.latency_ms}ms</span>
          · ${r.trigger==='intent'?'Intent「'+esc(r.trigger_detail)+'」':'手动模拟'} · 计费 +${r.fee}</div>`).join('')}</div>`:''}
      </div>`).join('');
  }catch(e){ /* 轮询失败静默，保留上次内容，不打断演示 */ }
}

window.simCall = async id=>{
  try{
    await api(`/api/v1/third-party/${id}/simulate-call`,{method:'POST'});
    lightFlow();
    await loadAfBoard();
    toast('网络已调用你的能力');
  }catch(e){ toast(e.data?.detail||'调用失败', false); }
};

$('#af-submit').onclick = async ()=>{
  if(!apiKey()) return toast('注册 AF 能力需要 API Key，请先订阅任意能力', false);
  const kw = $('#af-keywords').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
  const body = {name:$('#af-name').value.trim(), cap_type:$('#af-type').value,
                description:$('#af-desc').value.trim(), endpoint:$('#af-endpoint').value.trim(),
                intent_keywords: kw};
  if(!body.name || !body.endpoint) return toast('名称和端点必填', false);
  try{
    const res = await api('/api/v1/register-af',{method:'POST',body:JSON.stringify(body)});
    $('#af-result').innerHTML = `<div class="agent-block" style="border-left-color:var(--green)">
      <b class="ok">✓ 注册成功</b> <span class="mono muted" style="font-size:11px">${res.registration_id}</span>
      <p class="muted" style="font-size:12px;margin-top:4px">已上架能力超市 · Intent 关键词：${res.intent_keywords.map(esc).join('、')}</p></div>`;
    loadMarket(); loadAfBoard();
  }catch(e){ $('#af-result').innerHTML = `<p class="err">${esc(jfmt(e.data||{}))}</p>`; }
};
```

- [ ] **Step 4: Tab 切换接入轮询**

Tab 切换处理（第 285-295 行）的回调内追加 afreg 分支与轮询管理，整段改为：

```javascript
$$('#tabs button').forEach(b => b.onclick = () => {
  $$('#tabs button').forEach(x=>x.classList.remove('active'));
  $$('.tabpane').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  $('#pane-'+b.dataset.tab).classList.add('active');
  if(afPollTimer){ clearInterval(afPollTimer); afPollTimer = null; }
  if(b.dataset.tab==='subs') renderSubs();
  if(b.dataset.tab==='api') renderApiTab();
  if(b.dataset.tab==='mcp') renderMcpTab();
  if(b.dataset.tab==='composer') renderComposer();
  if(b.dataset.tab==='skill') loadSkill();
  if(b.dataset.tab==='afreg'){ loadAfBoard(); afPollTimer = setInterval(loadAfBoard, 3000); }
});
```

- [ ] **Step 5: 手动验证**

```powershell
python server.py
```

1. 注册账号 + 订阅任意能力 → AF 注册 Tab：顶部链路图常驻、左表单右看板
2. 注册能力（名称"工业缺陷识别模型"，关键词"质检, 缺陷"）→ 右侧看板出现卡片（registered 徽章）
3. 点「⚡ 模拟网络调用」→ 链路节点逐个点亮 → 台账 +1、徽章变「✓ 已被网络发现」、收益 ¥0.05
4. 切到 Intent Tab 输入「帮我对产线做质检」发送 → 回到 AF Tab，3 秒内台账自动 +1 且链路点亮（触发源显示 Intent 文本）
5. 切走再切回，确认轮询无重复叠加（Network 面板每 3 秒仅一次 my-calls）

- [ ] **Step 6: Commit**

```powershell
git add static/index.html
git commit -m "feat: AF tab redesign with reverse-call board, flow animation, polling"
```

---

### Task 9: 前端 — Intent 结果第三方步骤高亮

**Files:**
- Modify: `static/index.html`（`renderIntentResult`，新增一个 CSS class）

- [ ] **Step 1: 新增徽章样式**（追加到 `.tp-log .row` 规则后）：

```css
.rev-badge{font-size:10px;color:var(--green);border:1px solid #39ffb066;border-radius:8px;padding:0 6px;margin-left:6px}
```

- [ ] **Step 2: 修改 `renderIntentResult` 的执行步骤模板**

`renderIntentResult` 中 `g.list.map(ex=>...)` 一段（第 524-529 行）改为：

```javascript
      ${g.list.map(ex=>`
        <div style="margin:8px 0">
          <b>Step ${ex.step} · ${esc(ex.capability_name)}</b> <span class="mono muted" style="font-size:11px">${ex.capability}</span>
          ${ex.source==='third_party'?'<span class="rev-badge">↩ 反向调用 AF 能力</span>':''}
          <span class="muted" style="font-size:11px"> · ${ex.source==='third_party'?'经 NEF 出向网关':'NF Tools: '+ex.nf_tools.join(', ')}</span>
          <pre style="margin-top:5px;max-height:200px">${esc(jfmt(ex.result))}</pre>
        </div>`).join('')}
```

- [ ] **Step 3: 手动验证**

注册带"质检"关键词的第三方能力后，Intent 输入「帮我对产线做质检」：
1. 执行结果中第三方步骤出现绿色「↩ 反向调用 AF 能力」徽章，旁注「经 NEF 出向网关」
2. 普通步骤仍显示 NF Tools 列表
3. 第三方步骤所在 agent-block 左边框为对应 Agent 颜色（ai_model → 紫色 Computing Agent）

- [ ] **Step 4: Commit**

```powershell
git add static/index.html
git commit -m "feat: highlight third-party reverse-call steps in intent results"
```

---

### Task 10: README 更新 + 全量回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README**

「快速体验」第 3 条之后追加一条：

```markdown
4. AF 反向调用：「AF 注册」Tab 注册能力（填 Intent 关键词如 `质检`）→ 点「⚡ 模拟网络调用」看链路点亮；或到 Intent Tab 输入含关键词的意图，回来看台账自动增长
```

「结构」代码块更新：

```
server.py   FastAPI 后端（REST + MCP + Intent + Pipeline + Skill 双文档 + 反向调用）
registry.py 第三方能力注册表 + 反向调用台账
skills.py   能力目录唯一数据源（17 能力 / 5 套餐 / Agent-NF Tool 映射）
stubs.py    能力调用模拟返回
intent.py   Intent → Skill → Agent → Tool 链路（含第三方能力反向调用）
static/index.html  单页前端（无框架，深空电信蓝主题）
tests/      pytest 冒烟与 API 测试
```

末尾「注意」一段补充：第三方注册能力与反向调用台账同样存于内存，重启后清空。

- [ ] **Step 2: 全量测试 + 手动回归**

```powershell
python -m pytest tests/ -v
```

Expected: 12 passed

手动按演示动线完整过一遍：超市 hero → 注册账号 → 订阅套餐 → 我的订阅 → API 调试 → MCP（list + call）→ Intent（普通意图 + 第三方联动意图）→ Skill 双视图 → 编排器（拖拽 + 执行）→ AF 注册（注册 + 手动模拟 + Intent 联动台账）。

- [ ] **Step 3: Commit**

```powershell
git add README.md
git commit -m "docs: README for reverse invocation and new theme"
```

---

## Self-Review 记录

- **Spec 覆盖**：换肤(§2)→Task 7；AF Tab 布局 A(§3)→Task 8；Intent 联动(§4)→Task 6+9；后端接口(§5)→Task 2-5；边界(§6)→Task 5 的 403/404 测试 + Task 8 轮询静默失败；验证(§7)→各 Task 手动步骤 + Task 10 回归。无缺口。
- **类型一致性**：record 字段（ts/caller_agent/agent_color/trigger/trigger_detail/latency_ms/status/fee）在 registry、my-calls 响应、前端渲染三处一致；`source`/`direction` 字段在 intent.py 与前端模板一致；`intent_keywords` 在 Pydantic 模型、register_af、前端 body 三处一致。
- **无占位符**：所有代码步骤均给出完整代码。
