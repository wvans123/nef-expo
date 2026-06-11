# 6G NEF Demo 前端优化设计（深空电信蓝换肤 + AF 反向调用）

日期：2026-06-11
状态：已与用户确认

## v3 当前边界（2026-06-11，覆盖下文旧 Intent 设计）

- NEF 对 Intent 只负责 Bearer API Key 鉴权、账号识别、`intent:submit` scope 校验、审计、受理和路由。
- Intent 原文转发给合作伙伴网络 Agent；NEF 不做语义解析、能力匹配、Skill 编排或业务执行。
- 伙伴网络 Agent 返回任务 ID 和状态地址；任务状态与最终结果由伙伴系统维护。
- AF 反向调用保留手动模拟链路，不再由本 Demo 的 Intent 关键词匹配触发。
- 下文涉及“NEF 内 Planning Agent 执行”或“Intent 联动反向调用”的内容均为历史设计，不再代表当前实现。

## 背景与目标

nef-expo 是面向运营商伙伴的现场讲解演示（讲解人操作，界面扮演 AF 开发者视角）。
目标：让观众感受到 6G NEF「多种调用方式、繁荣的调用生态、双向开放」。

本期决策记录：

- 视觉风格选定「深空电信蓝」（候选中的 B：深海军蓝 + 青紫霓虹 + 玻璃拟态）。
- 信息架构保持现有 8-Tab 不变（候选中的 A：保守增强）。
- 不做多调法对比工作台。
- 不做 A2A（已另行记录：将来采用"NEF=总代理 Agent"任务委托模式）。
- 新增「AF 反向调用」：网络内部调用 AF 注册进来的能力，触发方式 = Intent 联动为主 + 手动模拟按钮兜底。
- AF 注册 Tab 采用「左注册表单 · 右生态看板」布局（候选布局 A）。

## 1. 范围

| 内容 | 是否本期 |
|---|---|
| 全局换肤（CSS 变量 + hero）| 是 |
| AF 注册 Tab 重做（反向调用看板）| 是 |
| Intent 与第三方能力联动 | 是 |
| 后端反向调用模拟接口 | 是 |
| A2A / 多调法对比 / Tab 重组 | 否 |

技术形态不变：FastAPI 后端 + 无框架单文件 `static/index.html`，所有状态内存存储。

## 2. 全局换肤（深空电信蓝）

只动 CSS 与少量 HTML，不改交互逻辑。

- CSS 变量替换（`:root`）：
  - 背景：深空渐变 `#050b1f → #0a1733`（body 用 fixed 渐变）
  - 面板 `--panel: #0a142e`，卡片 `--card: #0e1d3f`，边框 `--border: #2a4a8a`
  - 主强调 `--accent: #39d2ff`（青），辅助紫 `#bc8cff`，成功 `#39ffb0`，警示橙 `#ffc857`
- 顶栏：玻璃拟态（半透明背景 + backdrop-filter blur），平台名青→紫渐变文字（background-clip: text）。
- 能力超市 banner 升级为开场 hero：渐变大标题「一张网络，无限调用」+ 现有统计数字（N 项能力 / 3 种调用方式 / 5 个套餐）+ REST·MCP·Intent 徽标行。讲解开场画面。
- 能力卡片 hover 辉光（box-shadow 青色微光）、primary 按钮蓝紫渐变、分类色点加 glow。
- 各 Tab 的表格、pre、弹窗、pill、agent-block 同步适配新变量（多数自动继承）。

## 3. AF 注册 Tab 重做（布局：左注册 · 右生态看板）

### 顶部：反向链路图（常驻）

```
AF 能力 ─注册─▶ NEF 能力超市 ─发现─▶ Planning Agent ─编排─▶ NEF 出向网关 ─反向调用─▶ AF Endpoint
                                                        (鉴权·计费·审计)
```

- 静态常驻；当一条反向调用发生（手动或 Intent 联动）时，节点按链路顺序逐个点亮（CSS class 切换动画，总时长约 1.5s）。

### 左列：注册表单

现有字段（名称/类型/描述/端点）+ 新增「Intent 关键词」输入框（逗号分隔，选填；为空则默认用能力名称作关键词）。

### 右列：「我注册的能力」生态看板

当前账号注册的每项能力一张卡片：

- 状态徽章：`registered`（无调用记录）/ `已被网络发现`（有调用记录）
- 统计：被调用次数、最近调用时间、累计模拟收益（每次调用 +0.05 元）
- 「⚡ 模拟网络调用」按钮：调一次 simulate-call 接口
- 调用日志（最近 10 条，倒序）：时间 / 调用方 Agent / 触发源（Intent 文本摘要或「手动模拟」）/ 耗时 ms / 结果状态 / 计费
- 空态：未注册任何能力时显示引导文案（「注册你的第一个能力，让网络发现并调用它」）

刷新机制：该 Tab 激活时每 3 秒轮询 `my-calls` 接口；手动模拟后立即刷新。

## 4. Intent 联动

