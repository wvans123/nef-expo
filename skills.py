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
    status: str = "available"   # available / planned（规划中，标灰展示，不可订阅调用）
    icon: str = "⚙️"

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "category": self.category, "tier": self.tier,
            "params": [p.to_dict() for p in self.params],
            "intent_keywords": self.intent_keywords,
            "unit_price": self.unit_price, "source": self.source,
            "status": self.status, "icon": self.icon,
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
        id="target_detection", name="目标检测", category="isac", tier="basic", icon="🎯",
        description="检测指定区域内的物体（人、车辆、无人机等），返回目标类型、位置和置信度",
        params=[
            CapParam("area", "string", "检测区域标识或坐标范围", required=True),
            CapParam("object_types", "array", "关注的目标类型，如 person/vehicle/uav", default=["person", "vehicle", "uav"]),
            CapParam("sensitivity", "string", "检测灵敏度", default="medium", enum=["low", "medium", "high"]),
        ],
        intent_keywords=["检测", "识别", "发现", "异常物体", "入侵", "有没有人", "有没有车", "仓库", "感知", "巡检"],
        unit_price="19.9/月",
    ),
    Capability(
        id="target_tracking", name="目标追踪", category="isac", tier="advanced", icon="🛰️",
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
        id="environment_recon", name="环境重构", category="isac", tier="premium", icon="🏗️",
        description="基于无线信号进行三维空间建模，生成区域环境的数字化重构结果",
        params=[
            CapParam("area", "string", "重构区域标识", required=True),
            CapParam("resolution", "string", "重构分辨率", default="medium", enum=["low", "medium", "high"]),
            CapParam("output_format", "string", "输出格式", default="point_cloud", enum=["point_cloud", "mesh", "voxel"]),
        ],
        intent_keywords=["三维", "3D", "建模", "重构", "数字孪生", "空间模型", "环境感知"],
        unit_price="99.9/月",
    ),
    Capability(
        id="sensing_fusion", name="多源感知融合", category="isac", tier="premium", icon="🌐",
        description="将 3GPP 无线感知与非 3GPP 数据（摄像头/激光雷达/红外）融合处理，输出全天候高置信感知结果",
        params=[
            CapParam("area", "string", "融合感知区域", required=True),
            CapParam("sources", "array", "数据源列表", default=["3gpp_radio", "camera", "lidar"]),
            CapParam("fusion_mode", "string", "融合模式", default="realtime", enum=["realtime", "batch"]),
        ],
        intent_keywords=["感知融合", "融合", "雾天", "看得清", "机器狗", "非3gpp", "全天候"],
        unit_price="89.9/月",
    ),
    Capability(
        id="traffic_flow_sensing", name="车流量感知", category="isac", tier="advanced", icon="🚗",
        description="基于通感一体对城市道路进行车流量实时检测，输出车流密度、车速与拥堵状态",
        params=[
            CapParam("road_id", "string", "道路标识", required=True),
            CapParam("direction", "string", "检测方向", default="both", enum=["both", "inbound", "outbound"]),
            CapParam("interval_min", "integer", "统计间隔（分钟）", default=5),
        ],
        intent_keywords=["车流", "车流量", "道路", "拥堵", "交通检测"],
        unit_price="49.9/月",
    ),
    Capability(id="vital_sign_detection", name="生命体征感知", category="isac", tier="premium", icon="🫀",
               status="planned", unit_price="规划中",
               description="基于无线信号非接触检测呼吸/心率等生命体征（规划中）",
               params=[CapParam("area", "string", "检测区域", required=True)],
               intent_keywords=["生命体征", "呼吸", "心率"]),
    Capability(id="gesture_recognition", name="手势姿态识别", category="isac", tier="advanced", icon="✋",
               status="planned", unit_price="规划中",
               description="无线感知驱动的手势与人体姿态识别（规划中）",
               params=[CapParam("area", "string", "识别区域", required=True)],
               intent_keywords=["手势", "姿态识别"]),
    # ===== 通算一体 Computing =====
    Capability(
        id="compute_offload", name="计算卸载", category="computing", tier="basic", icon="⚡",
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
        id="ai_inference", name="AI推理服务", category="computing", tier="advanced", icon="🧠",
        description="调用网络侧已部署的AI模型进行实时推理",
        params=[
            CapParam("model", "string", "模型名称", required=True, enum=["yolo-v9-edge", "defect-detect-v2", "llm-7b-net", "asr-stream"]),
            CapParam("input_ref", "string", "输入数据引用（URL 或数据流 ID）", required=True),
            CapParam("max_latency_ms", "integer", "最大可接受推理时延", default=100),
        ],
        intent_keywords=["推理", "AI", "模型", "智能分析", "图像识别", "缺陷", "质检"],
        unit_price="49.9/月",
    ),
    Capability(
        id="render_offload", name="云渲染卸载", category="computing", tier="advanced", icon="🖼️",
        description="将 XR/AR 渲染任务卸载至边缘 GPU 节点，按目标帧率回传渲染流",
        params=[
            CapParam("scene_ref", "string", "场景/内容引用", required=True),
            CapParam("resolution", "string", "渲染分辨率", default="4k", enum=["1080p", "2k", "4k", "8k"]),
            CapParam("target_fps", "integer", "目标帧率", default=90),
        ],
        intent_keywords=["渲染", "云渲染", "XR", "AR", "VR", "元宇宙"],
        unit_price="69.9/月",
    ),
    Capability(
        id="compute_qos", name="算力 QoS 保障", category="computing", tier="advanced", icon="🎛️",
        description="为指定计算任务保障算力侧 QoS（CPU/GPU 优先级、抖动上限），可与通信 QoS 联动实现端到端体验保障",
        params=[
            CapParam("task_id", "string", "计算任务标识（来自计算卸载结果）", required=True),
            CapParam("cpu_priority", "string", "CPU 优先级", default="high", enum=["standard", "high", "realtime"]),
            CapParam("gpu_share_pct", "integer", "GPU 配额（%）", default=50),
            CapParam("max_jitter_ms", "integer", "计算抖动上限（ms）", default=10),
        ],
        intent_keywords=["算力QoS", "算力保障", "卡顿", "计算保障", "算力优先级", "不卡"],
        unit_price="39.9/月",
    ),
    Capability(id="edge_agent_hosting", name="边缘智能体托管", category="computing", tier="premium", icon="🤖",
               status="planned", unit_price="规划中",
               description="将 AF 的 AI Agent 托管到网络边缘运行，贴近数据与用户（规划中）",
               params=[CapParam("agent_image", "string", "Agent 镜像引用", required=True)],
               intent_keywords=["托管", "智能体托管"]),
    Capability(id="federated_learning", name="联邦学习编排", category="computing", tier="premium", icon="🤝",
               status="planned", unit_price="规划中",
               description="跨终端/边缘节点的联邦学习任务编排与聚合（规划中）",
               params=[CapParam("model_ref", "string", "模型引用", required=True)],
               intent_keywords=["联邦学习"]),
    # ===== 连接服务 Connectivity =====
    Capability(
        id="qos_guarantee", name="QoS 保障", category="connectivity", tier="basic", icon="📶",
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
        id="event_subscription", name="事件订阅", category="connectivity", tier="basic", icon="🔔",
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
        id="network_diagnosis", name="网络诊断", category="connectivity", tier="basic", icon="🩺",
        description="检测当前网络状态，输出体验评分和优化建议",
        params=[
            CapParam("device_id", "string", "待诊断设备标识", required=True),
            CapParam("scope", "string", "诊断范围", default="full", enum=["radio", "core", "full"]),
        ],
        intent_keywords=["诊断", "网络状态", "为什么慢", "体验", "评分", "检查网络", "网速"],
        unit_price="免费",
    ),
    Capability(
        id="slice_management", name="按需切片", category="connectivity", tier="advanced", icon="🧩",
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
        id="device_wakeup", name="设备唤醒", category="connectivity", tier="basic", icon="⏰",
        description="唤醒处于省电模式的 IoT 设备",
        params=[
            CapParam("device_id", "string", "目标设备标识", required=True),
            CapParam("wakeup_mode", "string", "唤醒方式", default="paging", enum=["paging", "wus", "nidd"]),
        ],
        intent_keywords=["唤醒", "省电", "休眠", "叫醒", "IoT设备"],
        unit_price="2.9/月",
    ),
    Capability(
        id="mobility_insight", name="移动性洞察", category="connectivity", tier="advanced", icon="🚶",
        description="分析设备/用户群的移动模式",
        params=[
            CapParam("target_group", "string", "分析对象（设备 ID 或群组 ID）", required=True),
            CapParam("time_window_h", "integer", "分析时间窗口（小时）", default=24),
        ],
        intent_keywords=["移动模式", "人流", "迁移", "通勤", "移动性"],
        unit_price="39.9/月",
    ),
    Capability(id="multipath_boost", name="多路径聚合加速", category="connectivity", tier="advanced", icon="🛣️",
               status="planned", unit_price="规划中",
               description="蜂窝+Wi-Fi+卫星多路径聚合传输（规划中）",
               params=[CapParam("device_id", "string", "设备标识", required=True)],
               intent_keywords=["多路径", "聚合加速"]),
    Capability(id="deterministic_latency", name="确定性时延", category="connectivity", tier="premium", icon="⏱️",
               status="planned", unit_price="规划中",
               description="为工业控制提供有界时延的确定性网络（规划中）",
               params=[CapParam("device_id", "string", "设备标识", required=True)],
               intent_keywords=["确定性", "有界时延"]),
    # ===== 定位服务 Location =====
    Capability(
        id="precision_location", name="精准定位", category="location", tier="advanced", icon="📍",
        description="提供亚米级室内外定位，支持实时位置查询和轨迹追踪",
        params=[
            CapParam("device_id", "string", "目标设备标识", required=True),
            CapParam("accuracy", "string", "精度要求", default="submeter", enum=["meter", "submeter", "centimeter"]),
            CapParam("mode", "string", "定位模式", default="realtime", enum=["realtime", "periodic", "on_demand"]),
        ],
        intent_keywords=["定位", "位置", "在哪", "坐标", "室内定位", "找到"],
        unit_price="29.9/月",
    ),
    Capability(
        id="geofencing", name="电子围栏", category="location", tier="basic", icon="🚧",
        description="为设备设置地理围栏，进出围栏时由网络主动告警",
        params=[
            CapParam("device_id", "string", "目标设备标识", required=True),
            CapParam("fence_area", "string", "围栏区域标识或坐标串", required=True),
            CapParam("trigger", "string", "触发方式", default="both", enum=["enter", "exit", "both"]),
        ],
        intent_keywords=["围栏", "电子围栏", "越界", "禁飞区"],
        unit_price="9.9/月",
    ),
    Capability(id="trajectory_predict", name="轨迹预测", category="location", tier="advanced", icon="🧭",
               status="planned", unit_price="规划中",
               description="基于历史轨迹预测目标未来位置（规划中）",
               params=[CapParam("target_id", "string", "目标标识", required=True)],
               intent_keywords=["轨迹预测"]),
    # ===== 数据服务 Data =====
    Capability(
        id="data_query", name="数据服务", category="data", tier="basic", icon="📊",
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
        id="network_analytics", name="网络分析", category="data", tier="premium", icon="📈",
        description="AI 驱动的网络智能分析（异常检测、容量预测等）",
        params=[
            CapParam("analytics_type", "string", "分析类型", required=True, enum=["anomaly_detection", "capacity_forecast", "ue_behavior", "service_experience"]),
            CapParam("target", "string", "分析对象", default="network_wide"),
        ],
        intent_keywords=["分析", "预测", "异常检测", "容量", "趋势", "NWDAF"],
        unit_price="79.9/月",
    ),
    Capability(
        id="traffic_forecast", name="车流量预测分析", category="data", tier="premium", icon="🚦",
        description="基于历史与实时车流感知数据，预测未来时段道路车流量与拥堵概率",
        params=[
            CapParam("road_id", "string", "道路标识", required=True),
            CapParam("horizon_min", "integer", "预测时长（分钟）", default=30),
        ],
        intent_keywords=["车流量预测", "预测", "车流", "早高峰", "晚高峰"],
        unit_price="59.9/月",
    ),
    Capability(id="digital_twin_feed", name="数字孪生数据底座", category="data", tier="premium", icon="🪞",
               status="planned", unit_price="规划中",
               description="向城市/园区数字孪生平台持续供给网络感知数据（规划中）",
               params=[CapParam("twin_id", "string", "孪生体标识", required=True)],
               intent_keywords=["数字孪生底座"]),
    # ===== 生态服务 Ecosystem =====
    Capability(
        id="security_check", name="安全检查", category="ecosystem", tier="basic", icon="🛡️",
        description="对设备/连接进行安全状态检查",
        params=[
            CapParam("target_id", "string", "检查对象（设备/连接 ID）", required=True),
            CapParam("check_level", "string", "检查级别", default="standard", enum=["quick", "standard", "deep"]),
        ],
        intent_keywords=["安全", "风险", "漏洞", "检查", "合规"],
        unit_price="免费",
    ),
    Capability(
        id="capability_register", name="能力注册", category="ecosystem", tier="premium", icon="🔗",
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
        id="identity_service", name="身份服务", category="ecosystem", tier="advanced", icon="🪪",
        description="为 Agent/应用颁发网络数字身份",
        params=[
            CapParam("subject", "string", "申请主体（Agent/应用名称）", required=True),
            CapParam("validity_days", "integer", "有效期（天）", default=365),
        ],
        intent_keywords=["身份", "凭证", "认证", "数字身份", "Agent身份"],
        unit_price="19.9/月",
    ),
    Capability(id="revenue_share", name="生态收益结算", category="ecosystem", tier="advanced", icon="💰",
               status="planned", unit_price="规划中",
               description="第三方能力被调用后的自动分账与结算（规划中）",
               params=[CapParam("settlement_period", "string", "结算周期", default="monthly")],
               intent_keywords=["分账", "结算"]),
]

