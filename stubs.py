# -*- coding: utf-8 -*-
"""能力调用的模拟返回数据（格式逼真，无真实后端）"""
import random
import time
import uuid


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def invoke_stub(cap_id: str, params: dict) -> dict:
    if cap_id.startswith("tp_"):
        fn = _third_party
    else:
        fn = _STUBS.get(cap_id, _generic)
    result = fn(params or {})
    return {"status": "success", "capability": cap_id, "timestamp": _ts(), "result": result}


def _generic(p):
    return {"task_id": _id("task"), "state": "completed", "echo_params": p}


def _third_party(p):
    return {"provided_by": "third_party_af",
            "af_task_id": _id("af"),
            "result": "AF 能力执行成功（由第三方端点返回，模拟）",
            "echo_payload": p}


def _target_detection(p):
    types = p.get("object_types") or ["person", "vehicle", "uav"]
    n = random.randint(1, 4)
    targets = []
    for i in range(n):
        t = random.choice(types)
        targets.append({
            "target_id": _id("tgt"),
            "type": t,
            "position": {"x": round(random.uniform(0, 200), 1),
                         "y": round(random.uniform(0, 120), 1),
                         "z": round(random.uniform(0, 60), 1) if t == "uav" else 0.0},
            "confidence": round(random.uniform(0.82, 0.99), 2),
        })
    return {"area": p.get("area", "area_default"), "detected_count": n,
            "targets": targets, "sensing_mode": "joint_comm_sensing",
            "sensitivity": p.get("sensitivity", "medium")}


def _target_tracking(p):
    track = []
    x, y = random.uniform(0, 50), random.uniform(0, 50)
    for i in range(5):
        x += random.uniform(2, 8); y += random.uniform(-3, 5)
        track.append({"t_offset_s": i * int(p.get("report_interval_sec", 5) or 5),
                      "x": round(x, 1), "y": round(y, 1)})
    return {"target_id": p.get("target_id", "tgt_demo"),
            "session_id": _id("trk"), "state": "tracking",
            "current_speed_mps": round(random.uniform(1.0, 15.0), 1),
            "heading_deg": random.randint(0, 359),
            "trajectory_preview": track}


def _environment_recon(p):
    return {"recon_id": _id("env"), "area": p.get("area", "area_default"),
            "resolution": p.get("resolution", "medium"),
            "output_format": p.get("output_format", "point_cloud"),
            "point_count": random.randint(120000, 980000),
            "coverage_pct": round(random.uniform(92, 99.5), 1),
            "download_url": f"https://nef.example.com/recon/{uuid.uuid4().hex[:8]}.pcd",
            "estimated_ready_sec": random.randint(15, 90)}


def _compute_offload(p):
    node = p.get("preferred_node", "edge")
    if node == "auto":
        node = random.choice(["edge", "cloud"])
    return {"task_id": _id("job"),
            "task_type": p.get("task_type", "generic"),
            "assigned_node": {"type": node,
                              "node_id": f"{node}-node-{random.randint(1, 8):02d}",
                              "region": "cn-east-1"},
            "allocated": {"cpu_cores": p.get("cpu_cores", 4),
                          "memory_gb": p.get("memory_gb", 8)},
            "state": "running",
            "est_completion_sec": random.randint(10, 120)}


def _ai_inference(p):
    model = p.get("model", "yolo-v9-edge")
    out = {"model": model, "inference_id": _id("inf"),
           "latency_ms": random.randint(8, int(p.get("max_latency_ms", 100) or 100)),
           "served_at": "edge-node-03"}
    if "yolo" in model or "defect" in model:
        out["predictions"] = [
            {"label": random.choice(["ok", "scratch", "dent", "person", "vehicle"]),
             "score": round(random.uniform(0.85, 0.99), 3)} for _ in range(random.randint(1, 3))]
    else:
        out["output"] = "推理完成，结果已写入输出流"
    return out


def _qos_guarantee(p):
    return {"policy_id": _id("qos"),
            "device_id": p.get("device_id", "imsi-460001234567890"),
            "applied": {"latency_ms": p.get("latency_ms", 20),
                        "bandwidth_mbps": p.get("bandwidth_mbps", 100),
                        "reliability": "99.999%",
                        "5qi": random.choice([1, 2, 82, 83])},
            "duration_min": p.get("duration_min", 60),
            "state": "active"}


def _event_subscription(p):
    return {"subscription_id": _id("sub"),
            "event_type": p.get("event_type", "device_online"),
            "device_id": p.get("device_id", "imsi-460001234567890"),
            "callback_url": p.get("callback_url", "https://af.example.com/callback"),
            "state": "active", "expires": "2026-12-31T23:59:59Z"}


def _network_diagnosis(p):
    score = random.randint(62, 98)
    issues = []
    if score < 80:
        issues = [{"issue": "上行干扰偏高", "severity": "medium", "suggestion": "建议启用 QoS 保障或切换至切片专网"}]
    return {"device_id": p.get("device_id", "imsi-460001234567890"),
            "experience_score": score,
            "metrics": {"rsrp_dbm": random.randint(-110, -75),
                        "latency_ms": random.randint(8, 45),
                        "ul_mbps": random.randint(20, 180),
                        "dl_mbps": random.randint(100, 900),
                        "jitter_ms": round(random.uniform(0.5, 6.0), 1)},
            "issues": issues,
            "suggestions": ["当前小区负载正常"] if not issues else [i["suggestion"] for i in issues]}


