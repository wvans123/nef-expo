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