CAP_INDEX = {c.id: c for c in CAPABILITIES}

# ===== 场景套餐 =====
PACKAGES = [
    {
        "id": "live_offload", "name": "直播计算卸载套餐", "price": "69/月",
        "description": "特效计算卸载先行；体验吃紧时通信 QoS 与算力 QoS 联动调整，保障 0 卡顿 AI 换脸",
        "capabilities": ["compute_offload", "compute_qos", "qos_guarantee", "network_diagnosis"],
        "scenario": "电商/户外直播 · 0卡顿 AI 特效",
    },
    {
        "id": "arm_dog_collab", "name": "机械臂×机器狗协同套餐", "price": "99/月",
        "description": "网络提供计算服务并结合环境感知，支撑机械臂与机器狗协同作业",
        "capabilities": ["compute_offload", "environment_recon", "precision_location", "event_subscription"],
        "scenario": "工业产线协同作业",
    },
    {
        "id": "embodied_agents", "name": "多智能体具身交互套餐", "price": "129/月",
        "description": "AR 眼镜与机器狗多智能体协同，渲染与算力卸载到网络边缘",
        "capabilities": ["render_offload", "compute_offload", "precision_location", "qos_guarantee"],
        "scenario": "AR 眼镜 × 机器狗具身智能",
    },
    {
        "id": "robot_patrol", "name": "机器狗巡检套餐", "price": "89/月",
        "description": "3GPP 无线感知与摄像头/激光雷达数据融合，让机器狗在雾天黑夜也看得清",
        "capabilities": ["sensing_fusion", "target_detection", "ai_inference", "precision_location", "event_subscription"],
        "scenario": "园区/变电站全天候巡检",
    },
    {
        "id": "traffic_forecast_pkg", "name": "城市车流量预测套餐", "price": "59/月",
        "description": "道路车流量检测触发，感知数据驱动的车流预测",
        "capabilities": ["traffic_flow_sensing", "traffic_forecast", "data_query"],
        "scenario": "智慧交通 · 城市道路",
    },
    {
        "id": "xr_render", "name": "XR 渲染卸载套餐", "price": "119/月",
        "description": "渲染卸载至边缘 GPU，通信 QoS 与算力 QoS 双保障",
        "capabilities": ["render_offload", "compute_qos", "qos_guarantee", "environment_recon"],
        "scenario": "XR/元宇宙 · 通算一体",
    },
    {
        "id": "uav_track", "name": "无人机识别追踪套餐", "price": "79/月",
        "description": "弱算力无人机将识别计算卸载到网络，结合通感实现持续追踪",
        "capabilities": ["target_detection", "target_tracking", "ai_inference", "compute_offload", "precision_location"],
        "scenario": "低空经济 · 无人机监管",
    },
    {
        "id": "smart_factory", "name": "智能工厂套餐", "price": "89/月",
        "description": "面向工厂园区的检测+质检+算力+网络保障一站式方案",
        "capabilities": ["target_detection", "ai_inference", "compute_offload", "qos_guarantee"],
        "scenario": "工厂产线视觉质检与园区安防",
    },
]

