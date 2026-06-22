# -*- coding: utf-8 -*-
import registry


def setup_function():
    registry.THIRD_PARTY.clear()
    registry.THIRD_PARTY_META.clear()
    registry.REVERSE_CALLS.clear()


def test_caller_agent_is_network_side_regardless_of_cap_type():
    # 反向调用方统一为网络侧 Agent（经内部 MCP），不再按 cap_type 武断映射
    registry.THIRD_PARTY_META["tp_x"] = {"cap_type": "ai_model", "owner": "a", "endpoint": "http://x"}
    assert registry.caller_agent_for("tp_x") == registry.NETWORK_CALLER
    registry.THIRD_PARTY_META["tp_y"] = {"cap_type": "data_source", "owner": "a", "endpoint": "http://y"}
    assert registry.caller_agent_for("tp_y") == registry.NETWORK_CALLER


def test_record_reverse_call():
    registry.THIRD_PARTY_META["tp_x"] = {"cap_type": "ai_model", "owner": "a", "endpoint": "http://x"}
    rec = registry.record_reverse_call("tp_x", trigger="manual", trigger_detail="手动模拟")
    assert rec["caller_agent"] == registry.NETWORK_CALLER[0]  # 默认网络侧 Agent
    assert rec["via"].startswith("内部 MCP")
    assert rec["status"] == "success"
    assert rec["fee"] == 0.05
    assert 20 <= rec["latency_ms"] <= 80
    assert registry.REVERSE_CALLS["tp_x"] == [rec]
    # 显式 caller 透传（如 Planning Agent）
    rec2 = registry.record_reverse_call("tp_x", trigger="internal_mcp",
                                        trigger_detail="d", caller="网络侧 Planning Agent")
    assert rec2["caller_agent"] == "网络侧 Planning Agent"


def test_third_party_stub():
    from stubs import invoke_stub
    out = invoke_stub("tp_abc12345", {"payload": {"image": "x.jpg"}})
    assert out["status"] == "success"
    assert out["result"]["provided_by"] == "third_party_af"
    assert out["result"]["echo_payload"] == {"payload": {"image": "x.jpg"}}
