# -*- coding: utf-8 -*-
"""能力目录定义 —— 唯一数据源。
REST API / MCP Tool / Intent 规则 / UI 展示全部从此派生。
"""
from dataclasses import dataclass, field, asdict


@dataclass
class CapParam:
    name: str
    type: str
    description: str
    required: bool = False
    default: object = None
    enum: list = None

    def to_dict(self):
        d = {"name": self.name, "type": self.type, "description": self.description,
             "required": self.required}
        if self.default is not None:
            d["default"] = self.default
        if self.enum:
            d["enum"] = self.enum
        return d


@dataclass
class Capability:
    id: str
    name: str
    description: str
    category: str          # isac/computing/connectivity/location/data/ecosystem
    tier: str              # basic/advanced/premium
    params: list = field(default_factory=list)
    intent_keywords: list = field(default_factory=list)
    unit_price: str = "免费"
    source: str = "network"  # network / third_party

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "category": self.category, "tier": self.tier,
            "params": [p.to_dict() for p in self.params],
            "intent_keywords": self.intent_keywords,
            "unit_price": self.unit_price, "source": self.source,
        }

    def mcp_tool(self):
        """派生 MCP Tool 定义"""
        props, required = {}, []
        for p in self.params:
            schema = {"type": p.type, "description": p.description}
            if p.enum:
                schema["enum"] = p.enum
            if p.default is not None:
                schema["default"] = p.default
            props[p.name] = schema
            if p.required:
                required.append(p.name)
        return {
            "name": self.id,
            "description": f"[{self.name}] {self.description}",
            "inputSchema": {"type": "object", "properties": props, "required": required},
        }


CATEGORIES = {
    "isac": {"name": "通感一体 ISAC", "color": "#ff9e3d"},
    "computing": {"name": "通算一体 Computing", "color": "#bc8cff"},
    "connectivity": {"name": "连接服务 Connectivity", "color": "#58a6ff"},
    "location": {"name": "定位服务 Location", "color": "#39d2c0"},
    "data": {"name": "数据服务 Data", "color": "#3fb950"},
    "ecosystem": {"name": "生态服务 Ecosystem", "color": "#6e7bf2"},
}

