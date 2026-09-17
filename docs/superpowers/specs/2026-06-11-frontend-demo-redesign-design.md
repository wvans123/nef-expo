# NEF 展示体验与网络目录对接设计

分类：架构 / 设计决策。更新：2026-09-17。当前范围以本文为准，旧实施计划仅作历史记录。

## 1. 展示范围

活动入口 `/`（`static/index.html`），直接修改原版工作台，保留深蓝底、青色高亮、紫色渐变，以及原能力卡片详情、订阅、拖拽编排、API / MCP 两栏调试和逐级鉴权。增量逻辑在 `static/workbench.js`，少量组件样式在 `static/workbench.css`。旧 `/static/showcase.html` 仅跳转至活动工作台。

七个可见原版页签：能力超市、订阅与鉴权、API 直调、MCP 接口、意图受理、自助编排、双向开放 · MCP。

- 超市同时保留基础能力与场景套餐；三个内置套餐为机器狗巡检、车流量检测、端网协同识别追踪。
- 三个场景默认 Intent；协同追踪仍兼容 API / Tool。API 面向已知接口，AF 的 MCP 路径保持先发现、再选工具、再调用，不预选场景。
- 自助编排说明套餐的来源，双向开放展示外部 MCP 能力源的登记与工具发现。
- 对外 Skill / 场景方案、AF 智能终端不在本期活动导航中。对应按钮隐藏，原功能代码与旧接口保留兼容；hash 不能打开隐藏页签。
- 文字是主结果；图像 / 视频可展开。场景回传仅在具体调用页出现，不能铺在目录、编排、注册页。

## 2. NEF、网络与外部服务的职责

NEF 承担目录汇聚、接入授权、能力和场景开放、套餐定义与协议适配；网络侧承接目标解析和实际执行。MCP Server 登记不会自动赋予调用权，也不会把注册地址当作可信地址直接连接。

自助编排采用**声明式套餐**：操作员选择能力引用、排列顺序，NEF 保存定义并交付网络侧。当前不自动生成参数映射、不把前一步输出注入后一步，也不将声明式步骤伪装成自主规划。可选 LLM 在 NEF 侧推荐能力组合，经确定性校验后由用户采用草稿并确认保存；这不改变业务 Intent 原文转发路径。执行仍由内部 NW Agent / 执行平台承接。

目前套餐发布是目录交付，不等于可执行部署。网络需提供执行标识、输入参数、依赖及失败处理契约后，才能把新套餐加入真实调用映射。内置三场景有独立已实现的开放接口，因此可订阅并演示 / 转发；导入目录项先展示声明，不直接借用某个场景执行。

主页场景卡收敛为普通套餐卡，去掉 Intent 标签。`scene_services.py` 的 `provenance.components` 使用 `{capability_id, role}` 引用 `skills.py` 中实际能力；页面显示基础能力名称并复用详情弹窗。它是 NEF 与场景服务方的产品组合设计，并非自动检测到的网络部署。机器狗控制、摄像头输入和具体识别算法仍由场景服务方提供，列出基础能力不意味着网络能力独自完成全部业务。网络导入和自建套餐保留各自来源。

### 2.1 编排检查与智能推荐

`composition.py` 是组合规则与模型提示词的唯一实现。手动保存和 LLM 方案共享检查：