- `intent.py` 的 `match_capabilities` 匹配范围扩展为 `CAPABILITIES + THIRD_PARTY`。
- 第三方能力进入执行计划时：
  - 步骤标记 `source: "third_party"`、`direction: "reverse"`
  - 执行语义为「NEF 出向网关调用 AF 端点」，调用 stub 返回模拟 AF 响应
  - 同时向 `REVERSE_CALLS` 写入一条台账（触发源 = intent 文本）
- 前端 Intent 结果渲染：third_party 步骤用绿色左边框 + 「↩ 反向调用 AF 能力」徽章，与内部 Agent 步骤形成对比；该步骤的"调用方 Agent"取 Planning Agent 分派的域 Agent（按能力类型映射，ai_model→Computing Agent，data_source→Data Agent，tool→Data Agent）。

## 5. 后端新增（全部内存模拟）

- `REVERSE_CALLS: dict[cap_id, list[record]]`，record 字段：`ts, caller_agent, trigger("manual"|"intent"), trigger_detail, latency_ms, status, fee`
- `POST /api/v1/third-party/{cap_id}/simulate-call`（需鉴权）：生成一条模拟记录（latency 20–80ms 随机，caller_agent 按能力类型映射），返回该记录 + 模拟的请求/响应 payload。
- `GET /api/v1/third-party/my-calls`（需鉴权）：返回当前账号注册的全部第三方能力及各自台账、汇总统计。
- `RegisterAfReq` 增加 `intent_keywords: list[str] = []`；`register_af` 写入 `Capability.intent_keywords`（为空时默认 `[name]`）。
- `stubs.py`：第三方能力 id（`tp_` 前缀）返回通用模拟 AF 响应（含 `provided_by: "third_party_af"`、echo payload、模拟结果字段）。

## 6. 错误处理与边界

- simulate-call 对不存在/不属于当前账号的 cap_id 返回 404/403。
- 服务重启后 THIRD_PARTY 与 REVERSE_CALLS 清空——demo 可接受，README 注明。
- 轮询接口失败时看板静默保持上次数据，不弹错误打断演示。

## 7. 验证

- 新增后端接口写最小 pytest 冒烟测试（subscribe → register-af → simulate-call → my-calls → intent 命中第三方能力）。
- 前端启动后按演示动线人工过一遍：超市 hero → 订阅 → API/MCP/Intent → Skill → 编排 → AF 注册+反向调用（手动 + Intent 联动两条路径）。

---

# v2 增量（2026-06-11 用户反馈后）

设计总原则：一切从"运营商伙伴看演示 / AF 开发者第一视角"出发；review 子代理只用于最重要改动。

## v2-1. 能力超市 → 缩略磁贴墙

- 能力卡片压缩为小磁贴（~150px：emoji 图标 + 名称 + tier 色点 + 小字价格），一屏 30+，分类标题保留，点击磁贴弹详情弹窗（复用现有弹窗）。
- 能力新增 `status` 字段（available / planned）与 `icon` 字段。planned 磁贴标灰（降透明度 + 「规划中」角标），详情显示"即将上线"，不可订阅/调用/参与 Intent 匹配/出现在 MCP 列表。

## v2-2. 能力清单 17 → 32

新增可用（6）：sensing_fusion 多源感知融合、traffic_flow_sensing 车流量感知、render_offload 云渲染卸载、compute_qos 算力 QoS 保障、geofencing 电子围栏、traffic_forecast 车流量预测分析。
新增规划中（9，标灰）：vital_sign_detection、gesture_recognition、edge_agent_hosting、federated_learning、multipath_boost、deterministic_latency、trajectory_predict、digital_twin_feed、revenue_share。

## v2-3. 场景套餐 5 → 8（对齐测试团队场景）

直播计算卸载（计算卸载+算力QoS+通信QoS+诊断，0卡顿换脸=双 QoS 联动）/ 机械臂×机器狗协同 / 多智能体具身交互（AR眼镜×机器狗）/ 机器狗巡检升级（含感知融合：3GPP+非3GPP 数据融合）/ 城市车流量预测 / XR 渲染卸载 / 无人机识别与追踪（弱算力终端借网络算力）/ 智能工厂（保留）。旧 uav_mgmt、livestream、xr_collab_pkg 被新套餐取代。

## v2-4. MCP 只列已订阅

`tools/list` 仅返回当前 API Key 已订阅的可用能力 + 第三方注册能力；前端 MCP 下拉同步。

## v2-5. Intent baseline

链路固定为：NEF 受理（鉴权）→ 意图转发至网络内部 Planning Agent → Planning Agent 语义解析、识别 N 个业务 → 业务编排分派各业务 Agent（一个意图可涉及多业务）→ 业务 Agent 调 NF Tool 执行 → NEF 聚合返回 AF。后端 pipeline 阶段文案与前端流程图按此改写，Planning Agent 节点紫色突出。

## v2-6. 业务粒度原则

每个能力 = AF 视角一次有意义的业务动作；跨能力"联动"（如双 QoS）在套餐叙事层表达，不做巨型能力。