CAPABILITIES = [
    # ===== 通感一体 ISAC =====
    Capability(
        id="target_detection", name="目标检测", category="isac", tier="basic",
        description="检测指定区域内的物体（人、车辆、无人机等），返回目标类型、位置和置信度",
        params=[
            CapParam("area", "string", "检测区域标识或坐标范围", required=True),
            CapParam("object_types", "array", "关注的目标类型，如 person/vehicle/uav", default=["person", "vehicle", "uav"]),
            CapParam("sensitivity", "string", "检测灵敏度", default="medium", enum=["low", "medium", "high"]),
        ],
        intent_keywords=["检测", "识别", "发现", "异常物体", "入侵", "有没有人", "有没有车", "仓库", "感知"],
        unit_price="19.9/月",
    ),
    Capability(
        id="target_tracking", name="目标追踪", category="isac", tier="advanced",
        description="持续追踪指定目标的移动轨迹，返回实时位置、速度和航向",
        params=[
            CapParam("target_id", "string", "目标标识（来自目标检测结果）", required=True),
            CapParam("duration_sec", "integer", "追踪时长（秒）", default=300),
            CapParam("report_interval_sec", "integer", "上报间隔（秒）", default=5),
        ],
        intent_keywords=["追踪", "跟踪", "轨迹", "无人机", "移动目标", "盯着", "监视"],
        unit_price="39.9/月",
    ),
    Capability(
        id="environment_recon", name="环境重构", category="isac", tier="premium",
        description="基于无线信号进行三维空间建模，生成区域环境的数字化重构结果",
        params=[
            CapParam("area", "string", "重构区域标识", required=True),
            CapParam("resolution", "string", "重构分辨率", default="medium", enum=["low", "medium", "high"]),
            CapParam("output_format", "string", "输出格式", default="point_cloud", enum=["point_cloud", "mesh", "voxel"]),
        ],
        intent_keywords=["三维", "3D", "建模", "重构", "数字孪生", "空间模型", "环境感知"],
        unit_price="99.9/月",
    ),
    # ===== 通算一体 Computing =====
    Capability(
        id="compute_offload", name="计算卸载", category="computing", tier="basic",
        description="将计算任务（模型部署/转码/渲染）卸载到网络边缘或云端节点执行",
        params=[
            CapParam("task_type", "string", "任务类型", required=True, enum=["model_deploy", "transcode", "render", "generic"]),
            CapParam("preferred_node", "string", "偏好节点", default="edge", enum=["edge", "cloud", "auto"]),
            CapParam("cpu_cores", "integer", "所需 CPU 核数", default=4),
            CapParam("memory_gb", "integer", "所需内存（GB）", default=8),
        ],
        intent_keywords=["卸载", "转码", "渲染", "部署", "边缘计算", "算力", "云端处理"],
        unit_price="29.9/月",
    ),
    Capability(
        id="ai_inference", name="AI推理服务", category="computing", tier="advanced",
        description="调用网络侧已部署的AI模型进行实时推理",
        params=[
            CapParam("model", "string", "模型名称", required=True, enum=["yolo-v9-edge", "defect-detect-v2", "llm-7b-net", "asr-stream"]),
            CapParam("input_ref", "string", "输入数据引用（URL 或数据流 ID）", required=True),
            CapParam("max_latency_ms", "integer", "最大可接受推理时延", default=100),
        ],
        intent_keywords=["推理", "AI", "模型", "智能分析", "图像识别", "缺陷", "质检"],
        unit_price="49.9/月",
    ),
    # ===== 连接服务 Connectivity =====
    Capability(
        id="qos_guarantee", name="QoS 保障", category="connectivity", tier="basic",
        description="为指定设备或应用保障网络质量（时延/带宽/可靠性）",
        params=[
            CapParam("device_id", "string", "设备标识（IMSI/GPSI）", required=True),
            CapParam("latency_ms", "integer", "目标时延上限（ms）", default=20),
            CapParam("bandwidth_mbps", "integer", "保障带宽（Mbps）", default=100),
            CapParam("duration_min", "integer", "保障时长（分钟）", default=60),
        ],
        intent_keywords=["低时延", "保障", "QoS", "带宽", "卡顿", "直播", "网络质量", "加速"],
        unit_price="9.9/月",
    ),
    Capability(
        id="event_subscription", name="事件订阅", category="connectivity", tier="basic",
        description="订阅网络事件通知（设备上下线、位置变更等）",
        params=[
            CapParam("event_type", "string", "事件类型", required=True, enum=["device_online", "device_offline", "location_change", "qos_degradation"]),
            CapParam("device_id", "string", "关注的设备标识", required=True),
            CapParam("callback_url", "string", "事件回调地址", default="https://af.example.com/callback"),
        ],
        intent_keywords=["订阅", "通知", "上线", "下线", "事件", "告警", "位置变更"],
        unit_price="4.9/月",
    ),
    Capability(
        id="network_diagnosis", name="网络诊断", category="connectivity", tier="basic",
        description="检测当前网络状态，输出体验评分和优化建议",
        params=[
            CapParam("device_id", "string", "待诊断设备标识", required=True),
            CapParam("scope", "string", "诊断范围", default="full", enum=["radio", "core", "full"]),
        ],
        intent_keywords=["诊断", "网络状态", "为什么慢", "体验", "评分", "检查网络", "网速"],
        unit_price="免费",
    ),
    Capability(
        id="slice_management", name="按需切片", category="connectivity", tier="advanced",
        description="按需创建/配置/释放网络切片",
        params=[
            CapParam("action", "string", "操作类型", required=True, enum=["create", "modify", "release"]),
            CapParam("slice_type", "string", "切片类型", default="urllc", enum=["embb", "urllc", "miot"]),
            CapParam("coverage_area", "string", "覆盖区域", default="campus_default"),
        ],
        intent_keywords=["切片", "专网", "独立网络", "隔离"],
        unit_price="59.9/月",
    ),
    Capability(
        id="device_wakeup", name="设备唤醒", category="connectivity", tier="basic",
        description="唤醒处于省电模式的 IoT 设备",
        params=[
            CapParam("device_id", "string", "目标设备标识", required=True),
            CapParam("wakeup_mode", "string", "唤醒方式", default="paging", enum=["paging", "wus", "nidd"]),
        ],
        intent_keywords=["唤醒", "省电", "休眠", "叫醒", "IoT设备"],
        unit_price="2.9/月",
    ),
    Capability(
        id="mobility_insight", name="移动性洞察", category="connectivity", tier="advanced",
        description="分析设备/用户群的移动模式",
        params=[
            CapParam("target_group", "string", "分析对象（设备 ID 或群组 ID）", required=True),
            CapParam("time_window_h", "integer", "分析时间窗口（小时）", default=24),
        ],
        intent_keywords=["移动模式", "人流", "迁移", "通勤", "移动性"],
        unit_price="39.9/月",
    ),
    # ===== 定位服务 Location =====
    Capability(
        id="precision_location", name="精准定位", category="location", tier="advanced",
        description="提供亚米级室内外定位，支持实时位置查询和轨迹追踪",
        params=[
            CapParam("device_id", "string", "目标设备标识", required=True),
            CapParam("accuracy", "string", "精度要求", default="submeter", enum=["meter", "submeter", "centimeter"]),
            CapParam("mode", "string", "定位模式", default="realtime", enum=["realtime", "periodic", "on_demand"]),
        ],
        intent_keywords=["定位", "位置", "在哪", "坐标", "室内定位", "找到"],
        unit_price="29.9/月",
    ),
    # ===== 数据服务 Data =====
    Capability(
        id="data_query", name="数据服务", category="data", tier="basic",
        description="获取网络侧数据集（覆盖、热力图、性能统计等）",
        params=[
            CapParam("dataset", "string", "数据集类型", required=True, enum=["coverage_map", "heatmap", "perf_stats", "traffic_profile"]),
            CapParam("area", "string", "查询区域", default="city_default"),
            CapParam("time_range_h", "integer", "时间范围（小时）", default=24),
        ],
        intent_keywords=["数据", "热力图", "覆盖", "统计", "报表"],
        unit_price="9.9/月",
    ),
    Capability(
        id="network_analytics", name="网络分析", category="data", tier="premium",
        description="AI 驱动的网络智能分析（异常检测、容量预测等）",
        params=[
            CapParam("analytics_type", "string", "分析类型", required=True, enum=["anomaly_detection", "capacity_forecast", "ue_behavior", "service_experience"]),
            CapParam("target", "string", "分析对象", default="network_wide"),
        ],
        intent_keywords=["分析", "预测", "异常检测", "容量", "趋势", "NWDAF"],
        unit_price="79.9/月",
    ),
    # ===== 生态服务 Ecosystem =====
    Capability(
        id="security_check", name="安全检查", category="ecosystem", tier="basic",
        description="对设备/连接进行安全状态检查",
        params=[
            CapParam("target_id", "string", "检查对象（设备/连接 ID）", required=True),
            CapParam("check_level", "string", "检查级别", default="standard", enum=["quick", "standard", "deep"]),
        ],
        intent_keywords=["安全", "风险", "漏洞", "检查", "合规"],
        unit_price="免费",
    ),
    Capability(
        id="capability_register", name="能力注册", category="ecosystem", tier="premium",
        description="将第三方能力注册到网络（双向开放）",
        params=[
            CapParam("cap_name", "string", "能力名称", required=True),
            CapParam("cap_type", "string", "能力类型", required=True, enum=["ai_model", "tool", "data_source"]),
            CapParam("endpoint", "string", "能力访问端点", required=True),
        ],
        intent_keywords=["注册", "接入", "开放", "我的能力", "第三方"],
        unit_price="企业专属",
    ),
    Capability(
        id="identity_service", name="身份服务", category="ecosystem", tier="advanced",
        description="为 Agent/应用颁发网络数字身份",
        params=[
            CapParam("subject", "string", "申请主体（Agent/应用名称）", required=True),
            CapParam("validity_days", "integer", "有效期（天）", default=365),
        ],
        intent_keywords=["身份", "凭证", "认证", "数字身份", "Agent身份"],
        unit_price="19.9/月",
    ),
]

