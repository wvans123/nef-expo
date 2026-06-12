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
INTENTS = {}            # intent_id -> 受理登记（供状态查询，演示用内存态）

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
    calls = REVERSE_CALLS.setdefault(cap_id, [])
    calls.append(rec)
    del calls[:-500]   # demo 内存保护：每能力最多保留 500 条
    return rec