模型配置默认读取 `config/composer.local.json`，可由 `NEF_COMPOSER_CONFIG` 覆盖。配置接受 `base_url` 或旧 `endpoint`，不能同时设置；`wire_api=responses` 补上 `/responses`，省略或为 `chat` 时兼容旧 `/chat/completions`。远程服务、模型及协议沿用既有配置，本项目推理档位已设为 `low`；不读取 Codex 凭据，实际 Key 由使用者设置到 NEF 环境变量。Responses 只解析 completed 的 assistant output_text。三个约束默认未指定并折叠，空值不进入请求；只有选择后才应用对应检查。运行说明见[运行手册](../../demo-playbook.md#智能编排准备与现场操作)。

- 实时交付不能搭配 `sensing_fusion.params.fusion_mode=batch`。
- `compute_qos.params.gpu_share_pct` 必须为 1–100，且不能超过套餐的 `context.gpu_budget_pct`。
- 选择 `context.target_source=detection` 时，`target_detection` 必须在 `target_tracking` 之前；外部提供目标时不强制检测。
- 规划中能力、未知 ID、重复 ID、非法参数均拒绝。缺少现有任务或目标标识给出调用前提示；未填写必填调用参数可以作为声明保存，不等于可以直接执行。外部工具约束未完整建模，提示需提供方确认。

以上为**本原型产品配置策略**，不是 3GPP 定义的能力互斥关系；不宣称穷尽无线资源、拓扑、并发、授权或实际运行冲突。

接口均要求 `pipeline:manage`：

| 接口 | 行为 |
|---|---|
| `GET /api/v1/composer/status` | 返回 `configured/code/message/connectivity`，区分缺文件、配置无效、进程缺 Key；`connectivity=not_checked`，不探测可达性，不泄露地址或密钥 |
| `POST /api/v1/composer/validate` | 接收 `steps` 和 `context`，返回 `valid/errors/warnings` |
| `POST /api/v1/composer/recommend` | 接收 `text/context`，真实请求模型并校验，返回 `proposal` 与 `requires_confirmation:true` |
| `POST /api/v1/network/packages` | 显式确认保存；再次校验，保留 `steps[].params` 与 `context` |

模型只看当前本地可用原子能力目录，不接收其他账号私有工具、用户密钥或回传数据。每次请求内嵌目录快照，包含 ID、名称、描述、分类、来源、状态、标准依据与完整参数 schema。`catalog_source` 给出来源路径但不赋予模型检索权限；网络导入与 AF 私有工具不自动进入推荐池。System prompt 在 `composition.py::SYSTEM_PROMPT` 中要求根据业务目标选择最小够用的能力、说明分工和缺失输入，并明确限定合法 ID、JSON 格式、冲突规则以及“推荐不是执行”。响应必须是 JSON 对象，不兼容 Markdown 包裹输出；无匹配、错误、超时或结构不合规直接报错，不以规则结果冒充 LLM。

先点“生成推荐方案”，再点“采用方案，替换当前草稿”，最后“确认并保存套餐”。采用前显示能力列表与可展开参数配置；用户可继续编辑。推荐/采用均不保存、不发布、不调用业务。账号切换、需求或约束变化后旧推荐不能套用。

模型接入支持 Responses 和旧 Chat Completions 报文，地址和模型从运维本地配置读取，API Key 仅由进程环境变量载入；启动时可按运行手册显式继承同名 Windows 用户变量，不增加客户投屏页面的密钥输入框。禁止浏览器传模型地址、禁止跟随重定向或环境代理，非本机地址要求 HTTPS。单次 30 秒 HTTP 超时、35 秒总预算、256 KiB 回包上限，每账号仅一个并发推荐、全局最多四个；错误不回显上游响应或密钥。运维需要信任配置中的模型提供方，用户填写的需求与内嵌能力池会发送给该提供方。

推荐异常按超时、上游 HTTP、连接和无效响应分类；成功及失败均带 request_id，日志只保留编号、耗时和状态。新代码需协调重启加载，不能用新分类猜测旧进程此前返回 502 的原因。

客户主界面仅展示业务描述、基础能力组合、使用状态、冲突与建议；标准审计、未实现的授权机制和内部联调边界放在文档。必要的“演示 / 真实调用”“未配置 / 失败 / 待确认”状态不删除。

## 3. TRF / ARF 目录与发布边界

`network_registry.py` 是适配层。本项目不预设 TRF / ARF 的正式协议和责任划分；下面是待与同事映射的最小本地契约。

- 前端进入目录页、以及停留能力超市 / 双向开放时每 30 秒自动拉取；移除目录同步按钮。这是页面驱动的同步，不是无人值守后台调度。
- `GET /api/v1/network/catalog`：读取当前账号导入的目录快照与状态。
- `POST /api/v1/network/catalog/refresh`：向运维配置的目录 URL 请求 `{items:[...]}`，验证后整体替换，不将无效响应混入旧目录。
- 目录项至少包含 `id`、`name`、`kind`（`tool` 或 `package`），可附 `description`、参数声明等元数据。
- MCP 注册与套餐声明通过各自 `/sync` 操作发布。只有对方明确返回 `{"accepted":true}` 才标记已同步；仅 HTTP 2xx 记为已提交、待确认。
- 本地原子能力/场景可通过 `/api/v1/network/catalog/publication` 预览、`/publish` 发布，只发送明确选择的项。契约见[网络目录发布](../../reference/network-catalog.md)，不宣称它是 NRF NFRegister；真实接收方仍待确认。
- 无配置 / 无网络连接不产生演示目录、不伪造同步成功。账号之间的登记、套餐、目录快照隔离；服务重启清空。

配置入口 `NEF_REGISTRY_CONFIG` 指向运维 JSON，示例 `config/registry.example.json`。`catalog_url` 为目录拉取地址；`publish_url` 为统一发布地址；`token_env` 指向内部凭证环境变量。伙伴实际字段不同，修改适配层，不要求对方照搬界面模型。

## 4. MCP Server JSON 注册与工具发现

注册 `POST /api/v1/network/servers`：

```json
{"name":"园区视觉服务","url":"https://partner.example.invalid/mcp","description":"巡检分析"}
```

无需逐项填写工具参数。注册时仅保存信息，`POST /servers/{id}/discover` 才对运维批准的 URL 发起 `initialize → notifications/initialized → tools/list`，分页汇聚真实名称、描述与 inputSchema。前缀均为 `/api/v1/network`。

服务地址需在配置 `mcp_servers` 精确允许列表中；认证凭证通过服务端 `token_env` 加载，不从 AF Key 转发，不放注册 JSON。禁止跟随重定向，不使用环境代理，限制响应体和超时。发现结果以实际响应为准；不支持的协议或畸形响应报错。支持本期 HTTP MCP 交互，不承诺旧版 SSE 独立双端点或任意 MCP 扩展。

`POST /servers/{id}/sync` 可先发布服务登记，也可在发现后发布工具信息；发现中不允许发布。后端从认证账号写入 `source: "AF"`、`source_account`、`registration_status: "registered"`，不接受调用方伪造来源。发布报文和能力超市均保留 AF 来源、登记 / 发现 / 同步状态，尚未发现时只显示能力源，不声称已有可用工具。注册服务供网络内部目录发现，不挂到外部 AF 使用的北向 `/mcp` 中。内部网元使用独立的 NEF 代理 MCP 入口，接入与调用规则如下。

### 4.1 网络目录登记什么

ARF / TRF 是网络内部网元，已有网络内部工具信息。NEF 一方面导入其目录到能力超市，另一方面把 AF 提供的工具作为“经 NEF 访问”的外部供给发布进去。目录记录能力在哪里、怎样访问；本项目不把 ARF / TRF 实现成执行代理。

`GET /api/v1/network/servers/{id}/publication` 让注册者预览真实发布内容，不发送网络请求；`/sync` 发送同一格式。发布带稳定的进程内 `registration_id`（内部目录可据此做幂等更新）、AF 来源账号，以及：

```json
{
  "type": "mcp_server_registration",
  "registration_id": "srv_example",
  "source": "AF",
  "source_account": "园区AF",
  "server": {
    "id": "srv_example",
    "name": "园区视觉服务",
    "url": "http://NEF_HOST:8069/api/v1/network/af-servers/srv_example/mcp",
    "transport": "streamable-http",
    "access_via": "NEF",
    "protocol_version": "2025-03-26",
    "authentication": "network-client-bearer",
    "tools": [{"name":"inspect_frame","description":"检查图像","inputSchema":{"type":"object","properties":{"frame":{"type":"string"}},"required":["frame"]}}]
  }
}
```

上面为关键字段节选，完整报文还保留登记状态、NEF `serverInfo`，以及从 AF 握手实读的 `origin_server_info`（来源服务器名称 / 版本）。AF 的工具声明按实际 `tools/list` 保存，包括参数 schema、annotations 等元数据。**`server.url` 指向 NEF，而不是 AF；AF 原始 URL 和上游凭证只供 NEF 服务端连接使用，不出现在发布报文中。** 对方可以按 server 保存 tools 列表，也可以拆成每工具条目，但每项都应保留 AF 来源、registration_id、NEF endpoint 和 tool name。真实 ARF / TRF 接口字段及其持久化 / 更新机制仍由同事提供并映射；`accepted:true` 仅证明接口确认接收，不证明已核验内部数据库持久化。

### 4.2 网络内部怎样调用

`内部网元 / NW Agent → NEF 代理 MCP → AF MCP Server`。

- 每个注册服务对应 `POST /api/v1/network/af-servers/{id}/mcp`，支持 `initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`。NEF 代理侧为无状态请求；向 AF 侧每次调用重新握手，透传 AF 分配的会话 ID，随后真实发送工具调用，不自动重试。
- 内部调用者使用 `network_clients` 配置的独立 Bearer 凭证与 `af_accounts` 授权范围，不借用 AF 注册账号 Key，不默认允许所有网络调用者访问所有 AF。每次调用重新核对配置、账号范围、AF URL 精确允许列表和已发现状态。
- NEF 校验名称必须存在于实际发现目录，参数需满足该工具的 JSON Schema。校验不解析外部引用；含远程 `$ref` / `$dynamicRef` 或 `$id` 的 schema 暂拒绝执行，不让声明触发任意外联。当前按 Draft 2020-12 校验，不承诺任意 schema dialect。
- AF `CallToolResult` 原样返回，`isError:true` 保持工具错误。网络故障只报告未获得可确认回执，不能推断没有执行，也不自动重试。最近一次调用仅记录调用者、工具、状态、实际耗时，不保存业务参数、内容或密钥。
- 没有凭证 / 不在授权账号范围 / 允许列表被撤销 / 未发现 / 不合法参数均在转发前拒绝。单个 AF 服务同一时刻只处理一个代理工具调用；重复并发返回 busy。单次外部 HTTP 总超时 10 秒，工具握手加调用总超时 30 秒；单请求 / 响应 1 MiB。仅支持可在期限内结束的 JSON / SSE 响应，不承诺长连接事件流。

### 4.3 运维配置

`config/registry.example.json` 默认禁用外联。复制为本机配置并填写以下字段；实际密钥在环境变量中单独设置，不写 JSON、文档或页面。

```json
{
  "catalog_url": "http://NETWORK_DIRECTORY/catalog",
  "publish_url": "http://NETWORK_DIRECTORY/registrations",
  "token_env": "NEF_DIRECTORY_TOKEN",
  "nef_base_url": "http://NEF_HOST:8069",
  "mcp_servers": {
    "http://AF_HOST/mcp": {"token_env":"NEF_AF_TOKEN"}
  },
  "network_clients": {
    "nw-agent": {"token_env":"NEF_NW_AGENT_TOKEN","af_accounts":["园区AF"]}
  }
}
```

`nef_base_url` 必须是网络网元可访问的 NEF 地址，发布时不可根据入站 Host 头猜测；未配置则拒绝发布 AF 访问入口。`NEF_DIRECTORY_TOKEN` 用于 NEF 向内部目录发布 / 拉取；`NEF_AF_TOKEN` 用于 NEF 访问 AF；`NEF_NW_AGENT_TOKEN` 用于内部网元访问 NEF。配置了凭证变量但未设置实际值时不得降级为匿名上游请求。所有地址由运维指定；不设置真实接口时不伪造联调成功。演示账户可自助注册，因此本原型仅用于获准测试网络；这些控制不等于生产级 mTLS / OAuth 与租户管理。

## 5. 套餐构建接口

`GET /api/v1/network/packages` 列出当前账号的定义。

`POST /api/v1/network/packages` 保存：

```json
{"name":"园区协同巡检","description":"组合感知与分析","steps":[{"capability_id":"target_detection"}],"execution_target":"network"}
```

步骤只能引用已知可用基础能力、导入工具或本账号发现的服务工具；外部工具引用形式为 `serverId:toolName`。支持顺序调整，限制 1–12 个不重复步骤。保存不执行，`POST /packages/{id}/sync` 交付网络目录。

## 6. 场景 Intent、结果与鉴权

农场订购交接独立于执行：跳转 `/?account_id=1`，用户开通后发送 `subscriberId` + `servicePlan` 到运维配置的 `/business/v1/service-plans`。可选 `networkCapabilities` 来自本次明确勾选，不选则省略；PA/CA 在范围内编排或 PA 自主编排均归网络侧，NEF 不实现规划器。通知失败不撤销本地权益，手动重试保留事件 ID 与正文；价格不能默认零元。唯一契约见[套餐订购通知与订阅查询](../../reference/subscription-query.md)。

`scene_services.py` 维护三个场景契约。`POST /api/v1/services/{service_id}/intent` 先校验 AF、`intent:submit` 和场景订阅，再转发原文。

内部执行映射由 `NEF_BRIDGE_CONFIG` 配置，示例 `config/bridge.example.json`。`$text` 保留原文，`$arguments` 支持 API / Tool 参数。外部 API 与 MCP Tool 可以映射同一个内部 HTTP 接口，不要求内部也使用 MCP。

场景默认 demo，并明确标记示例文字与插画；live 缺配置返回 503，不回退。前端主结果读取上游 text / result.text / summary 等实际文字；只有受理回执时不自动显示任务完成。独立回传按场景 Key 归属，不能把无 request_id 的任意状态自动认定为本次 Intent 完成。

鉴权动画仅展示后端实际校验结果；等待时只提示正在核验，不编造时延、Agent 思考过程、资源授权或执行进度。安全细节见同目录鉴权设计。对接同事只需阅读简短的 `docs/reference/integration.md`，不承担内部通道和配置结构。

### 自动提供场景回传接口

前端进入真实调用时使用账号凭证请求 `POST /api/v1/services/{service_id}/feedback-access`；基础能力使用保留值 `general`。服务端幂等准备、并在本次进程中复用同账号同场景的回传接入信息，不要求演示者创建或选择调用点。此管理接口返回内部读取定位和专用写 Key，使用 `Cache-Control: no-store`；只有“接口信息”详情可查看 Key。对接同事仍只收到统一 `POST /api/v1/scene-feedback` 地址与 Key。普通列表不返回 Key，Key 无账号读取权。所有状态内存保存，重启后重新获取。按场景顺序展示回传，但不自动把未关联结果认定为本次请求完成。

## 7. 验证范围

Python 覆盖场景订阅、三场景 Intent、API / MCP、真实 HTTP 转发、回传隔离、目录 / 注册 / 发布失败路径。Node 覆盖工具发现客户端、访问回执与文字结果语义。浏览器验证原版七页签、编排、注册与发现、订阅后的 Intent 结果，以及回传仅在调用界面出现。

本地受控服务验证可以证明序列化与网络请求链路，不能替代真实 TRF / ARF、场景服务和网络侧执行环境联调。

2026-09-10 补充验收：`tests/test_network_gateway.py` 在真实本地 TCP 链路上验证目录发布 → 从发布 endpoint 连接 NEF → tools/list → tools/call → AF 结果返回，并覆盖 AF / 网络凭证分离、授权撤销、schema 拒绝、isError 保留、发布内容无 AF 原始 URL。它不替代伙伴真实网络联调。