CAP_INDEX = {c.id: c for c in CAPABILITIES}

# ===== 场景套餐 =====
PACKAGES = [
    {
        "id": "smart_factory", "name": "智能工厂套餐", "price": "89/月",
        "description": "面向工厂园区的检测+质检+算力+网络保障一站式方案",
        "capabilities": ["target_detection", "ai_inference", "compute_offload", "qos_guarantee"],
        "scenario": "工厂产线视觉质检与园区安防",
    },
    {
        "id": "uav_mgmt", "name": "无人机管控套餐", "price": "59/月",
        "description": "低空无人机的探测、追踪、定位与事件告警",
        "capabilities": ["target_tracking", "precision_location", "event_subscription"],
        "scenario": "低空经济 / 无人机监管",
    },
    {
        "id": "livestream", "name": "直播增强套餐", "price": "29/月",
        "description": "户外直播的转码卸载与上行体验保障",
        "capabilities": ["compute_offload", "qos_guarantee", "network_diagnosis"],
        "scenario": "户外/电商直播",
    },
    {
        "id": "xr_collab_pkg", "name": "XR 协同套餐", "price": "129/月",
        "description": "XR 空间重构、云渲染推理与确定性网络体验",
        "capabilities": ["environment_recon", "ai_inference", "qos_guarantee"],
        "scenario": "XR 远程协作 / 元宇宙",
    },
    {
        "id": "robot_patrol", "name": "机器狗巡检套餐", "price": "79/月",
        "description": "机器狗的定位、目标检测、AI 识别与事件上报",
        "capabilities": ["precision_location", "target_detection", "ai_inference", "event_subscription"],
        "scenario": "园区/变电站机器狗巡检",
    },
]

