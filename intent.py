# -*- coding: utf-8 -*-
"""Intent 意图解析与执行：文本 → 能力匹配 → Skill 匹配 → Agent 分派 → Tool 执行"""
from skills import CAPABILITIES, PACKAGES, agent_for_capability
from stubs import invoke_stub
from registry import THIRD_PARTY, record_reverse_call, caller_agent_for


def match_capabilities(text: str):
    """关键词匹配，按相关度排序。返回 [(cap, score, hit_keywords)]"""
    scored = []
    for cap in CAPABILITIES + THIRD_PARTY:
        hits = [kw for kw in cap.intent_keywords if kw.lower() in text.lower()]
        if hits:
            scored.append((cap, len(hits), hits))
    scored.sort(key=lambda x: -x[1])
    return scored


def match_package(matched_cap_ids):
    """若匹配能力中 ≥2 个属于同一套餐，识别为场景级调用"""
    best, best_overlap = None, 1
    for pkg in PACKAGES:
        overlap = len(set(pkg["capabilities"]) & set(matched_cap_ids))
        if overlap > best_overlap:
            best, best_overlap = pkg, overlap
    return best


def process_intent(text: str):
    matched = match_capabilities(text)
    pipeline = [
        {"stage": "nef_accept", "label": "NEF 受理", "detail": f"收到意图文本（{len(text)} 字符），完成鉴权与限流检查"},
        {"stage": "semantic_parse", "label": "语义解析",
         "detail": f"提取关键词，命中 {len(matched)} 个候选能力" if matched else "未命中任何能力关键词"},
    ]

    if not matched:
        return {"intent": text, "matched": False, "pipeline": pipeline,
                "message": "未能理解该意图，请尝试包含具体场景关键词（如：检测、定位、低时延、转码）",
                "executions": []}

    cap_ids = [c.id for c, _, _ in matched]
    pkg = match_package(cap_ids)

    if pkg:
        exec_caps = [c for c, _, _ in matched if c.id in pkg["capabilities"]]
        pipeline.append({"stage": "skill_match", "label": "Skill 匹配",
                         "detail": f"识别为场景级调用 → 匹配 Skill「{pkg['name']}」({pkg['id']})"})
    else:
        exec_caps = [matched[0][0]] + [c for c, s, _ in matched[1:] if s >= matched[0][1]]
        exec_caps = exec_caps[:3]
        pipeline.append({"stage": "skill_match", "label": "Skill 匹配",
                         "detail": "未命中场景套餐，按单能力调用执行"})

    # Agent 分派计划
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

    pipeline.append({"stage": "agent_dispatch", "label": "Agent 分派",
                     "detail": "Planning Agent 按 Skill 分派 → " +
                               "；".join(f"{a}: {', '.join(caps)}" for a, caps in agent_groups.items())})

    # 执行
    executions = []
    for step in plan:
        cap = next(c for c in CAPABILITIES + THIRD_PARTY if c.id == step["capability"])
        params = {p.name: (p.default if p.default is not None else _demo_value(p)) for p in cap.params}
        result = invoke_stub(cap.id, params)
        if step.get("source") == "third_party":
            record_reverse_call(cap.id, trigger="intent", trigger_detail=text[:40])
        executions.append({**step, "params": params, "result": result})

    pipeline.append({"stage": "tool_exec", "label": "Tool 执行",
                     "detail": f"各域 Agent 调用内部 NF Tool，共执行 {len(executions)} 步，全部成功"})
    pipeline.append({"stage": "aggregate", "label": "结果聚合", "detail": "NEF 聚合各 Agent 结果并返回 AF"})

    return {
        "intent": text, "matched": True,
        "scenario": pkg["name"] if pkg else None,
        "scenario_id": pkg["id"] if pkg else None,
        "matched_capabilities": [{"id": c.id, "name": c.name, "score": s, "keywords_hit": h}
                                 for c, s, h in matched],
        "pipeline": pipeline,
        "plan": plan,
        "executions": executions,
    }


def _demo_value(p):
    if p.enum:
        return p.enum[0]
    return {"string": "demo_" + p.name, "integer": 1, "number": 1.0,
            "array": [], "boolean": True}.get(p.type, "demo")