def _slice_management(p):
    return {"slice_id": _id("slice"),
            "action": p.get("action", "create"),
            "slice_type": p.get("slice_type", "urllc"),
            "s_nssai": {"sst": {"embb": 1, "urllc": 2, "miot": 3}.get(p.get("slice_type", "urllc"), 2),
                        "sd": f"{random.randint(1, 0xFFFFFF):06X}"},
            "coverage_area": p.get("coverage_area", "campus_default"),
            "state": "provisioned", "ready_in_sec": random.randint(5, 30)}


def _device_wakeup(p):
    return {"wakeup_id": _id("wk"),
            "device_id": p.get("device_id", "imsi-460001234567890"),
            "mode": p.get("wakeup_mode", "paging"),
            "state": "awake", "response_time_ms": random.randint(300, 2500)}


def _mobility_insight(p):
    return {"analysis_id": _id("mob"),
            "target_group": p.get("target_group", "group_default"),
            "time_window_h": p.get("time_window_h", 24),
            "patterns": [
                {"pattern": "commute", "share_pct": 46, "peak_hours": ["08:00-09:30", "18:00-19:30"]},
                {"pattern": "stationary", "share_pct": 38},
                {"pattern": "roaming", "share_pct": 16},
            ],
            "hotspots": ["园区A栋", "地铁2号线沿线", "商业中心"]}


def _precision_location(p):
    return {"location_id": _id("loc"),
            "device_id": p.get("device_id", "imsi-460001234567890"),
            "position": {"lat": round(30.0 + random.uniform(0, 0.5), 6),
                         "lon": round(120.0 + random.uniform(0, 0.5), 6),
                         "altitude_m": round(random.uniform(0, 80), 1),
                         "floor": random.randint(1, 12)},
            "accuracy_m": {"meter": 1.0, "submeter": 0.5, "centimeter": 0.05}.get(p.get("accuracy", "submeter"), 0.5),
            "method": "NR-UTDOA + AoA",
            "mode": p.get("mode", "realtime")}


def _data_query(p):
    ds = p.get("dataset", "coverage_map")
    return {"query_id": _id("dq"), "dataset": ds,
            "area": p.get("area", "city_default"),
            "time_range_h": p.get("time_range_h", 24),
            "record_count": random.randint(1000, 50000),
            "sample": {"coverage_map": {"avg_rsrp_dbm": -92, "weak_zones": 3},
                       "heatmap": {"peak_density_per_km2": 1240, "hot_cells": 12},
                       "perf_stats": {"avg_dl_mbps": 412, "p99_latency_ms": 34},
                       "traffic_profile": {"daily_gb": 8421, "peak_hour": "20:00"}}.get(ds, {}),
            "download_url": f"https://nef.example.com/datasets/{_id('ds')}.json"}


def _network_analytics(p):
    at = p.get("analytics_type", "anomaly_detection")
    res = {"analytics_id": _id("an"), "analytics_type": at, "target": p.get("target", "network_wide")}
    if at == "anomaly_detection":
        res["anomalies"] = [{"cell": f"gNB-{random.randint(100, 999)}", "type": "traffic_spike",
                             "severity": "medium", "confidence": 0.91}]
    elif at == "capacity_forecast":
        res["forecast"] = {"horizon_h": 72, "peak_load_pct": 87, "expansion_advice": "建议在 gNB-214 扩容 1 载波"}
    else:
        res["summary"] = "分析完成，详情见报告链接"
        res["report_url"] = f"https://nef.example.com/reports/{_id('rp')}.pdf"
    return res


def _security_check(p):
    risk = random.choice(["low", "low", "medium"])
    return {"check_id": _id("sec"), "target_id": p.get("target_id", "dev_demo"),
            "check_level": p.get("check_level", "standard"),
            "risk_level": risk, "score": random.randint(80, 99),
            "findings": [] if risk == "low" else [{"finding": "固件版本偏旧", "advice": "建议升级至 v2.4+"}]}


def _capability_register(p):
    return {"registration_id": _id("reg"),
            "cap_name": p.get("cap_name", "third_party_cap"),
            "cap_type": p.get("cap_type", "tool"),
            "endpoint": p.get("endpoint", "https://af.example.com/cap"),
            "state": "registered", "visible_in_marketplace": True}


def _identity_service(p):
    return {"identity_id": _id("did"),
            "subject": p.get("subject", "agent_demo"),
            "credential": f"did:6gnet:{uuid.uuid4().hex[:16]}",
            "validity_days": p.get("validity_days", 365),
            "issued_at": _ts(), "state": "active"}


_STUBS = {
    "target_detection": _target_detection,
    "target_tracking": _target_tracking,
    "environment_recon": _environment_recon,
    "compute_offload": _compute_offload,
    "ai_inference": _ai_inference,
    "qos_guarantee": _qos_guarantee,
    "event_subscription": _event_subscription,
    "network_diagnosis": _network_diagnosis,
    "slice_management": _slice_management,
    "device_wakeup": _device_wakeup,
    "mobility_insight": _mobility_insight,
    "precision_location": _precision_location,
    "data_query": _data_query,
    "network_analytics": _network_analytics,
    "security_check": _security_check,
    "capability_register": _capability_register,
    "identity_service": _identity_service,
}