PKG_INDEX = {p["id"]: p for p in PACKAGES}

# ===== 内部 Agent 与 NF Tool 映射 =====
AGENTS = {
    "connection": {
        "name": "Connection Agent", "color": "#58a6ff",
        "capabilities": ["qos_guarantee", "event_subscription", "network_diagnosis",
                         "slice_management", "device_wakeup", "mobility_insight"],
        "nf_tools": [
            {"tool": "amf_ue_context_query", "sbi": "Namf_Communication"},
            {"tool": "smf_session_create", "sbi": "Nsmf_PDUSession"},
            {"tool": "pcf_policy_update", "sbi": "Npcf_PolicyAuthorization"},
            {"tool": "nssf_slice_select", "sbi": "Nnssf_NSSelection"},
            {"tool": "udm_subscriber_query", "sbi": "Nudm_SDM"},
        ],
    },
    "computing": {
        "name": "Computing Agent", "color": "#bc8cff",
        "capabilities": ["compute_offload", "ai_inference"],
        "nf_tools": [
            {"tool": "eees_app_deploy", "sbi": "EEES AppContext"},
            {"tool": "compute_offload_submit", "sbi": "Edge Computing API"},
            {"tool": "resource_monitor", "sbi": "OAM/Analytics"},
        ],
    },
    "sensing": {
        "name": "Sensing Agent", "color": "#ff9e3d",
        "capabilities": ["target_detection", "target_tracking", "environment_recon"],
        "nf_tools": [
            {"tool": "sensing_session_create", "sbi": "Nsensf_Sensing"},
            {"tool": "sensing_result_fetch", "sbi": "Nsensf_SensingData"},
            {"tool": "sensing_config_update", "sbi": "Nsensf_Configuration"},
        ],
    },
    "data": {
        "name": "Data Agent", "color": "#3fb950",
        "capabilities": ["data_query", "network_analytics", "security_check",
                         "capability_register", "identity_service"],
        "nf_tools": [
            {"tool": "nwdaf_analytics_query", "sbi": "Nnwdaf_AnalyticsInfo"},
            {"tool": "dccf_data_subscribe", "sbi": "Ndccf_DataManagement"},
            {"tool": "adrf_dataset_fetch", "sbi": "Nadrf_DataManagement"},
        ],
    },
    "location": {
        "name": "Location Agent", "color": "#39d2c0",
        "capabilities": ["precision_location"],
        "nf_tools": [
            {"tool": "lmf_location_request", "sbi": "Nlmf_Location"},
            {"tool": "gmlc_location_query", "sbi": "GMLC API"},
        ],
    },
}


def agent_for_capability(cap_id: str):
    for key, ag in AGENTS.items():
        if cap_id in ag["capabilities"]:
            return key, ag
    return "data", AGENTS["data"]
