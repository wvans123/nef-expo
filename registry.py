# -*- coding: utf-8 -*-
"""第三方（AF 注册）能力注册表 + 反向调用台账。

server.py 与 intent.py 都依赖本模块，本模块只依赖 skills.py，避免循环导入。
"""
import random
import time

from skills import AGENTS

THIRD_PARTY = []        # list[Capability]，AF 注册进来的能力
THIRD_PARTY_META = {}   # cap_id -> {"cap_type", "endpoint", "owner", "registered_ts", "billing_mode"}
THIRD_PARTY_SUBS = {}   # cap_id -> set(订阅方账号)：包月第三方能力的订阅方，用于结算月收入
REVERSE_CALLS = {}      # cap_id -> [record]
INTENTS = {}            # intent_id -> 受理登记（供状态查询，演示用内存态）

# 第三方能力的反向调用统一由"网络侧 Agent"经内部 MCP（模仿网元 tools/call）发起，
# 不再按 cap_type 武断映射到某个域 Agent（cap_type 只用于内部归类，不决定谁来调）。
NETWORK_CALLER = ("网络侧 Network Agent", "#bc8cff")

REVERSE_FEE = 0.05      # 每次反向调用的模拟计费（元）


def caller_agent_for(cap_id: str):
    """返回反向调用方 (agent_name, agent_color)：统一为网络侧 Agent（经内部 MCP）。"""
    return NETWORK_CALLER


def record_reverse_call(cap_id: str, trigger: str, trigger_detail: str,
                        caller: str = None, fee: float = None) -> dict:
    """写入一条反向调用台账并返回该记录。
    trigger: 'manual' | 'intent' | 'internal_mcp' | 'north_invoke'；caller 为发起方
    （默认网络侧 Agent）；fee 为本次计费（默认 REVERSE_FEE，北向按次调用按实际单价计）。"""
    agent_name, color = (caller or NETWORK_CALLER[0]), NETWORK_CALLER[1]
    rec = {
        "ts": time.time(),
        "caller_agent": agent_name,
        "agent_color": color,
        "via": "内部 MCP · JSON-RPC tools/call（经 NEF 出向网关）",
        "trigger": trigger,
        "trigger_detail": trigger_detail,
        "latency_ms": random.randint(20, 80),
        "status": "success",
        "fee": REVERSE_FEE if fee is None else round(fee, 2),
    }
    calls = REVERSE_CALLS.setdefault(cap_id, [])
    calls.append(rec)
    del calls[:-500]   # demo 内存保护：每能力最多保留 500 条
    return rec