PKG_INDEX = {p["id"]: p for p in PACKAGES}

# ===== 内部 Agent 与 NF Tool 映射 =====
AGENTS = {
    "connection": {
        "name": "Connection Agent", "color": "#58a6ff",
        "capabilities": ["qos_guarantee", "event_subscription", "network_diagnosis",
                         "slice_management", "device_wakeup", "mobility_insight",
                         "multipath_boost", "deterministic_latency"],
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
        "capabilities": ["compute_offload", "ai_inference",
                         "render_offload", "compute_qos", "edge_agent_hosting", "federated_learning"],
        "nf_tools": [
            {"tool": "eees_app_deploy", "sbi": "EEES AppContext"},
            {"tool": "compute_offload_submit", "sbi": "Edge Computing API"},
            {"tool": "resource_monitor", "sbi": "OAM/Analytics"},
        ],
    },
    "sensing": {
        "name": "Sensing Agent", "color": "#ff9e3d",
        "capabilities": ["target_detection", "target_tracking", "environment_recon",
                         "sensing_fusion", "traffic_flow_sensing", "vital_sign_detection", "gesture_recognition"],
        "nf_tools": [
            {"tool": "sensing_session_create", "sbi": "Nsensf_Sensing"},
            {"tool": "sensing_result_fetch", "sbi": "Nsensf_SensingData"},
            {"tool": "sensing_config_update", "sbi": "Nsensf_Configuration"},
        ],
    },
    "data": {
        "name": "Data Agent", "color": "#3fb950",
        "capabilities": ["data_query", "network_analytics", "security_check",
                         "capability_register", "identity_service",
                         "traffic_forecast", "digital_twin_feed", "revenue_share"],
        "nf_tools": [
            {"tool": "nwdaf_analytics_query", "sbi": "Nnwdaf_AnalyticsInfo"},
            {"tool": "dccf_data_subscribe", "sbi": "Ndccf_DataManagement"},
            {"tool": "adrf_dataset_fetch", "sbi": "Nadrf_DataManagement"},
        ],
    },
    "location": {
        "name": "Location Agent", "color": "#39d2c0",
        "capabilities": ["precision_location", "geofencing", "trajectory_predict"],
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
