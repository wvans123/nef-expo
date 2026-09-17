# 6G NEF 能力开放平台 Demo

一个面向运营商现场演示的 **6G 网络能力开放功能（NEF, Network Exposure Function）** 原型。
后端为 FastAPI，前端为原生 HTML/CSS/JS（无构建步骤），用于向第三方应用（AF, Application Function）
开发者展示"一张网络、无限调用"的能力开放生态：服务化接口（REST）、类 MCP 接口、意图接口、
场景一键运行、自助编排、以及 AF 双向开放与网络反向调用。

> 状态全部存于内存，重启服务即清零——演示从"新 AF 入驻"讲起即可。


## 当前展示更新（2026-09-17）

入口：`/`（`static/index.html`）。直接在原版工作台上增量修改，保留原有布局、能力详情弹窗、订阅、拖拽排序、参数表单和逐级鉴权；不再维护第二套活动展示页。原 `/static/showcase.html` 书签自动跳转到这里。

可见页签：**能力超市 / 订阅与鉴权 / API 直调 / MCP 接口 / 意图受理 / 自助编排 / 双向开放 · MCP**。

- **能力超市**保留基础能力与三大场景套餐，场景卡显示可点击的基础能力组合，并展示 TRF / ARF 导入目录和自建套餐定义。
- **三个场景以 Intent 为主**：机器狗巡检、车流量检测、端网协同识别追踪。端网协同仍保留 API / Tool 参数化调用，其他基础能力保留 API / MCP 接入。
- **自助编排**选择能力、调整步骤、检查配置冲突；可选 LLM 根据需求推荐组合，经采用和确认后保存声明式套餐，再发布至网络目录。NEF 不因此成为自主 Agent，也不会在保存时执行步骤；网络执行与参数绑定由内部对接。
- **双向开放**通过名称、URL、说明组成的 JSON 注册 MCP Server；经运维批准的地址可真实连接并发现工具，再同步至 TRF / ARF。登记、发现、发布确认分别显示；后端记录 `source: AF` 与认证账号，随发布报文传给网络，能力超市同时展示 AF 来源及同步状态。
- **网络经 NEF 调用 AF**：ARF / TRF 是网络内部目录，接收 AF 工具声明与 NEF MCP 入口，而不是可绕过 NEF 的 AF 原始 URL。内部网元以独立凭证访问 NEF，NEF 按 AF 账号授权范围与 URL 允许列表校验、验证工具参数，再向 AF 真实发送 `tools/call`，保持实际 `CallToolResult` 与 `isError`。页面可查看发布报文和最近网络调用状态。
- **调用与鉴权**展示实际身份、入口权限和订阅校验回执；文字业务结果优先，图片 / 视频按需展开。场景回传仍只在具体调用页出现。
- **真实调用**：活动页面直接发送 live 请求，移除执行方式和示例意图；Intent 可选“不指定场景”，走单独配置的通用接收地址。未配置返回待对接，不回落到模拟结果。旧后端 demo 契约仅保留兼容，HTTP 受理不等于业务完成。
- **简化回传**：自动准备并复用当前场景接口；“接口信息”可查看对接资料。同事只接收一个 `/api/v1/scene-feedback` 地址与场景 Key；车流量支持 `{"final_result":"文字结果"}`，其他文字、数据、图片、视频也通过同一接口提交。
- **目录展示**：主页不再强调 Intent 标签，场景卡展示可点击的基础能力组合与套餐设计来源；网络导入和自助编排定义分别标明来源。浏览器进入目录页、以及停留超市 / 双向开放时每 30 秒自动同步，不再提供手动同步网络目录按钮。
- **边界**：当前目录契约是本项目的对接约定，不是 TRF / ARF 标准协议。生产网络接口仍待同事提供；本地账号、权益、登记与回传保存在内存。mTLS / OAuth、资源级策略、生产持久化未接入。
- **本期隐藏**：对外 Skill / 场景方案、AF 智能终端不进入展示动线。对应页签隐藏，旧后端接口保留兼容但不进入本期演示。

