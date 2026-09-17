"""Scenario-level product contracts; independent of legacy capability packages."""
from copy import deepcopy

SCENES = {
    "robot_patrol": {
        "id": "robot_patrol", "name": "机器狗巡检", "headline": "意图驱动，让巡检自主展开",
        "description": "巡检任务下发、异常信息与巡检结果回传。",
        "modes": ["intent"], "preferred_mode": "intent", "tag": "INTENT-DRIVEN INSPECTION",
        "intent_example": "请对园区 A 的重点区域进行机器狗巡检，发现异常后返回现场画面和巡检摘要。",
        "outputs": ["巡检摘要", "异常事件", "现场画面"], "sample_arguments": {},
        "demo_data": {"场景区域": "园区 A", "巡检反馈": "重点区域巡检回执示例", "异常事件": "一处待复核区域（演示）"}},
    "traffic_flow_detection": {
        "id": "traffic_flow_detection", "name": "车流量检测", "headline": "感知城市脉搏，让交通态势可见",
        "description": "车辆检测、数量统计与检测结果回传。",
        "modes": ["intent"], "preferred_mode": "intent", "tag": "URBAN TRAFFIC INSIGHT",
        "intent_example": "请检测 A 路口当前的车流情况，持续反馈检测画面、车流统计和交通状态。",
        "outputs": ["交通报告", "车流统计", "道路状态"], "sample_arguments": {},
        "demo_data": {"检测路口": "A 路口", "车流分布": "东西向较集中（演示）", "观测对象": "机动车 / 非机动车"}},
    "collaborative_tracking": {
        "id": "collaborative_tracking", "name": "端网协同识别追踪", "headline": "端侧看见，网络协同，目标持续可见",
        "description": "终端输入与网络识别追踪服务协同，返回目标与轨迹结果。",
        "modes": ["intent", "api", "tool"], "preferred_mode": "intent", "tag": "DEVICE–NETWORK COLLABORATION",
        "tool_name": "scene_collaborative_tracking",
        "intent_example": "请通过终端 terminal-01 与网络协同，识别 camera-01 中的指定移动目标，持续追踪并返回轨迹摘要与识别结果。", "outputs": ["目标识别", "追踪轨迹", "协同结果"],
        "sample_arguments": {"device_id": "terminal-01", "video_source": "camera-01", "target": "指定移动目标"},
        "demo_data": {"协同终端": "terminal-01", "输入源": "camera-01", "追踪反馈": "目标轨迹回传示例"}}
}


# Product composition references; execution remains with the configured scene provider.
SCENE_COMPONENTS = {
    "robot_patrol": [("target_detection", "异常目标检测"), ("sensing_fusion", "现场多源感知"), ("precision_location", "终端位置"), ("event_subscription", "事件通知")],
    "traffic_flow_detection": [("traffic_flow_sensing", "车流统计"), ("sensing_fusion", "多源观测融合"), ("data_query", "数据查询")],
    "collaborative_tracking": [("target_detection", "目标发现"), ("target_tracking", "轨迹追踪"), ("ai_inference", "识别推理"), ("compute_offload", "边缘计算"), ("qos_guarantee", "连接质量")],
}
for scene_id, components in SCENE_COMPONENTS.items():
    SCENES[scene_id]["provenance"] = {
        "source": "preset", "label": "场景套餐",
        "provider_role": "场景服务方",
        "components": [{"capability_id": cap_id, "role": role} for cap_id, role in components],
    }


def catalog():
    return [{k: deepcopy(v) for k, v in scene.items() if k != "demo_data"} for scene in SCENES.values()]


def tool_definition(scene):
    return {"name": scene["tool_name"], "description": scene["description"],
            "inputSchema": {"type": "object", "properties": {
                key: {"type": "string", "minLength": 1, "maxLength": 256, "description": description}
                for key, description in [("device_id", "参与协同的终端标识"), ("video_source", "已约定的视频源引用"), ("target", "待识别追踪的目标描述")]},
                "required": ["device_id", "video_source", "target"], "additionalProperties": False}}


def demo_result(scene, request_id):
    return {"request_id": request_id, "service_id": scene["id"], "data_source": "demo",
            "status": "demo_complete", "summary": scene["name"] + " · 场景演示已呈现",
            "demo_result": {"text": {
                "robot_patrol": "【演示结果】园区 A 重点区域巡检已完成。发现一处待复核区域，建议安排现场人员确认；其余巡检点未发现异常。",
                "traffic_flow_detection": "【演示结果】A 路口车流检测已完成。东西向车流较集中，南北向通行平稳；建议持续观察东西向排队变化。",
                "collaborative_tracking": "【演示结果】端网协同识别与追踪已完成。目标已从 camera-01 输入中识别，协同服务返回连续轨迹摘要；建议对遮挡区域继续观测。"
            }[scene["id"]], "title": scene["name"], "status": "场景结果示例已就绪", "data": deepcopy(scene["demo_data"])}}
