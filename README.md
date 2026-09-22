# 6G NEF 能力开放平台 Demo

一个面向运营商现场演示的 **6G 网络能力开放功能（NEF, Network Exposure Function）** 原型。
后端为 FastAPI，前端为原生 HTML/CSS/JS（无构建步骤），用于向第三方应用（AF, Application Function）
开发者展示"一张网络、无限调用"的能力开放生态：服务化接口（REST）、类 MCP 接口、意图接口、
场景一键运行、自助编排、以及 AF 双向开放与网络反向调用。

> 状态全部存于内存，重启服务即清零——演示从"新 AF 入驻"讲起即可。


## 当前展示更新（2026-09-21）

入口：`/`（`static/index.html`）。直接在原版工作台上增量修改，保留原有布局、能力详情弹窗、订阅、拖拽排序、参数表单和逐级鉴权；不再维护第二套活动展示页。原 `/static/showcase.html` 书签自动跳转到这里。

可见页签：**能力超市 / 订阅与鉴权 / API 直调 / MCP 接口 / 意图受理 / 自助编排 / 双向开放 · MCP**。

- **能力超市**按 TRF 四类展示已可用工具，隐藏规划中和旧生态服务；保留三大场景套餐。首页底部可同步/撤回本地能力、核对状态；TRF 目录来源切换收在运维视图的折叠设置中。显式发布的外部工具与自助套餐展示为带图标和用途说明的“扩展能力”；未发布或取消发布的内容不展示。开通场景后留在当前页，主动点击“进入场景”才跳转。
- **三个场景以 Intent 为主**：机器狗巡检、车流量检测、端网协同识别追踪。端网协同仍保留 API / Tool 参数化调用，其他基础能力保留 API / MCP 接入。
- **自助编排**选择能力、调整步骤、检查配置冲突；可选 LLM 根据需求推荐组合，经采用和确认后保存声明式套餐，再显式发布到本地首页；套餐不发到 TRF MCP Server 接口。NEF 不因此成为自主 Agent，也不会在保存时执行步骤；网络执行与参数绑定由内部对接。
- **双向开放**填写服务名称、描述和 URL，默认名称 `patrol-car-managementx`，URL 留空待提供。连接并发现工具后，显式点击“发布”才上首页并 POST 至 TRF；支持“取消发布”、撤回重试及未发布/发现失败记录的“删除记录”。已有记录使用“重新发现工具”，避免与首次接入混淆。无 Key 开放登记也只登记与发现，不自动发布。
- **网络经 NEF 调用 AF**：新 TRF 契约接收六个基础字段及 `isThirdParty: true`，其中 url 是填写的外部 MCP 地址。NEF 代理调用仍独立保留，不能将 TRF 直连与 NEF 代理混为一条调用链。内部网元以独立凭证访问，NEF 核验已发布状态、AF 账号范围、URL 允许列表和参数后转发真实 `tools/call`。取消发布立即禁止新调用；预览与调用记录接口保留供联调使用。
- **第三方工具订阅**：其他账号在商城点击工具即可订阅、取消订阅，并通过“去 MCP 调用”使用。当前演示免费，PRO/MAX 不自动开通；下架暂停调用，删除清理权益。发布、订阅和网络调用授权分别管理，完整契约见 [TRF 与工具订阅参考](docs/reference/network-catalog.md#5-第三方工具的账号订阅与调用)。
- **调用与鉴权**展示实际身份、入口权限和订阅校验回执；页面显示文字与结构化数据，媒体仅保留后端接收。场景回传仍只在具体调用页出现。
- **真实调用**：活动页面直接发送 live 请求，移除执行方式和示例意图；Intent 可选“不指定场景”，走单独配置的通用接收地址。未配置返回待对接，不回落到模拟结果。旧后端 demo 契约仅保留兼容，HTTP 受理不等于业务完成。
- **简化回传**：同事无需 NEF Key，向 `/api/v1/scene-feedback/{scene_id}` POST `{"final_result":"文字结果"}`，GET 同一路径即可自查。三场景通道共享，页面不登录也可读；旧带接收 Key 接口保留备用。`?ops=1` 显示“回传地址”和通知诊断，只是显示开关，不是鉴权。命令见 [curl 手册](docs/reference/manual-curl.md)。
- **TRF 目录同步**：首页底部显式同步 23 项可用本地能力，POST 带 `isThirdParty: false`；逐项 GET 核对后显示登记圆点，支持整体撤回。普通首页只展示同步操作和状态；`?ops=1` 中的“目录来源设置”可预览 TRF 四类服务登记，不自动变成可调用工具，也不影响普通商城来源。页面加载/定时刷新只读本地缓存。
- **订阅费用与说明**：估算月费用包含等级基础价和已购场景价格，场景按购买时所选能力与折扣计价；取消后移除。PRO/MAX 可用能力可点击查看用途，完整规则见[订阅参考](docs/reference/subscription-query.md#103-nef-服务端配置)。
- **边界**：当前目录契约是本项目的对接约定，不是 TRF 标准协议。生产网络接口仍待同事提供；本地账号、权益、登记与回传保存在内存。mTLS / OAuth、资源级策略、生产持久化未接入。
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

**Windows 独立后台运行（关闭 Codex / 终端后仍可用）：** 安装依赖后，先停止已核对身份的前台 NEF，在项目目录执行一次：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-NefBackground.ps1
```

脚本创建并立即启动 Windows 计划任务 `NEF-Expo`；任务以当前普通用户身份无窗口运行，用户登录 Windows 后自动启动，异常退出每分钟重试（最多 999 次），不依赖 Codex。默认仅监听 `127.0.0.1:8069`，适用于本机与现有 Tunnel；同事需要内网直连时首次安装追加 `-ListenAddress 0.0.0.0`。重复执行不会重启已运行的任务，也不会覆盖不同配置的同名任务。任务在用户注销后停止；电脑休眠或关机时不可访问。

任务使用安装时选定的 Python；可用 `-PythonPath "完整的python.exe路径"` 指定已安装依赖的环境。智能编排沿用当前 Windows 用户已保存的 `NEF_COMPOSER_API_KEY`，不把 Key 写入脚本或任务参数；仅在 Codex / 临时终端中设置的变量不会传给该任务。查看、停止、重新启动可直接打开 Windows“任务计划程序”→“任务计划程序库”→`NEF-Expo`；先结束、再运行即可重启，内存数据会清空。后台日志追加写入 `.runtime/nef-background.stdout.log` 和 `.runtime/nef-background.stderr.log`。不要同时执行 `python start.py`。

### 2. POST 地址只改这一份文件

打开自动生成的 **`config/integration.local.json`**，修改对应字段；改地址或价格后下一次请求生效，不用重启。JSON 不支持注释，未配置项保留 `null`。

| 用途 | JSON 字段 | 填什么 |
|---|---|---|
| 订购套餐后发给农场 | `subscriptions.callback_url` | 完整地址，例如 `http://<农场IP>:<端口>/business/v1/service-plans` |
| 套餐折扣 | `subscriptions.discount` | 模板为 `0.8`：所选能力月价之和 × 折扣，保留两位小数 |
| 固定套餐价格 | `subscriptions.plan_prices` | 未配置 discount 时使用；将对应 `null` 改为双方确认的数字，免费明确填 `0` |
| 通知范围 | `subscriptions.account_ids` / `notify_plans` | `null` 表示全部；否则填账号列表 / `scene:robot_patrol` 等完整套餐键列表 |
| 启动清理对端套餐 | `subscriptions.reset_partner_plans_on_start` | 默认 `false`；仅在确认可删除固定测试订购者的套餐后设 `true` |
| TRF MCP 服务发布、查询、撤回 | `registry.trf_mcp_servers_url` | 完整集合地址 `http://<TRF-IP>:<端口>/trf/api/v1/mcp-servers`；POST/GET 同址，DELETE 追加 serverName |
| 对方访问本 NEF 的地址 | `registry.nef_base_url` | `http://<NEF电脑IP>:8069`，用于首页本地能力的单工具 MCP 入口及独立代理入口 |
| 允许连接的外部 MCP | `registry.mcp_servers` | 按[农场联调](docs/reference/farm-integration.md#5-nef-运维配置)填精确 URL 允许列表；只登记不代表已经发布 |
| 开放 MCP 登记归属 | `registry.open_registration_account` | 无 Key 登记的来源账号，默认 `1` |
| 放宽 MCP 允许列表 | `registry.allow_unlisted_mcp_servers` | 默认 `false`；仅获准隔离测试网可启用，存在任意地址探测风险 |
| 车流量 Intent | `bridge.scenes.traffic_flow_detection.intent.url` | 填 `http://<车流服务IP>:5432/car/start`；发布模板留空，避免误连现场 |
| 机器狗 Intent / 结果 | `bridge.scenes.robot_patrol.intent` / `result` | 分别填 text/plain POST 地址与 GET latest 地址；模板 URL 留空，详见[场景接口](docs/reference/integration.md) |
| 端网协同 Intent | `bridge.scenes.collaborative_tracking.intent.url` | 等待对方提供完整地址 |
| 不指定场景的 Intent | `bridge.intent` | 将 `null` 改成 `{"url":"http://<接收方IP>:<端口>/<路径>","method":"POST","body":{"user_request":"$text"}}` |
| 原子能力 API / MCP | `bridge.capabilities.<能力ID>` | route 对象，结构见 `config/bridge.example.json` |

普通同日内网无鉴权测试可保留 `token_env: null`；有鉴权时这里只填凭据的环境变量名，不填 Key 本身。完整字段和回包见[套餐通知](docs/reference/subscription-query.md#10-跳转订购与套餐通知)、[车流量执行与回传](docs/reference/integration.md#车流量联调)和[农场 MCP 联调](docs/reference/farm-integration.md)。

兼容旧部署：显式设置的 `NEF_BRIDGE_CONFIG` / `NEF_REGISTRY_CONFIG` / `NEF_SUBSCRIPTION_CONFIG` 优先于统一文件；换电脑不要照搬这些旧变量。仅在没有统一文件时，订购通知还会兼容读取 `config/subscription.local.json`。高级操作可用 `NEF_INTEGRATION_CONFIG` 指定统一文件位置。

### 3. 对方改字段时，改哪个文件

只改 IP、端口或路径时不改 Python。请求格式变化时按下表定位，改 Python 后需要重启并重新准备内存账号。

| 改动 | 文件 / 位置 |
|---|---|
| `subscriberId`、`servicePlan`、`networkCapabilities` 等通知字段 | `subscription_notifications.py`：`_notify_plan()`、`deliver()` |
| 双向开放 POST 到 TRF 的正文（含 isThirdParty=true） | `network_registry.py`：`_trf_publication()` |
| 首页本地能力 POST 到 TRF 的正文（isThirdParty=false） | `trf_catalog.py`：`_payloads()`；分类在 `skills.py`：`capability_tool_type()` |
| 首页单工具 MCP 路径和调用 | `server.py`：`capability_mcp_endpoint()` |
| TRF GET 回包解析、DELETE 与发布状态 | `network_registry.py`：`_validate_trf_servers()`、`_delete_trf_server()`、`change_trf_server_publication()` |
| 旧目录兼容导出正文（不用于新 TRF MCP 接口） | `catalog_publication.py` |
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
3. 自助编排中拖入或点击能力、拖拽调整顺序。交付方式、GPU 上限及目标来源收在“可选约束”中，默认不填。可选模型推荐经采用进入草稿，填写名称并确认保存；发布按钮将套餐放到本地首页，不发到 TRF MCP Server 接口，也不表示执行完成。
4. 首页下方可“同步到 TRF”“取消 TRF 注册”或“核对状态”，需配置 registry.trf_mcp_servers_url 与对方可访问的 registry.nef_base_url。TRF 目录预览在 `/?ops=1#market` 的“目录来源设置”中，将展示来源切为“TRF 目录”后点“刷新目录”；普通首页仍展示本地能力，不影响账号订阅。双向开放填写巡检小车 MCP 地址，连接并发现工具，再点击发布；首页可见后可取消发布。TRF 地址未配置时只更新本地状态并明确提示。
5. MCP 接口先连接 / 发现、再选工具；API 直调从已知能力开始。两者保留原版请求、参数、鉴权和响应两栏。
6. 实际接口配置后直接调用；场景数据源用无 Key POST/GET 回传地址。机器狗配置结果地址后，发送 Intent 自动拉取并每 3 秒检查最新结果。

## 四、接口和执行边界

- **认证与授权分开**：场景使用本地 AF Key + scope + 场景订阅；场景未开通返回 403。旧基础能力的等级 / 订阅 / 按次付费接口保留。Key 不等于标准 mTLS / OAuth 安全接入。
- **Intent 原文转发**：三个场景调用 `/api/v1/services/{service_id}/intent`；网络侧负责解析与执行。没有内部 Intent ID 也可回文字，不虚构 Planning Agent 轨迹。
- **API / MCP 并行**：已知能力走 HTTP API；AF 通过 `/mcp` 初始化、发现、选用和调用工具。两者可以映射同一内部 HTTP 服务，不要求网络内部都重写为 MCP。
- **套餐定义不是执行计划引擎**：NEF 保存有序能力引用并在本地发布；真实部署、参数绑定和失败处理仍需网络侧契约。
- **双向开放**：页面保留带 Key 分步登记；农场可通过无 Key `/api/v1/af/mcp-servers` 一步登记与发现，随后显式发布。默认仍检查 URL 允许列表，不自动授予网内调用权。
- **结果证据**：demo 明确标注；live 无配置返回 503、不回落；HTTP 受理不等于业务完成。场景级回传与某次调用不自动关联。

对接地址统一读取 `config/integration.local.json`，字段与旧配置兼容规则见第二节。智能推荐默认读取 `config/composer.local.json`（可由 `NEF_COMPOSER_CONFIG` 覆盖），模板为 `config/composer.example.json`；远程 Base URL `https://sub2api.2012wtlab.com/v1`、模型 `gpt-6-astra`、Responses 协议及 `low` 档位已填写。模型 Key 使用 `NEF_COMPOSER_API_KEY`，不读取 Codex 密钥、不依赖本机 CPA。每次请求内嵌可用原子能力池与参数 schema；Responses 通过 instructions 和显式 developer 消息传递同一份应用提示词，适配本次观察到的仅用顶层 instructions 时未遵守输出要求的问题，未确认远程网关的内部处理方式。推荐仍须校验、采用和确认后保存，不代表套餐已部署或执行业务。错误按超时、上游错误、连接失败和响应格式错误分类，并返回排查用 request_id，不暴露密钥或上游正文。当前验收和历史记录见[演示运行手册](docs/demo-playbook.md)。

跨应用读取订阅：`GET /api/v1/integration/subscriptions?account_id=1`，其中 `1` 是在 NEF 注册的账号名，不是自动编号。1.1 响应的 `purchased_packages` 直接提供已购场景/能力套餐及详情，适合农场平台展示“已购网络套餐”；新增 `external_tool_subscriptions` 提供第三方 MCP 工具订阅与 available 状态；原子工具、参数 schema、权益来源等旧字段仍保留，不返回 API Key。公网仍需 Access 机器凭据，接口详细契约见[订阅查询接口](docs/reference/subscription-query.md)。农场查询套餐、MCP 注册发现、发布网络和网络回调的步骤见[农场平台联调](docs/reference/farm-integration.md)。场景开通不要求组件逐一订阅，但组件单独调用仍校验各自权益；订阅数据仍为内存态，重启后需恢复。

订购主流程：农场按钮跳转 `/?account_id=1`，用户开通任一场景后由 NEF 向配置的 `/business/v1/service-plans` POST `subscriberId` + `servicePlan`。套餐内含 `planId/showName/description/price`；页面默认全选能力，至少保留一项；后端兼容显式空选择并省略 `networkCapabilities`，PA/CA 决策由网络侧实现。价格按折扣计算，未配折扣才用固定价；失败保留订阅，`?ops=1` 可查看请求/回包并重试。取消开通会删除本地权益并向农场发送 DELETE。现场地址来自另一台记录，本机未访问验证或重启加载。唯一契约见[套餐订购通知与订阅查询](docs/reference/subscription-query.md#10-跳转订购与套餐通知)，新部署使用统一配置模板 `config/integration.example.json`。

当前联调的外发 `subscriberId` 固定为 `subscriber-001`，定义在 `subscription_notifications.py` 的 `SUBSCRIBER_ID`，无需新增配置。跳转和查询仍使用本地账号 `1/2/3`；对方会将这些账号的通知都归入同一个测试订购者。

TRF 当前登记 MCP Server，NF 无需自行实现 MCP：首页本地能力通过 NEF `/mcp/capabilities/{id}` 单工具入口包装后显式注册。首页发布带 `isThirdParty: false`，双向开放发布带 `true`，使用同一注册结构；四类映射、批量处理、撤回与只读目录契约见 [TRF 参考](docs/reference/network-catalog.md#8-首页本地能力同步与-trf-读取模式)。场景/自助套餐不属于服务登记，旧目录导出和农场订购通知独立保留。

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
catalog_publication.py  旧目录兼容导出，不发到 TRF MCP 集合
trf_catalog.py          首页本地能力批量登记、撤回与 TRF 读取缓存
registry.py           旧第三方注册与调用台账（兼容）
intent.py / stubs.py   旧意图与参考执行（不作为当前真实结果）
scene_services.py     三场景契约与明确标注的演示文字
exhibition.py         真实转发与统一场景回传
network_registry.py   TRF MCP 登记/查询/撤回、发现与本地发布
static/index.html     活动原版工作台，保留原布局与交互
static/workbench.js    新接口接入及原交互的增量控制逻辑
static/workbench.css   原主题的少量新增组件样式
static/showcase.html   旧书签兼容跳转，不再独立展示
static/showcase-mcp.js / showcase-story.js  共用发现与回执语义
config/               内部执行、网络目录配置模板
```

所有业务状态保存在单进程内存。重启清除账号 Key、订阅、套餐定义、注册、目录及回传数据；浏览器通过 `/api/v1/instance` 在加载或 401 后识别重启并清除旧账号，需重新注册。

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
| `capability_register` | 能力注册 | 平台扩展 | 本项目 AF MCP 登记/发现/发布协议为平台扩展，不等同于 CAPIF API 发布实现或标准 TRF 接口。 |
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