详见[演示手册](docs/demo-playbook.md)、[场景对接说明](docs/reference/integration.md)、[展示与网络对接设计](docs/superpowers/specs/2026-06-11-frontend-demo-redesign-design.md)和[文档索引](docs/README.md)。

---

## 一、环境要求

| 项目 | 版本 / 说明 |
|---|---|
| Python | 3.11+（已在 3.14 上验证） |
| 操作系统 | Windows / macOS / Linux 均可（开发环境为 Windows + PowerShell） |
| 依赖 | `fastapi`、`uvicorn`、`httpx`、`jsonschema`（运行）；`pytest`（测试） |

---

## 二、换电脑启动与配置

### 1. 下载、启动

安装 Python 3.11+。在 [GitHub 仓库](https://github.com/wvans123/nef-expo) 点击 **Code → Download ZIP** 并解压，进入含 `start.py` 的目录，在终端执行：

```bash
python -m pip install -r requirements.txt
python start.py
```

本机打开 `http://127.0.0.1:8069/`；同事打开 `http://<这台电脑的IP>:8069/`。默认监听 `0.0.0.0:8069`，无需原域名、Tunnel、Node 或前端构建。`0.0.0.0` 不能填成同事的访问地址。端口占用时用 `python start.py --port 8070`，不要强杀未知进程。

首次启动自动创建 `config/integration.local.json` 和 `config/composer.local.json`，已有文件不会覆盖。暂不使用智能推荐时无需模型 Key；使用时在启动终端设置 `NEF_COMPOSER_API_KEY`，远程模型地址已在模板中填写。

仅在获准测试内网使用，不直接暴露公网；跨机不通先检查 IP、路由和 8069 入站规则，不关闭整个防火墙。此版本单进程内存保存，重启清空账号、订阅和回传 Key。GitHub 上传代码不会迁移这些数据，也不会更新另一台已运行的进程。

### 2. POST 地址只改这一份文件

打开自动生成的 **`config/integration.local.json`**，修改对应字段；改地址或价格后下一次请求生效，不用重启。JSON 不支持注释，未配置项保留 `null`。

| 用途 | JSON 字段 | 填什么 |
|---|---|---|
| 订购套餐后发给农场 | `subscriptions.callback_url` | 完整地址，例如 `http://<农场IP>:<端口>/business/v1/service-plans` |
| 套餐价格 | `subscriptions.plan_prices` | 将对应套餐的 `null` 改为双方确认的数字；测试免费也要明确填 `0`，否则不发送通知 |
| 外部 MCP 登记发布到 ARF/TRF | `registry.publish_url` | 对方接收登记的完整 POST 地址；当前只支持一个接收方 |
| 对方访问本 NEF 的地址 | `registry.nef_base_url` | `http://<NEF电脑IP>:8069`，用于生成 MCP 代理入口 |
| 允许连接的外部 MCP | `registry.mcp_servers` | 按[农场联调](docs/reference/farm-integration.md#5-nef-运维配置)填精确 URL 允许列表；只登记不代表已经发布 |
| 车流量 Intent | `bridge.scenes.traffic_flow_detection.intent.url` | 已填 `http://10.70.113.122:5432/car/start`，按部署实际修改 |
| 不指定场景的 Intent | `bridge.intent` | 将 `null` 改成 `{"url":"http://<接收方IP>:<端口>/<路径>","method":"POST","body":{"user_request":"$text"}}` |
| 原子能力 API / MCP | `bridge.capabilities.<能力ID>` | route 对象，结构见 `config/bridge.example.json` |

普通同日内网无鉴权测试可保留 `token_env: null`；有鉴权时这里只填凭据的环境变量名，不填 Key 本身。完整字段和回包见[套餐通知](docs/reference/subscription-query.md#10-跳转订购与套餐通知)、[车流量执行与回传](docs/reference/integration.md#车流量联调)和[农场 MCP 联调](docs/reference/farm-integration.md)。

兼容旧部署：显式设置的 `NEF_BRIDGE_CONFIG` / `NEF_REGISTRY_CONFIG` / `NEF_SUBSCRIPTION_CONFIG` 优先于统一文件；换电脑不要照搬这些旧变量。仅在没有统一文件时，订购通知还会兼容读取 `config/subscription.local.json`。高级操作可用 `NEF_INTEGRATION_CONFIG` 指定统一文件位置。

### 3. 对方改字段时，改哪个文件

只改 IP、端口或路径时不改 Python。请求格式变化时按下表定位，改 Python 后需要重启并重新准备内存账号。

| 改动 | 文件 / 位置 |
|---|---|
| `subscriberId`、`servicePlan`、`networkCapabilities` 等通知字段 | `subscription_notifications.py`：`_notify_plan()`、`deliver()` |
| POST 到 ARF/TRF 的 MCP 登记正文 | `network_registry.py`：`_publication()` |
| 选定能力或场景发布正文 | `catalog_publication.py` |
| 车流量发送字段，例如 `user_request` | `config/integration.local.json` 的 `bridge.scenes.traffic_flow_detection.intent.body` |
| 我方回传路径、`final_result` 接收与解析 | `exhibition.py`：`mount_routes()` 内 `/api/v1/scene-feedback` |
| 我方订购 / 查询接口路径 | `server.py` |

旧域名部署仍可按[运行手册](docs/demo-playbook.md#cloudflare-tunnel-演示部署)使用；换电脑不需要先配置 Tunnel。

### 4. 运行测试（开发时可选）

```bash
pytest -q
```

前端鉴权、MCP 发现与开放路径回执规则测试（可选，需要 Node.js）：

```bash
node tests/test_showcase_auth.cjs
node tests/test_showcase_mcp.cjs
node tests/test_showcase_story.cjs
node tests/test_composer.cjs
node tests/test_purchase.cjs
```

---

## 三、快速体验（5 分钟）

1. 顶栏注册演示账号，能力超市查看三个场景及原有基础能力卡片；点击能力仍可查看参数、价格并订阅。
2. 填好执行地址后开通场景，进入意图受理；查看对方的真实文字结果和鉴权回执。未配置的场景只显示待对接。
3. 自助编排中拖入或点击能力、拖拽调整顺序。交付方式、GPU 上限及目标来源收在“可选约束”中，默认不填。可选模型推荐经采用进入草稿，填写名称并确认保存；发布按钮交付目录定义，不表示执行完成。
4. 双向开放提交 MCP Server JSON；连接并发现工具后展开参数声明，按需同步 TRF / ARF。无配置时明确待对接。
5. MCP 接口先连接 / 发现、再选工具；API 直调从已知能力开始。两者保留原版请求、参数、鉴权和响应两栏。
6. 实际接口配置后直接调用；场景数据源仅需一个回传地址与 Key。文字优先，媒体按需展开。

## 四、接口和执行边界

- **认证与授权分开**：场景使用本地 AF Key + scope + 场景订阅；场景未开通返回 403。旧基础能力的等级 / 订阅 / 按次付费接口保留。Key 不等于标准 mTLS / OAuth 安全接入。
- **Intent 原文转发**：三个场景调用 `/api/v1/services/{service_id}/intent`；网络侧负责解析与执行。没有内部 Intent ID 也可回文字，不虚构 Planning Agent 轨迹。
- **API / MCP 并行**：已知能力走 HTTP API；AF 通过 `/mcp` 初始化、发现、选用和调用工具。两者可以映射同一内部 HTTP 服务，不要求网络内部都重写为 MCP。
- **套餐定义不是执行计划引擎**：NEF 保存有序能力引用，发布至 TRF / ARF；真实部署、参数绑定和失败处理仍需网络侧契约。
- **双向开放**：外部 MCP Server 先登记，运维批准后才实际发现工具；发现与同步分别显示，不自动授予外部工具执行权。
- **结果证据**：demo 明确标注；live 无配置返回 503、不回落；HTTP 受理不等于业务完成。场景级回传与某次调用不自动关联。

对接地址统一读取 `config/integration.local.json`，字段与旧配置兼容规则见第二节。智能推荐默认读取 `config/composer.local.json`（可由 `NEF_COMPOSER_CONFIG` 覆盖），模板为 `config/composer.example.json`；远程 Base URL `https://sub2api.2012wtlab.com/v1`、模型 `gpt-6-astra`、Responses 协议及 `low` 档位已填写。模型 Key 使用 `NEF_COMPOSER_API_KEY`，不读取 Codex 密钥、不依赖本机 CPA。此前 `high` 档位通过一次真实推荐；`low` 的真实响应尚待验证。每次请求内嵌可用原子能力池与参数 schema；新代码按超时、上游错误、连接失败和响应格式错误分类，并返回排查用 request_id，不暴露密钥或上游正文。历史运行证据见[演示运行手册](docs/demo-playbook.md#智能编排准备与现场操作)。

跨应用读取订阅：`GET /api/v1/integration/subscriptions?account_id=1`，其中 `1` 是在 NEF 注册的账号名，不是自动编号。1.1 响应的 `purchased_packages` 直接提供已购场景/能力套餐及详情，适合农场平台展示“已购网络套餐”；原子工具、参数 schema、权益来源等旧字段仍保留，不返回 API Key。公网仍需 Access 机器凭据，接口详细契约见[订阅查询接口](docs/reference/subscription-query.md)。农场查询套餐、MCP 注册发现、发布网络和网络回调的步骤见[农场平台联调](docs/reference/farm-integration.md)。场景开通不要求组件逐一订阅，但组件单独调用仍校验各自权益；订阅数据仍为内存态，重启后需恢复。

订购主流程：农场按钮跳转 `/?account_id=1`，用户开通后由 NEF 向配置的 `/business/v1/service-plans` POST `subscriberId` + `servicePlan`。套餐内含 `planId/showName/description/price`；默认发送套餐可用能力组成 `networkCapabilities`，用户全部取消勾选才省略并交给 PA 自主编排。NEF 不实现 PA/CA 决策。价格必须明确配置；失败保留订阅并支持同事件手动重试。真实农场地址及接收回执待联调；本次上传不重启已有进程。唯一契约见[套餐订购通知与订阅查询](docs/reference/subscription-query.md#10-跳转订购与套餐通知)，新部署使用统一配置模板 `config/integration.example.json`。

当前联调的外发 `subscriberId` 固定为 `subscriber-001`，定义在 `subscription_notifications.py` 的 `SUBSCRIBER_ID`，无需新增配置。跳转和查询仍使用本地账号 `1/2/3`；对方会将这些账号的通知都归入同一个测试订购者。

向 ARF/NRF 提供选定的本地能力或场景元数据，使用独立的[网络目录发布接口](docs/reference/network-catalog.md)。这是待同事确认的项目契约，不是已实现标准 NRF 注册；与农场订购通知、AF MCP 注册分开。

对接同事仅需 [场景接口对接说明](docs/reference/integration.md)；运维与网络目录边界见 [展示设计](docs/superpowers/specs/2026-06-11-frontend-demo-redesign-design.md)。

## 五、项目结构

```text
server.py             FastAPI 路由、账号权益、API / MCP / 场景调用
start.py              换机启动，初始化本地配置，监听 0.0.0.0:8069
integration_config.py  统一对接配置读取
skills.py             基础能力、标准分类、组合套餐与参考映射
composition.py        配置冲突检查、限定目录的 LLM 推荐（不执行）
subscription_query.py  对外订阅查询响应模型（不含凭据）
subscription_notifications.py  订购通知、可选能力范围与手动重试
catalog_publication.py  选定本地能力/场景的目录发布报文
registry.py           旧第三方注册与调用台账（兼容）
intent.py / stubs.py   旧意图与参考执行（不作为当前真实结果）
scene_services.py     三场景契约与明确标注的演示文字
exhibition.py         真实转发与统一场景回传
network_registry.py   TRF / ARF 目录、MCP 注册发现、套餐发布
static/index.html     活动原版工作台，保留原布局与交互
static/workbench.js    新接口接入及原交互的增量控制逻辑
static/workbench.css   原主题的少量新增组件样式
static/showcase.html   旧书签兼容跳转，不再独立展示
static/showcase-mcp.js / showcase-story.js  共用发现与回执语义
config/               内部执行、网络目录配置模板
```

所有业务状态保存在单进程内存。重启清除账号 Key、订阅、套餐定义、注册、目录及回传数据；浏览器中保存的账号记录会失效，需重新注册。

## 六、能力目录与标准复核

分类：接口参考。复核日期：2026-09-10。以下覆盖 `skills.py` 的 33 个内置能力，含规划中能力。**本项目的 ID、参数结构和 REST / Tool 封装均为项目接口，不等于对应标准已经定义了同名 NEF 北向 API，更不等于已通过符合性测试。**

页面用简短标签区分“5G 能力参考”“通感能力探索”“平台扩展”；标签指设计依据和本原型定位，不是商用部署证明。`standard_basis.api_contract=project_defined` 随能力元数据返回。AF 动态登记能力单独标为 AF 扩展。

重要修正：
- 不能把通感全部说成“尚未标准化的 6G”。本次读取的 TS 22.137 V19.1.0 已有 **5G 无线感知服务要求**，但它不是这套 Tool 的 API 规范。6G/IMT-2030 是演进背景，不作为本项目接口符合性的依据。
- AKMA 以 UE 的 5G 主认证与应用密钥上下文为基础，不是向任意 AF/Agent 颁发通用数字身份。应用登记与平台凭证保留为产品能力，不声称实现 AKMA。
- 网络分析、定位、ATSSS 等存在标准能力，也不代表 AF 可以通过本项目简化字段直接调用内部 NF 服务；须映射授权、标识、请求参数及返回格式。
- 切片创建、CPU/GPU 调度、模型部署、收益结算是应用/平台或管理域扩展；不能写成 NEF 已有的通用标准操作。

| 能力 ID | 展示名称 | 分类 | 依据与需要保留的边界 |
|---|---|---|---|
| `target_detection` | 目标检测 | 通感能力探索 | S2 §5.2.1 支持对象检测要求；模型类别与置信度字段为产品定义。 |
| `target_tracking` | 目标追踪 | 通感能力探索 | S2 §5.2.1 支持跟踪和服务连续性；本项目 target_id 和报告结构自定义。 |
| `environment_recon` | 环境重构 | 通感能力探索 | S2 §§3.1、5.1 涉及环境特征；点云/mesh/voxel 格式与重构算法是扩展。 |
| `sensing_fusion` | 多源感知融合 | 通感能力探索 | S2 §5.2.1 有联合处理 3GPP/非 3GPP 数据要求；具体融合模式及接口自定义，不承诺全天候效果。 |
| `traffic_flow_sensing` | 车流量感知 | 平台扩展 | S2 §4.1 提及交通管理；车流密度、计数和拥堵指标是场景产品输出，输入不必然是无线感知。 |
| `vital_sign_detection` | 生命体征感知（规划中） | 通感能力探索 | S2 §4.1 涉及健康与活动监测；未逐项验证本项目呼吸/心率参数，保持规划，不作医疗准确性承诺。 |
| `gesture_recognition` | 手势姿态识别（规划中） | 通感能力探索 | S2 §5.1 涉及运动/手势；本项目尚为规划，具体识别服务未验证。 |
| `sensing_fence` | 感知虚拟围栏 | 通感能力探索 | S2 §5.2.1 对象/区域感知要求可作基础；周界和告警逻辑是产品组合。 |
| `compute_offload` | 计算卸载 | 平台扩展 | S7 支持边缘应用架构；不等同于本项目通用任务调度/模型部署 API。 |
| `ai_inference` | AI推理服务 | 平台扩展 | S7 仅作边缘应用承载背景；通用 LLM/视觉推理 API 未据此认定为 NEF 标准能力。 |
| `render_offload` | 云渲染卸载 | 平台扩展 | 渲染与帧率/分辨率控制为应用扩展；S7 不证明存在同名 NEF GPU 渲染 API。 |
| `compute_qos` | 算力服务保障 | 平台扩展 | CPU/GPU 份额、优先级、抖动目标为调度平台策略，不是通信 QoS API。 |
| `edge_agent_hosting` | 边缘智能体托管（规划中） | 平台扩展 | S7 可作边缘承载参考；Agent 镜像部署/托管为规划中的平台扩展。 |
| `federated_learning` | 联邦学习编排（规划中） | 平台扩展 | 联邦学习技术背景不等同于可向任意 AF 开放的训练编排 API；保持规划，未核实该接口标准映射。 |
| `qos_guarantee` | 应用 QoS 请求 | 5G 能力参考 | S1 的 QoS 会话 API 为参考；简化 device_id/latency/bandwidth 仍需映射会话、流和策略，不保证任意目标可满足。 |
| `event_subscription` | 事件订阅 | 5G 能力参考 | S1 的 MonitoringEvent 为参考；四种本地 event_type 须逐一映射标准事件，不能视作同一通用事件资源。 |
| `network_diagnosis` | 网络诊断 | 平台扩展 | 综合体验评分与建议为产品分析，不是已核实的标准通用 NEF 诊断 API。 |
| `slice_management` | 切片服务申请 | 平台扩展 | S6 有切片架构；create/modify/release 为本项目对服务管理方的申请契约，不是 NEF 任意创建切片。 |
| `device_wakeup` | 设备触达请求 | 平台扩展 | 设备触达按提供方契约适配；paging/WUS/NIDD 不能视为可互换的标准 AF 唤醒选项。保留旧字段仅为兼容。 |
| `mobility_insight` | 移动性洞察 | 5G 能力参考 | S3 §6.7.2 UE mobility analytics 为参考；任意目标群体和时间窗是简化产品参数。 |
| `multipath_boost` | 多路径聚合加速（规划中） | 5G 能力参考 | S6 §5.32 ATSSS 为参考；保持规划，取消无条件蜂窝/Wi-Fi/卫星聚合承诺。 |
| `deterministic_latency` | 确定性时延（规划中） | 5G 能力参考 | S6 §4.4.8 TSC/时间同步/DetNet 为参考；保持规划，不意味着仅传 device_id 即获有界时延。 |
| `precision_location` | 终端位置服务 | 5G 能力参考 | S4 §6.1 是 Nlmf_Location 内部服务，不是同名 NEF 北向接口；精度是申请目标，不承诺亚米/厘米级结果。 |
| `geofencing` | 电子围栏 | 5G 能力参考 | S1 事件监测及 S4 定位可作为组合依据；设备围栏的区域和触发字段为产品封装。 |
| `trajectory_predict` | 轨迹预测（规划中） | 平台扩展 | S3 UE mobility 可作方向参考；任意 target_id 的轨迹预测仍属规划产品扩展。 |
| `data_query` | 数据服务 | 平台扩展 | 覆盖图/热力图/历史性能等数据集访问为平台定义，不声称通用 NEF 数据湖 API。 |
| `network_analytics` | 网络智能分析 | 5G 能力参考 | S3 §§6.4、6.7、6.7.5 分别支持业务体验、UE 相关及异常行为分析背景；容量预测等本地枚举不逐字对应标准 Analytics ID。 |
| `traffic_forecast` | 车流量预测分析 | 平台扩展 | 行业车流预测模型与结果定义，不应归为 NWDAF 原生道路交通预测 API。 |
| `digital_twin_feed` | 数字孪生数据底座（规划中） | 平台扩展 | 数字孪生数据供给为规划中的平台服务；未核实同名标准北向 API。 |
| `identity_service` | 应用接入身份 | 平台扩展 | S5 的 UE-AF 应用密钥机制不能证明任意 Agent 身份签发；当前能力是平台身份登记与凭证管理封装。 |
| `security_posture` | 连接安全态势 | 平台扩展 | S3 §6.7.5 异常行为分析可作输入；风险评分、depth 及处置建议为产品扩展。 |
| `capability_register` | 能力注册 | 平台扩展 | 本项目 AF MCP 登记/发现/发布协议为平台扩展，不等同于 CAPIF API 发布实现或标准 TRF/ARF 接口。 |
| `revenue_share` | 生态收益结算（规划中） | 平台扩展 | 收益分账/结算为规划中的商业平台能力，不能类比 CHF 就认定为标准 NEF 接口。 |

### 本次使用的官方核对基线

以下 PDF 本次均从 ETSI 官方站点取得 HTTP 200 并读取原文；是本次选定的核对基线，不声称各系列最新版本。标准文件只支持表中明确对应的技术方向/要求；“未核实”不是不存在的证明。原 README 对 TR 22.837 的笼统映射不再作为逐项证据。

- **S1**：[TS 29.522 V18.10.0](https://www.etsi.org/deliver/etsi_ts/129500_129599/129522/18.10.00_60/ts_129522v181000p.pdf)：5G NEF 北向 API；检查 MonitoringEvent、AsSessionWithQoS 相关说明及其对 TS 29.122 的引用。
- **S2**：[TS 22.137 V19.1.0](https://www.etsi.org/deliver/etsi_ts/122100_122199/122137/19.01.00_60/ts_122137v190100p.pdf)：§1 范围、§4.1 服务概述、§5.1/5.2.1 功能要求；5G 无线感知，不是本项目 Tool 规范。
- **S3**：[TS 23.288 V18.13.0](https://www.etsi.org/deliver/etsi_ts/123200_123299/123288/18.13.00_60/ts_123288v181300p.pdf)：§6.4、§6.7.2、§6.7.5 网络分析背景。
- **S4**：[TS 29.572 V18.11.0](https://www.etsi.org/deliver/etsi_ts/129500_129599/129572/18.11.00_60/ts_129572v181100p.pdf)：§6.1 Nlmf_Location 服务。
- **S5**：[TS 33.535 V18.8.0](https://www.etsi.org/deliver/etsi_ts/133500_133599/133535/18.08.00_60/ts_133535v180800p.pdf)：AKMA 的 AAnF、UE 主认证与 UE-AF 应用密钥上下文。
- **S6**：[TS 23.501 V18.12.0](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.12.00_60/ts_123501v181200p.pdf)：§4.4.8、§5.32 的架构背景。
- **S7**：[TS 23.558 V18.11.0](https://www.etsi.org/deliver/etsi_ts/123500_123599/123558/18.11.00_60/ts_123558v181100p.pdf)：§1、§6 的边缘应用架构背景。

本次未做标准 OpenAPI 逐字段一致性、正式鉴权互通、无线感知性能、6G 网络部署或场景真实算法验收；不能把目录复核说成标准认证。AKMA/CAPIF 的身份边界与场景授权责任继续维护在 [鉴权设计](docs/superpowers/specs/2026-06-15-dynamic-auth-and-dispatch-design.md)。

---

## 七、推送到 GitHub

已有远程为 `https://github.com/wvans123/nef-expo.git`，当前开发分支为 `main`；不要重复创建仓库或覆盖远程。确认测试通过并检查待提交文件不含凭据后：

```bash
git status --short
git add <已检查的变更文件>
git diff --cached --check
git commit -m "Update NEF integration"
git push origin main
```

`.runtime/`、`config/*.local.json` 中当前列入 `.gitignore` 的本地配置和服务端环境变量不上传；各类 `*.example.json` 是可提交模板。GitHub 推送不等于正在运行的 NEF 自动更新，Python 变更仍需协调加载。
