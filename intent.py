# -*- coding: utf-8 -*-
"""Intent handoff: NEF authenticates, accepts, forwards to the internal network
agent, and proxies status queries by intent_id (execution is simulated)."""
import random
import time
import uuid

from skills import CAPABILITIES, PACKAGES, agent_for_capability
from registry import THIRD_PARTY, INTENTS


PARTNER_AGENT_NAME = "网络内部 Network Agent"
PARTNER_INTENT_ENDPOINT = "https://network-agent.nef.internal/v1/intents"

# 异步执行各阶段的时间线（秒，自提交起算）—— 演示时可看到状态推进
STAGE_TIMELINE = [
    (0, "accepted", "已受理 · 已转交网络内部 Agent"),
    (2, "semantic_parsing", "Planning Agent 语义解析中（待对接·当前为 NEF 模拟）"),
    (5, "orchestrating", "业务编排 · Planning Agent 逐能力鉴权中"),
    (8, "executing", "业务 Agent 执行中（已授权能力）"),
    (12, "completed", "执行完成 · 回执已生成"),
]


def _plan_trace(text: str):
    """模拟网络内部 Agent 的编排结果：关键词→能力→（可选）场景套餐。
    注意：这是"内部侧"的模拟，NEF 本身仍只做受理与转交。"""
    scored = []
    for cap in CAPABILITIES + THIRD_PARTY:
        if cap.status != "available":
            continue
        hits = [kw for kw in cap.intent_keywords if kw.lower() in text.lower()]
        if hits:
            scored.append((cap, len(hits)))
    scored.sort(key=lambda x: -x[1])
    cap_ids = [c.id for c, _ in scored]
    best, best_key = None, (1, 0.0)
    for pkg in PACKAGES:
        overlap = len(set(pkg["capabilities"]) & set(cap_ids))
        key = (overlap, overlap / len(pkg["capabilities"]))
        if key > best_key:
            best, best_key = pkg, key
    if best:
        exec_ids = [c for c in best["capabilities"]]
        scenario = best["name"]
    elif scored:
        exec_ids = cap_ids[:3]
        scenario = None
    else:
        return None, []
    steps = []
    for i, cid in enumerate(exec_ids, 1):
        cap = next((c for c in CAPABILITIES + THIRD_PARTY if c.id == cid), None)
        if cap is None:
            continue
        if cap.source == "third_party":
            agent_name, color, nf_tools = "Data Agent", "#3fb950", []
        else:
            _, agent = agent_for_capability(cid)
            agent_name, color, nf_tools = agent["name"], agent["color"], agent.get("nf_tools", [])
        # 占位：该 Agent 落到哪个网元 NF Tool（待网络侧 PA/Agent 接入后替换为真实选择）
        nf_tool = nf_tools[i % len(nf_tools)]["tool"] if nf_tools else None
        steps.append({"step": i, "agent": agent_name, "agent_color": color,
                      "capability": cid, "name": cap.name, "nf_tool": nf_tool,
                      "latency_ms": random.randint(20, 80), "status": "ok"})
    return scenario, steps


def process_intent(text: str, auth: dict, entitled_ids=None) -> dict:
    """受理 + 转交，并登记任务供后续按 intent_id 查询状态。"""
    intent_id = "intent_" + uuid.uuid4().hex[:12]
    partner_task_id = "partner_task_" + uuid.uuid4().hex[:12]
    submitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    scenario, trace = _plan_trace(text)
    # 标注每步是否已授权（供第二道——网络侧 Planning Agent 在执行中逐能力鉴权使用）
    for step in trace:
        step["authorized"] = (entitled_ids is None) or (step["capability"] in entitled_ids)

    INTENTS[intent_id] = {
        "intent_id": intent_id, "text": text, "account": auth["account"],
        "task_id": partner_task_id, "submitted_ts": time.time(),
        "submitted_at": submitted_at, "scenario": scenario, "trace": trace,
    }

    # 第一道已过（在 server 端按套餐/等级判定）→ NEF 受理并转交；
    # 第二道（逐能力鉴权）不在此预先判定，交给网络侧 Planning Agent 在执行过程中反馈。
    pipeline = [
        {"stage": "auth_verify", "label": "NEF 受理鉴权（第一道）",
         "detail": f"账号 {auth['account']} 具备意图受理资格，NEF 已受理"},
        {"stage": "nef_accept", "label": "NEF 受理",
         "detail": f"已生成 Intent ID {intent_id} 与审计请求 ID {auth['request_id']}"},
        {"stage": "partner_route", "label": "转发网络 Agent",
         "detail": f"Intent 原文透传至{PARTNER_AGENT_NAME}；逐能力鉴权由其 Planning Agent 在执行中进行"},
        {"stage": "partner_accept", "label": "网络内部接收",
         "detail": f"网络内部任务 {partner_task_id} 已接收，可通过 Intent ID 查询执行状态"},
    ]

    return {
        "intent_id": intent_id,
        "intent": text,
        "status": "dispatched",
        "submitted_at": submitted_at,
        "auth": auth,
        "pipeline": pipeline,
        "handoff": {
            "status": "accepted",
            "partner_agent": PARTNER_AGENT_NAME,
            "endpoint": PARTNER_INTENT_ENDPOINT,
            "task_id": partner_task_id,
            "status_owner": "internal_network_agent",
            "status_endpoint": f"GET /api/v1/intent/{intent_id}",
            "message": "Intent 已转交网络内部 Network Agent 执行，逐能力鉴权由 Planning Agent 在执行中反馈，可随时按 Intent ID 查询状态。",
        },
    }


