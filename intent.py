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
    (2, "semantic_parsing", "网络内部 Agent 语义解析中"),
    (5, "orchestrating", "业务编排中 · 选择业务 Agent 与 NF Tool"),
    (8, "executing", "业务 Agent 执行中"),
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
            agent_name, color = "Data Agent", "#3fb950"
        else:
            _, agent = agent_for_capability(cid)
            agent_name, color = agent["name"], agent["color"]
        steps.append({"step": i, "agent": agent_name, "agent_color": color,
                      "capability": cid, "name": cap.name,
                      "latency_ms": random.randint(20, 80), "status": "ok"})
    return scenario, steps


def process_intent(text: str, auth: dict, entitled_ids=None) -> dict:
    """受理 + 转交，并登记任务供后续按 intent_id 查询状态。"""
    intent_id = "intent_" + uuid.uuid4().hex[:12]
    partner_task_id = "partner_task_" + uuid.uuid4().hex[:12]
    submitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    scenario, trace = _plan_trace(text)
    for step in trace:
        step["authorized"] = (entitled_ids is None) or (step["capability"] in entitled_ids)

    # 第二道：网络侧业务鉴权 —— 意图解析出的每个能力逐项按订阅/等级判定
    authz_checks = [{"capability": s["capability"], "name": s["name"],
                     "authorized": s["authorized"],
                     "reason": ("已授权（订阅 / 等级 / 第三方）" if s["authorized"]
                                else "未授权（未订阅且等级不足）")}
                    for s in trace]
    n_auth = sum(1 for s in trace if s["authorized"])
    # 解析出能力、但一个都没授权 → NEF 不予转发（挡住白嫖/网络过载）
    rejected = bool(trace) and n_auth == 0

    INTENTS[intent_id] = {
        "intent_id": intent_id, "text": text, "account": auth["account"],
        "task_id": partner_task_id, "submitted_ts": time.time(),
        "submitted_at": submitted_at, "scenario": scenario, "trace": trace,
        "rejected": rejected,
    }

    network_authz = {
        "layer": "network", "label": "网络侧业务鉴权（第二道）",
        "decision": "rejected" if rejected else "forwarded",
        "authorized_count": n_auth, "denied_count": len(trace) - n_auth,
        "checks": authz_checks,
        "detail": (f"解析出 {len(trace)} 个能力，{n_auth} 个已授权、{len(trace) - n_auth} 个未授权"
                   if trace else "未从意图中解析出可执行能力"),
    }

    if rejected:
        pipeline = [
            {"stage": "auth_verify", "label": "NEF 受理鉴权（第一道）",
             "detail": f"账号 {auth['account']} 具备 intent:submit 权限，准许发起意图"},
            {"stage": "network_authz", "label": "网络侧业务鉴权（第二道）",
             "detail": f"解析出 {len(trace)} 个能力均未授权，NEF 不予转发（请订阅 / 升级后重试）"},
        ]
        return {
            "intent_id": intent_id, "intent": text, "status": "rejected",
            "submitted_at": submitted_at, "auth": auth, "pipeline": pipeline,
            "network_authz": network_authz,
            "handoff": {
                "status": "rejected", "partner_agent": PARTNER_AGENT_NAME,
                "endpoint": PARTNER_INTENT_ENDPOINT, "task_id": None,
                "status_owner": "nef", "status_endpoint": None,
                "message": "意图解析出的能力均未授权，NEF 未转发网络 Agent。订阅相关能力 / 套餐或升级账号等级后重试。",
            },
        }

    pipeline = [
        {"stage": "auth_verify", "label": "NEF 受理鉴权（第一道）",
         "detail": f"账号 {auth['account']} 具备 intent:submit 权限，准许发起意图"},
        {"stage": "nef_accept", "label": "NEF 受理",
         "detail": f"已生成 Intent ID {intent_id} 与审计请求 ID {auth['request_id']}"},
        {"stage": "network_authz", "label": "网络侧业务鉴权（第二道）",
         "detail": network_authz["detail"] + ("；未授权步骤将被拒绝执行" if network_authz["denied_count"] else "")},
        {"stage": "partner_route", "label": "转发网络 Agent",
         "detail": f"Intent 原文透传至{PARTNER_AGENT_NAME}，NEF 不做语义解析和业务执行"},
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
        "network_authz": network_authz,
        "handoff": {
            "status": "accepted",
            "partner_agent": PARTNER_AGENT_NAME,
            "endpoint": PARTNER_INTENT_ENDPOINT,
            "task_id": partner_task_id,
            "status_owner": "internal_network_agent",
            "status_endpoint": f"GET /api/v1/intent/{intent_id}",
            "message": "Intent 已转交网络内部 Network Agent 执行，可随时按 Intent ID 查询状态。",
        },
    }


def intent_status(intent_id: str):
    """按 intent_id 查询执行状态：NEF 代理查询网络内部任务，状态随时间推进。"""
    rec = INTENTS.get(intent_id)
    if not rec:
        return None
    if rec.get("rejected"):
        return {
            "intent_id": intent_id, "text": rec["text"], "task_id": None,
            "submitted_at": rec["submitted_at"], "account": rec["account"],
            "status": "rejected", "status_label": "网络侧鉴权未通过 · NEF 未转发",
            "progress": 100, "stages": [], "partner_agent": PARTNER_AGENT_NAME,
            "summary": f"解析出 {len(rec['trace'])} 个能力均未授权，NEF 未转发（订阅 / 升级后重试）",
            "execution_trace": [{**s, "status": "denied"} for s in rec["trace"]],
        }
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
        if status == "completed":
            out["scenario"] = rec["scenario"]
            out["execution_trace"] = rec["trace"]
            out["summary"] = (f"识别为场景「{rec['scenario']}」，" if rec["scenario"] else "") + \
                f"{len(allowed)} 个业务步骤执行成功" + \
                (f"；{len(denied)} 个步骤未授权被拒绝（未订阅/等级不足，订阅或升级后重试）" if denied else "，全部成功")
        elif status == "executing":
            done = max(1, len(allowed) // 2) if allowed else 0
            out["execution_trace"] = allowed[:done] + denied
            out["summary"] = f"已完成 {done}/{len(allowed)} 个已授权业务步骤" + \
                (f"；{len(denied)} 个步骤未授权" if denied else "")
    elif status == "completed":
        out["summary"] = "网络内部 Agent 未能从意图中识别出可执行业务，已返回澄清请求"
        out["status"] = "needs_clarification"
    return out