def intent_status(intent_id: str):
    """按 intent_id 查询执行状态：NEF 代理查询网络内部任务，状态随时间推进。"""
    rec = INTENTS.get(intent_id)
    if not rec:
        return None
    elapsed = time.time() - rec["submitted_ts"]
    status, label = STAGE_TIMELINE[0][1], STAGE_TIMELINE[0][2]
    for t, s, l in STAGE_TIMELINE:
        if elapsed >= t:
            status, label = s, l
    idx = [s for _, s, _ in STAGE_TIMELINE].index(status)
    progress = min(100, int(elapsed / STAGE_TIMELINE[-1][0] * 100))
    stages = [{"stage": s, "label": l,
               "state": "done" if i < idx else ("active" if i == idx else "pending")}
              for i, (_, s, l) in enumerate(STAGE_TIMELINE)]
    out = {
        "intent_id": intent_id, "text": rec["text"], "task_id": rec["task_id"],
        "submitted_at": rec["submitted_at"], "account": rec["account"],
        "status": status, "status_label": label, "progress": progress,
        "stages": stages, "partner_agent": PARTNER_AGENT_NAME,
    }
    if rec["trace"]:
        allowed = [s for s in rec["trace"] if s.get("authorized", True)]
        denied = [s for s in rec["trace"] if not s.get("authorized", True)]
        for d in denied:
            d["status"] = "denied"
        # ⚠ 占位：网络侧 Planning Agent 尚未对接。以下 PA 语义解析输出为 NEF 侧模拟，
        # 待网络侧把真实 PA 接入后，这里替换为其真实的"解析结果 + 各 Agent 选用的 NF Tool"。
        if idx >= 1:  # semantic_parsing 及以后
            out["pa"] = {
                "engine": "网络侧 Planning Agent（待对接）",
                "integrated": False,
                "note": "下列为 NEF 侧模拟占位；网络侧 PA 接入后替换为其真实语义解析与工具选择输出",
                "parsed_scenario": rec["scenario"],
                "selected": [{"capability": s["capability"], "name": s["name"],
                              "agent": s["agent"], "nf_tool": s.get("nf_tool")}
                             for s in rec["trace"]],
            }
        # 第二道鉴权由 Planning Agent 在编排/执行过程中逐能力进行（orchestrating 起可见）
        if idx >= 2:  # orchestrating 及以后
            out["network_authz"] = {
                "by": "网络侧 Planning Agent", "authorized_count": len(allowed),
                "denied_count": len(denied),
                "checks": [{"capability": s["capability"], "name": s["name"],
                            "authorized": s.get("authorized", True),
                            "reason": ("已授权（订阅 / 等级 / 第三方）" if s.get("authorized", True)
                                       else "未授权（未订阅且等级不足）")} for s in rec["trace"]],
            }
        if status == "completed":
            out["scenario"] = rec["scenario"]
            out["execution_trace"] = rec["trace"]
            out["summary"] = (f"识别为场景「{rec['scenario']}」，" if rec["scenario"] else "") + \
                f"Planning Agent 逐能力鉴权后执行：{len(allowed)} 个步骤成功" + \
                (f"；{len(denied)} 个步骤未授权被拒（未订阅/等级不足，订阅或升级后重试）" if denied else "，全部通过")
        elif status == "executing":
            done = max(1, len(allowed) // 2) if allowed else 0
            out["execution_trace"] = allowed[:done] + denied
            out["summary"] = f"Planning Agent 已鉴权并完成 {done}/{len(allowed)} 个已授权步骤" + \
                (f"；{len(denied)} 个未授权步骤被拒" if denied else "")
        elif status == "orchestrating":
            out["summary"] = f"Planning Agent 编排中并逐能力鉴权：{len(allowed)} 个可执行" + \
                (f"，{len(denied)} 个未授权将被拒" if denied else "")
    elif status == "completed":
        out["summary"] = "网络内部 Agent 未能从意图中识别出可执行业务，已返回澄清请求"
        out["status"] = "needs_clarification"
    return out
