# 6G NEF 演示运行手册

分类：运行手册。更新：2026-09-17。当前展示范围以本节为准，后面的旧工作台流程仅供历史核对。

换电脑部署的唯一操作入口见 [README 第二节](../README.md#二换电脑启动与配置)：`python -m pip install -r requirements.txt` 后执行 `python start.py`，地址集中在 `config/integration.local.json`。下文带日期、PID、测试数量的内容为当时检查记录，不代表上传后重启或另一台电脑的状态。

## 本期展示动线

入口：`/`。直接在原版工作台上增量修改；`/static/showcase.html` 旧书签自动跳转。保留原能力卡片、弹窗、拖拽编排、参数表单与鉴权步骤，不使用另一套重做的展示页。

1. **能力超市**：场景套餐与基础能力并列供给；场景为普通目录卡，卡内显示基础能力组合，点击复用能力详情弹窗，不以 Intent 标签宣传。TRF / ARF 目录由页面自动同步，状态条只显示状态；下方展示网络导入、自建套餐及 AF 注册能力源 / 工具。
2. **套餐从哪里来**：进入原自助编排，拖入或点击能力、拖拽排序、命名并保存，再同步网络目录。展示 NEF 的配置检查与可选智能推荐；方案需要确认，保存不是部署完成。
3. **外部能力怎样进入网络**：进入双向开放，提交 MCP Server JSON，连接并发现工具，展开其参数声明，然后同步 TRF / ARF。NEF 展示 AF 来源账号、已登记、工具发现和网络同步状态；能力超市同步显示 AF 标记。可先发布服务登记，发现工具后再次发布。登记、实际发现、发布确认是不同动作。展开“查看网络登记内容”，指出对网络发布的是 AF 工具与 NEF 代理入口，而不是 AF 原始地址。内部网元从目录获得信息后，经 NEF 调用 AF；服务卡展示最近调用的真实状态。真实演示前需配置获准服务地址。
4. **订阅与鉴权**：接入演示账号，按场景开通。订阅赋予使用权，调用时再次核验，不产生真实费用。
5. **Intent 主流程**：三个场景都可从套餐进入 Intent，也可选择“不指定场景”。填写业务目标后直接真实转发，未配置则待对接；不指定场景只检查账号与 Intent scope，场景入口仍检查场景订阅。端网协同保留 API / Tool。
6. **MCP 北向接口**：仍从“连接 NEF 并发现工具 → 选择工具 → tools/call”开始。它是 AF 发现 NEF 的工具，不能与双向开放中“NEF 发现外部 MCP Server”的方向混淆。
7. **真实联调**：页面不再提供执行方式或示例意图，NEF 原文转发至内部接口，呈现对方实际文字；车流量回传兼容 `final_result`。没有内部任务 ID 也可回传，但不能把未关联的场景反馈认定为某次 Intent 完成。

本期隐藏对外 Skill / 场景方案、AF 智能终端。场景回传只在具体调用页出现；不在超市、编排、注册或发现目录阶段占用空间。

## 智能编排准备与现场操作

1. 手动演示不需要模型，三个约束默认未指定并折叠，不妨碍推荐或保存。要演示检查规则时展开“可选约束”：交付选实时反馈，加入多源感知融合并设置批处理模式，观察冲突；改回实时后恢复。GPU 上限 40 与算力服务保障 50% 可演示资源冲突；“由本套餐检测”可演示检测先于追踪。
2. 智能推荐沿用 2026-09-17 核对的远程 Base URL `https://sub2api.2012wtlab.com/v1`、模型 `gpt-6-astra` 和 `responses` 协议；本项目推理档位现设为 `low`，不再照搬 Codex 的 `high`。本机配置 `config/composer.local.json` 被 Git 忽略，默认自动读取；新环境使用 `config/composer.example.json`。请求发往 `/responses`，不依赖本机 CPA。保留 `api_key_env: NEF_COMPOSER_API_KEY`，由使用者设置到启动进程环境；不复制 Codex Key，不混用 NEF 账号 Key 或回传 Key。配置不会每次请求读取 Codex config，远程服务变动需同步项目配置。

```json
{
  "base_url": "https://sub2api.2012wtlab.com/v1",
  "model": "gpt-6-astra",
  "wire_api": "responses",
  "reasoning_effort": "low",
  "api_key_env": "NEF_COMPOSER_API_KEY"
}
```

模型与地址已经填写，使用者只需设置有效 Key。可通过 `NEF_COMPOSER_CONFIG` 指定另一个配置文件；旧 `endpoint` 完整 URL 仍兼容，但不能与 `base_url` 同时配置。`wire_api=responses` 使用 `/responses`；省略 `wire_api` 或设置为 `chat` 保持旧 `/chat/completions` 兼容。Responses 使用最终 assistant 文本解析推荐，不把 reasoning、拒绝或未完成输出作为方案。请求设置 `store=false`，但不据此承诺第三方网关不保留日志。2026-09-17 已加载使用者配置的 Key 并完成一次真实模型推荐；超时或格式异常仍明确失败，不回退其他模型。

2026-09-17 早先提示词修复阶段完成 80 项定向测试及 4 组前端测试，并在正式服务用 `high` 档位完成一次真实推荐：HTTP 200、约 23.69 秒、`source=llm`、`validation.valid=true`，仅生成草稿，没有订购、发布或执行业务。后续一次现场 502 的旧日志未记录足够细分原因，不能断言是超时。现已把配置降为 `low`；该档位通过本地合成对端请求验证，尚未再调用真实模型。

新代码为每次推荐生成 `compose_*` request_id，分别返回 504 `model_timeout`、502 `model_upstream_error`、502 `model_connection_error`、502 `model_invalid_response`。安全日志只记录编号、分类、耗时及上游 HTTP 状态，不记录需求、Key 或上游正文；这些新诊断需重启加载后生效，不能倒推旧 502 原因。

```powershell
$env:NEF_COMPOSER_CONFIG = (Resolve-Path .\config\composer.local.json).Path # 可省略，默认读取此文件
$previousKey = $env:NEF_COMPOSER_API_KEY
if ([string]::IsNullOrWhiteSpace($env:NEF_COMPOSER_API_KEY)) {
    $env:NEF_COMPOSER_API_KEY = [Environment]::GetEnvironmentVariable('NEF_COMPOSER_API_KEY', 'User')
}
if ([string]::IsNullOrWhiteSpace($env:NEF_COMPOSER_API_KEY)) {
    $secret = Read-Host '模型 API Key' -AsSecureString
    $credential = [System.Net.NetworkCredential]::new('', $secret)
    $env:NEF_COMPOSER_API_KEY = $credential.Password
    $secret.Dispose()
    Remove-Variable secret, credential
}
try {
    python -m uvicorn server:app --host 127.0.0.1 --port 8069
} finally {
    $env:NEF_COMPOSER_API_KEY = $previousKey
    Remove-Variable previousKey
}
```

在启动服务的同一 PowerShell 会话设置环境变量；先按下文核对并停止本项目旧进程，不在已占用端口重复启动。模型配置不会修改现有 AF 调用 Key。模型端点为运维信任边界，请确认允许将客户填写的需求传给该服务。不要把 Key 发到聊天、放到 localStorage、注册 JSON、截图或 Git。

只修改 JSON 中的模型或地址，下一次请求即可读取；在另一个终端设置 Key 不会改变已运行 NEF 的环境，需在已安排的重启中重新启动 NEF。重启会清除账号和订阅，先协调联调窗口。启动及状态检查不自动调用真实模型，不替用户选择模型或读取 Codex 秘密配置。

2026-09-17 排查“未就绪”：Windows 用户环境已存在 `NEF_COMPOSER_API_KEY`，但此前 NEF 启动进程未继承它。仅设置用户环境变量不会更新旧终端或正在运行的服务。上面启动命令优先保留进程变量，缺失时显式读取同名用户变量，不修改持久环境值，不读取 Codex 凭据。

3. 页面“模型已配置”只代表配置校验通过，不代表远程连接已验证。`GET /api/v1/composer/status` 返回 `configured`、`code`、`message` 和 `connectivity=not_checked`，不发起模型请求。缺文件为 `composer_config_missing`，无效配置为 `composer_config_invalid`，进程未加载 Key 为 `composer_key_missing`；推荐接口以 HTTP 503 和相同 `detail.code/message` 返回配置失败。状态及错误均不暴露地址、路径或 Key。填写需求 → 生成推荐 → 查看能力和参数 → 采用方案 → 确认保存。只有真实模型响应经过校验才展示“智能推荐”；状态查询失败单独显示，不误报为模型未配置。测试使用本地合成 HTTP 对端，不等于客户模型或生产网络已联调。
4. 发布套餐仍是独立操作；下游参数映射、数据绑定、执行接口未对齐前不能宣称新套餐可以运行。场景卡的组成是产品设计，场景提供方需确认机器人控制、输入数据和算法的实际供给。

### 套餐设计提示词与能力池

唯一提示词在 `composition.py::SYSTEM_PROMPT`。每次推荐从 `skills.py::CAP_INDEX` 重新构建 `status=available` 的原子能力快照，与用户需求和约束一同发送给所配远程模型。每项包含 ID、名称、描述、分类、来源、状态、标准依据、参数 schema（含类型、必填项、枚举和默认值）；不发送账号密钥、私有 AF 工具、现场回传数据或订阅清单。

模型被要求先识别业务目标，再选最小够用的能力、按依赖排序，在套餐说明中解释分工与缺失输入。不能编造设备、数据源、能力、资源预留或实际运行结果；核心能力缺失时返回 unavailable，不把相似工具当成已具备的业务服务。推荐仍为有待确认的草稿。

请求中的 `catalog_source` 标记目录来源 `/api/v1/capabilities` 与详情路径 `/api/v1/capabilities/{capability_id}`，但 `lookup_enabled=false`：能力池已内嵌提供，当前模型没有主动 HTTP/MCP 检索权限。目录文件变动需要运行进程重新加载后才可见；每次请求重建不意味着自动热加载 Python 文件。规划中能力、网络导入项和农场私有 MCP 不自动纳入本轮推荐池，避免未知 schema 或跨账号工具泄露。

示例需求：`根据已有能力池，为农场设计周界异常检测与持续追踪套餐；说明每项能力的作用，以及还需农场提供的区域、目标或数据源信息。不要假设灌溉控制和农业专用模型已接入。` 配合“由本套餐检测”约束后，检查检测先于追踪；不能把草稿当成真实农场执行成功。

### 编排约束字段

| 页面字段 | 含义与当前检查 | 不代表什么 |
|---|---|---|
| 结果交付 | 实时反馈或批量分析；选实时后，拒绝组合中使用批处理模式的多源感知融合 | 不配置回传 URL，不保证实时流、时延或交付时限 |
| 追踪目标来源 | 调用时提供目标 ID，或本套餐先检测再追踪；后者要求检测步骤在追踪之前 | 不自动把检测输出绑定到追踪输入，实际参数映射仍待网络执行方实现 |
| GPU 资源上限 | 百分比预算，1–100；如设为 40，算力服务保障请求 50% 会判冲突 | 不是 GPU 卡数、显存 GB，也不真实预留或限制 GPU；百分比的资源基准须与执行方约定 |

这些是可选的套餐草稿校验条件，默认不发送，未选择时不应用对应的场景约束。它们不是 NEF 已接管业务执行或集群调度，也不作为农场订购回调的必填字段。

## 订阅查询联调

主流程为农场页面跳转 `http://<NEF电脑IP>:8069/?account_id=1` → 用户订购 → NEF POST `subscriberId` + `servicePlan` 到农场 `/business/v1/service-plans`。默认勾选套餐全部能力并发送 `servicePlan.networkCapabilities`；全部取消才省略，PA 自主编排由网络侧实现。旧 Tunnel 部署仍可用原域名。字段、配置和重试唯一维护于[套餐订购通知与订阅查询](reference/subscription-query.md#10-跳转订购与套餐通知)。

当前联调的 POST `subscriberId` 固定为 `subscriber-001`，不随本地账号改变，不需要配置新变量。补偿查询接口仍为 `GET /api/v1/integration/subscriptions?account_id=1`，使用本地账号编号。对方不需要 NEF 账号 Key，公网继续带原有 Access 机器凭据；公网跳转浏览器必须先能通过现有 Access 登录，不能把机器 Secret 放到链接中。

农场平台优先读取 1.1 的 `purchased_packages`，一次获得已购场景套餐 / 旧能力套餐的名称、说明、组成能力、支持的入口和意图示例；未购目录和编排草稿不作为已购返回。完整双向流程见[农场平台联调](reference/farm-integration.md)。查询账号编号与注册 MCP 的鉴权分开，不能用数字编号替代 MCP 登记或网内调用凭据。

在 NEF 页面注册账号名 `1`、`2`、`3` 并订阅，对方传相同字符串查询。不是按注册顺序分配编号，不创建隐藏映射。订阅仍保存在进程内存；查询不替用户注册或恢复订阅。场景入口只需场景权益，组件独立调用仍需各自权益；同名旧套餐与新场景不可混淆。

2026-09-17 前一阶段验证：244 项 Python 测试和 5 组 Node 脚本通过，保留 3 条依赖弃用警告。包括当时的订购通知、subscriberId、所选能力、空选择、价格、重试、查询和回传；对端均为本地模拟服务。此前浏览器检查使用独立临时 NEF，未操作 8069 账号。这是当时版本的记录，不作为后续改动的全量验证。

**运行状态（2026-09-17）：保留正在联调的 PID `7896`，本轮未再次重启。** 监听 `127.0.0.1:8069`，没有自动重载；PID 文件 `.runtime/nef.pid`，日志 `.runtime/nef-20260917-composer.stdout.log` / `.stderr.log`。只读检查首页 200、查询 1.1 可用，账号 `1` 已开通 `robot_patrol`，`2` / `3` 为空。这些是当前用户测试数据，不清空或代为恢复。静态页面与模型 JSON 会读取磁盘更新；订购通知、目录选择发布、回传游标和编排新错误分类等 Python 变更仍在磁盘，运行进程未加载。

**下一次加载前：** 等同事提供回调完整地址、鉴权和成功响应，双方确认套餐价格，填写 `config/integration.local.json` 的 `subscriptions`。与操作者约定重启窗口及内存账号/订阅重新准备方式后再加载；不能为了部署通知而打断当前查询联调。新代码没有收到真实同事 HTTP 接收回执，更没有验证 PA/CA 已执行约束。

本次没有停止或修改 Tunnel；重启后 `/ready` 返回 200。此前公网查询与 MCP 登记列表路径无 Access 凭据均返回 302 到既有登录页。有效机器凭据的公网查询、真实农场 MCP 发现和真实网络目录接收尚待验收，不能用本机测试代替。远程模型已通过上文单次真实推荐，不将其等同于真实农场执行或公网 Access 联调完成。

### 农场双向联调预演

```powershell
python -m pytest tests/test_farm_integration.py -q -s -p no:cacheprovider
```

测试在独立进程中使用临时端口运行 NEF、模拟农场 MCP 和模拟目录，实际通过 TCP 验证“场景开通 → 已购套餐详情查询 → 农场注册 → MCP 发现 → 目录 accepted → 网络经 NEF 调用只读 get_field_status → 返回带 mock 标记的结果”，并检查跨账号隔离、参数校验、各方向凭据分离。结束后停止全部测试服务；不触碰 8069 账号状态，不调用真实农场、不向生产目录发布。相关查询与网络代理定向测试共 29 项通过；真实现场联调按[农场平台联调](reference/farm-integration.md)逐项替换地址和单独提供的凭据。

## 五分钟讲解主线

**供给，约 1 分钟。** 能力超市展示从基础工具到场景套餐的供给层次；TRF / ARF 是待对齐的网络目录，不能把本地样例称为已联网目录。

**生成与开放，约 1 分钟。** 用自助编排保存一个套餐定义，再展示外部 MCP Server JSON 注册和真实工具发现。向网络交付的是可读的能力 / 套餐声明，网络侧执行机制独立对接。

**业务，约 2 分钟。** 开通机器狗巡检，提交一条 Intent，观察实际鉴权回执和文字报告；再切换车流或端网协同，说明入口统一但目标与服务不同。演示模式必须保留示例标记，真实模式必须有实际接口。

**协议与反馈，约 1 分钟。** 按需补充 MCP 发现优先和 API 已知接口的区别。调用页自动准备场景接口，打开“接口信息”即可交付地址和 Key，不创建或选择调用点。场景同事只拿一个回传地址和 Key，既能回文字，也能回图像 / 视频。服务重启后需要重新获取 Key。

## 关键追问与讲解口径

### 这不就是给 API 网关换个界面？

入口转发是基础，不是全部卖点。本原型把**开放对象**由细粒度接口扩展到可独立订阅的场景服务，把**使用方式**扩展为 API、可发现 Tool 和业务 Intent，把**反馈内容**扩展为独立接入的场景状态与多模态结果。现场分别用服务目录、订阅校验、真实 tools/list、调用页回传展示证据。没有实测成本、时延数据时，不报效率提升百分比。

### 哪些是面向 6G 的变化，哪些现在就能实现？

“面向 6G”说的是以连接、感知、计算和智能能力支撑场景服务的开放方案探索；不是为每项技术贴上 6G 独占标签。API、MCP、订阅和鉴权都能在现有软件系统实现。当前能证明统一开放原型与演示闭环，不能证明已部署 6G 网络、已完成标准符合性认证或全部场景都来自基站感知。场景画面的来源必须由对接方确认，不能把摄像头检测自动称为无线通感。

### API 与 Tool 最后都是 HTTP，区别在哪里？

外部 API 客户端按预先约定的接口和参数调用；MCP Client 先读取工具名称、描述和 inputSchema，再使用 tools/call。NEF 对外发布工具，内部把工具调用映射到已约定的执行接口，后台无需也讲 MCP。并非一般 API 永远不能发现，而是本次对比的两条实际接入流程不同。展示时从独立 MCP 入口开始，不能预选场景后“发现”一个早已确定的工具。

### Intent 谁理解？NEF 自己是不是大模型？

当前 NEF 做身份 / 场景权益核验和意图原文转发；不解析成执行工具计划。自助编排页可选模型推荐套餐，但与业务 Intent 受理是两条独立路径，不会自动执行。内部接收方可按后续约定为场景服务或统一 NW Agent，目前不定死。场景入口明确选定服务，所以能先做相应订阅校验；不是一个已经实现任意目标识别的全能 Intent 入口。

### 为什么不是直接连 NW Agent？

业务执行仍可归 NW Agent / 场景服务。NEF 作为本方案的统一开放边界，集中承接对外目录、入口契约、AF 身份与服务权益、内部路由适配，减少把内部地址和不同接入方式直接交给各个 AF。这里是部署 / 产品职责取舍，不声称 NW Agent 技术上不能实现这些功能。

### 买了巡检服务，就能控制任何机器狗吗？

不能。场景订阅只证明 AF 获得这项服务的使用权，不自动授予任意区域、设备和数据的访问权。平台暴露的是经运营商 / 服务提供方约定的场景契约；设备所有权、区域限制、用户授权等还要由相应资源方 / 执行方实施并与开放层对齐。当前实际实现是 API Key 加服务权益判定，正式 mTLS / OAuth 和资源策略仍待接入；不把这些待办装成已完成的 6G 鉴权创新。安全参考统一见[鉴权设计](superpowers/specs/2026-06-15-dynamic-auth-and-dispatch-design.md)。

### 没有 Intent ID，如何证明业务做完了？

不伪造任务状态。NEF 自己的 request_id 仅用于本次请求关联；内部 HTTP 回执按原样解释。另由场景数据源向独立接收通道推送状态、数据或媒体。没有共享关联字段时，回传只能证明某个通道收到了数据，不能证明它属于某次请求，也不能自动宣称意图已完成。多请求并行、取消、进度 / 结果关联需要后续双方共同定义。

### 哪些是真接入，哪些只是展示？

可验证的原型能力：场景目录、内存订阅、请求鉴权、MCP 发现与调用、配置驱动的 HTTP 转发、独立回传接口。场景演示数据和 SVG 画面始终带来源标识。真实内网地址、参数格式、凭证和回传来源尚需对接；未配置时报错，不静默回退。视频当前接收媒体文件，不等于直播、转码或实时流服务。重启会清除账号与媒体，不宣称生产级持久审计或计费。

## 口径依据

- [ITU-R M.2160-0（2023）](https://www.itu.int/rec/R-REC-M.2160-0-202311-I/en)：IMT-2030 总体框架背景，不作为本项目已实现 6G 的证明。
- [MCP 2025-03-26 Tools](https://modelcontextprotocol.io/specification/2025-03-26/server/tools)：本项目兼容版本的工具目录、inputSchema 与 tools/call 行为；不是声称采用最新协议版本。
- 功能是否完成以[接口参考](reference/integration.md)、当前代码与测试为准；原工作台的旧演示说法不能代替本期实现。

## 跨机器临时联调

仅在获准的测试网络中启用。从项目目录运行：

```powershell
python start.py
```

`0.0.0.0` 是监听地址，其他机器应访问 `http://<本机网卡IP>:8069/`；可先请求 `GET /api/v1/services` 测试连通。回传使用 `http://<本机网卡IP>:8069/api/v1/scene-feedback`，带对应场景 Key。如果页面从 localhost 打开，复制对接信息后须把地址替换为网卡 IP。

2026-09-09 本机 WLAN 地址核验为 `100.70.22.69`，已启动全接口监听，并在本机通过该地址验证页面和场景目录返回 200。IP 可能变化；这不等于已验证另一台机器连通。此次未修改防火墙、网络类型或路由器端口映射；跨机不通时先核对网络可达性和入站规则，不关闭整个防火墙。

本服务是可自助创建账号与权益的内存演示，不是生产部署；仅使用测试数据，不直接映射公网端口。获准的域名访问按下节配置 Tunnel 与 Access 入口保护，不要求固定 IP。重启清空账号、订阅与回传 Key。结束跨机联调后，将 host 改回 `127.0.0.1` 并重启即可恢复仅本机访问；如果已运行 Tunnel，还需停止对应连接程序，单纯改监听地址不会关闭 Tunnel 入口。

## Cloudflare Tunnel 演示部署

**启动检查记录（2026-09-17，新增订阅查询接口之前）：已恢复本机 NEF 服务，复用现有 Tunnel；有效机器凭据调用与回传仍待验收。** 当时检查 `Cloudflared` Windows 服务为 Running / Automatic，本机 `http://127.0.0.1:20241/diag/tunnel` 返回下述隧道 ID，`/ready` 返回 200、4 条就绪连接；8069 原无监听，已后台启动 `python -m uvicorn server:app --host 127.0.0.1 --port 8069`，未启用自动重载。启动后首页、`/api/v1/services`、`/openapi.json` 均返回 200，回传接口无 Key 返回 401；公网服务目录无 Access 凭据返回 302 到现有团队登录页。启动阶段的 14 项冒烟、场景回传和接口契约测试通过；测试对端为本地合成服务，不代表同事真实接口已联调。恢复启动阶段未修改业务代码、凭据、Access 策略、DNS 或 Tunnel 配置，也未重新验证浏览器登录后的页面。日志为 `.runtime/nef-20260917.stdout.log` 和 `.runtime/nef-20260917.stderr.log`，当前 PID 记录于 `.runtime/nef.pid`，停止进程前仍须核对身份。启动时没有加载真实执行、网络目录或模型配置；旧进程的内存账号及 Key 不会恢复。后续新增接口和模型 Base URL 的代码状态见上文“订阅查询联调”，不把磁盘代码修改等同于运行服务已经加载。

**发布记录（2026-09-11）：** `nef-demo-windows`（ID `2484b232-145f-4f43-b8f1-d1571a967bc2`）此前已核实为 Healthy，连接主机 `DESKTOP-RI63J7T` 与本机一致，版本为 `2026.9.0`。当时复核本机 `Cloudflared` Windows 服务为 Running / Automatic，NEF 服务目录返回 HTTP 200 JSON。该隧道和服务不是本脚本创建或安装。经用户确认，已发布 `nef.2012wtlab.com` → `http://127.0.0.1:8069`，控制台确认创建 CNAME 指向 `2484b232-145f-4f43-b8f1-d1571a967bc2.cfargotunnel.com`；未修改其他隧道或 DNS。

用户已选择用邮箱登录替代 IP 白名单，并同意 Zero Trust Free 结算页说明的超额扣费授权；不把“Free”解释成任何用量都不收费。经用户确认，`NEF Demo` Access 应用及 `NEF demo browser access` 策略已保存，保护 `nef.2012wtlab.com` 全部路径，仅精确允许 `wesleyvana0122@gmail.com`，应用和策略会话均为 1 week。已添加 One-time PIN，并重新打开应用核实：只选择该登录方法，不接受全部身份提供方。应用 ID 为 `fe4eeac1-ea68-41fa-a998-0f83281f75d8`，策略 ID 为 `d3b6316d-ee15-4697-9165-1be515901b03`。其他邮箱默认拒绝的配置已保存。浏览器经验证码页后已显示原版 NEF 页面、能力超市及三个场景套餐；未改用静态替代页面。

Tunnel 路由已开启 Protect with Access，使用 Team name `spring-cherry-1b51` 及 NEF 应用 AUD，未配置绕过入口。经用户确认，已生成 `nef-demo-colleagues` 服务凭据（有效期 1 year），并将 `NEF demo service access` 策略（ID `bfd21e0d-8a53-4a1d-a531-d96d29db28f9`）关联到 NEF 应用，Action 为 Service Auth，仅匹配该令牌，不使用 Any Access Service Token。密钥未写入项目或聊天，由用户从保留的 Service token details 页自行安全保存并单独交付同事；演示结束后可提前撤销。真实带凭据请求及回传仍待验证。

**外部鉴权检查：** 此前使用显式 User-Agent 对首页、服务目录和回传接口发送缺失、错误 Access 凭据的请求，六项均返回 HTTP 302，目标为本团队 Access 登录页，未获得 NEF 内容。2026-09-11 已通过下述限定路径的兼容规则解决 Python urllib 默认 User-Agent 触发 Cloudflare 1010 的问题，不再要求调用方设置特殊 User-Agent。

浏览器工具另开 `/api/v1/services` 验收标签时返回 `net::ERR_BLOCKED_BY_CLIENT`，没有取得接口响应；不能据此认定后端接口通过或故障。公网接口正向响应仍需真实 HTTP 客户端带专用凭据验证。

部署路径为“外部 AF / 浏览器 / 回传服务 → Cloudflare 域名与访问规则 → Tunnel → 本机 NEF”，不是把后端迁移到 Workers。不需要上传 GitHub，也不需要开放路由器或 Windows 入站端口。Tunnel 和本机服务都必须保持运行；休眠、断网、关闭程序会导致不可达。Tunnel 当前由已有 Windows 服务运行；NEF 仍是普通后台进程，尚未配置开机启动。电脑重启后不能仅凭 Tunnel 服务自动启动就认定 NEF 可用。

### 公网基础防护（2026-09-11 已实施）

- 域名 `2012wtlab.com` 已开启 **Always Use HTTPS**，最低 TLS 版本设为 **1.2**，TLS 1.3 保持开启。这是域名级设置；DNS only 的 VPS 入口不因此获得 Cloudflare 边缘防护。
- 已启用 Configuration Rule `API compatibility - disable browser integrity check`（ID `4237ccffb2cc43fba59c85556637ce72`），仅在以下范围关闭 Browser Integrity Check；不绕过 Access、业务 Key、WAF 或 DDoS 防护：
  - `nef.2012wtlab.com`：`/api/` 下的路径、`/mcp` 及 `/mcp/` 下的路径。
  - `sub2api.2012wtlab.com`：`/v1/` 下的路径。
- 域名全局 Browser Integrity Check 保持开启；未开启全站挑战、HSTS 或额外付费功能，未修改 VPS、DNS 代理状态、隧道路由或客户端凭据。无需新增登录步骤、证书或 IP 白名单。

规则表达式：

```text
(http.host eq "nef.2012wtlab.com" and (starts_with(http.request.uri.path, "/api/") or http.request.uri.path eq "/mcp" or starts_with(http.request.uri.path, "/mcp/"))) or (http.host eq "sub2api.2012wtlab.com" and starts_with(http.request.uri.path, "/v1/"))
```

**实施后实测（默认 Python urllib User-Agent、无登录 Cookie、不跟随跳转）：**

| 检查 | 结果 |
|---|---|
| HTTP 访问 NEF 服务目录、sub2api `/v1/models` | 301 跳转同主机同路径的 HTTPS |
| HTTPS 访问 NEF 服务目录，缺失或错误 Access 凭据 | 302 到 Access 登录页 |
| HTTPS POST NEF 回传接口及 `/mcp`，缺失凭据 | 302 到 Access 登录页 |
| HTTPS 访问 sub2api `/v1/models`，缺失或错误 API Key | 401，业务鉴权仍有效 |
| HTTPS 访问 sub2api 首页（不在规则范围） | 403 / Cloudflare 1010，未全局关闭浏览器检查 |
| 强制 TLS 1.0 / 1.1 连接 sub2api | 服务端拒绝协议版本 |
| 强制 TLS 1.2 连接 sub2api `/v1/models` | 握手成功，未带 Key 返回 401 |

这些结果证明跳转、协议限制和未授权拦截有效，不代表有效凭据业务调用或回传已完成联调。客户端必须直接使用 `https://`；HTTP 跳转不能保护此前已经明文发送的凭据。

**回滚范围：** 如兼容规则需要撤销，仅停用上述规则；默认 Python 客户端可能再次触发 1010。HTTPS 与最低 TLS 设置独立，不随规则回滚；若需恢复，分别回到 SSL/TLS → Edge Certificates 调整。不要为排障关闭 Access 或放行整个站点。

### 本地程序与运行

使用 Cloudflare 官方仓库发布的 `cloudflared 2026.9.0` Windows amd64 程序，位于 `.runtime/cloudflared.exe`。发布地址：
`https://github.com/cloudflare/cloudflared/releases/download/2026.9.0/cloudflared-windows-amd64.exe`。
官方资产 SHA-256：
`547057326266f0e1c7d50d102dbd22ff283d740c055bd61e94f10e2c606f89af`。
本地下载已通过哈希比对和版本命令验证。`.runtime/` 已忽略，不提交程序、日志或运行数据。

从仓库根目录执行只读预检查：

```powershell
.\scripts\Start-NefTunnel.ps1 -CheckOnly
```

**当前 Windows 服务已连接，不要重复运行下方启动命令。** 以下脚本仅供以后未使用 Windows 服务的手动运行方式。确认没有现有连接程序、并获得该隧道自己的 Token 后，才执行：

```powershell
.\scripts\Start-NefTunnel.ps1
```

在本地隐藏输入提示中粘贴 Token，不要粘贴整个安装命令，也不要把 Token 发到聊天或写进 Git。脚本将其放入子进程环境，而不是命令行参数；结束后恢复启动前的环境。若当前进程已有 `TUNNEL_TOKEN`，将使用它，请确认属于本次 NEF 隧道。脚本不安装系统服务，前台运行，`Ctrl+C` 停止。运行期凭据仍可被同用户或管理员进程读取，不作为抵御本机攻击的机制。日志使用 info 级别，不开启可能包含请求头的 debug 日志。

本机 NEF 未运行时另开终端执行 `python -m uvicorn server:app --host 127.0.0.1 --port 8069`；不要重复启动已占用端口。脚本启动子进程不等于连接成功，必须看到 Cloudflare Tunnel 的连接状态并验证实际请求。

### 公网入口与验收

1. 复用已连接的 `nef-demo-windows`，不重复创建，也不修改已有其他用途隧道；无需重新生成或轮换 Token。
2. 已确认并保存获准登录的完整邮箱，按精确邮箱匹配，不放行整个邮件域名或 Everyone。Access 允许名单独立于 NEF 自助注册，不能因创建 NEF 账号自动获得入口权限。
3. 已保存仅保护 `nef.2012wtlab.com` 全部路径的 Access 应用和邮箱策略，并复核仅启用 One-time PIN。应用与邮箱策略会话均为 1 week；浏览器登录后原版页面已验证，不修改其他应用的会话或权限。
4. 已配置 Service Auth 与专用服务凭据。客户端增加 `CF-Access-Client-Id`、`CF-Access-Client-Secret` 请求头，原有 NEF Authorization Key 不变。浏览器走登录会话，不在前端 JS 嵌入服务密钥。机器路径不能简单 Bypass，否则会失去入口保护。
5. 已在保存 Access 保护后发布域名路由，目标为 `http://127.0.0.1:8069`，同时开启 Tunnel 的 Access 令牌校验。HTTPS 登录页可达，控制台确认 DNS 已创建。
6. 缺失及错误凭据的六项外部检查、浏览器登录后原版页面检查已通过。尚需使用有效机器凭据调用接口、回传状态/数据/媒体；不能把登录页或 302 当成后端成功。内部执行接口未配置或未联调时，公网可达也不代表业务已经执行。

回传业务契约不变，仍是一条 `POST /api/v1/scene-feedback` 加场景 Key，媒体限制与示例见[场景接口说明](reference/integration.md)。通过 Access 入口时，回传方还需携带上述两个 Cloudflare 请求头；不用提供公网出口 IP。域名发布后从该域名打开页面再复制接口地址。重启 NEF 后重新获取场景 Key。若向内部目录发布 NEF 代理入口，还需按网络实际可达性核对 `config/registry.example.json` 对应的网关入口，不能误发布 localhost；内部调用端若使用受 Access 保护的域名也需要机器凭据。

## 网络目录与注册配置

- 新部署填写 `config/integration.local.json` 的 `registry`；旧部署通过 `NEF_REGISTRY_CONFIG` 指定独立文件仍兼容。
- 填写同事提供的实际 `catalog_url` / `publish_url`（模板默认 null），密钥通过 `token_env` 指向环境变量。
- 在 `mcp_servers` 中加入获准的 MCP 地址，和注册 JSON 的 URL 精确匹配。不能通过页面登记任意 URL 后绕过运维批准。
- 设置 `nef_base_url` 为内部网元能访问的 NEF 地址；否则无法发布 AF 的调用入口。配置 `network_clients` 的独立 `token_env` 与允许访问的 `af_accounts`。AF 账号 Key 不能替代内部调用凭证。
- 目录接口返回 `{items:[...]}`；发布接口明确 `{accepted:true}` 才显示已同步。其他 2xx 仅表示已提交。
- 目录和发布契约详见展示设计。未配置时可讲本地定义 / 登记，但工具发现和网络同步会明确失败，不伪造演示成功。

## 本地完整代理链路验收

执行 `python -m pytest tests/test_network_gateway.py -q`，其中真实 TCP 测试由本地 AF、NEF、目录接收端组成，确认从发布的 NEF endpoint 发现 / 调用 AF 工具并取得实际回执。`python tests/workbench_fixture.py --port 8071` 仅用于隔离浏览器验收，配置不会带入 8069；结束后停止。生产网络是否接收并保存记录仍需同事接口与真实环境确认。

## 演示准备与验收

- 先按[场景接口对接说明](reference/integration.md)交付回传地址和 Key、收集同事的执行接口资料，先验回传再验三入口转发；不在正式展示中把“待对接”当成成功。
- 预备演示账号与订阅；旧全局 Intent 仍沿用 PRO/MAX；新场景入口需单独开通对应场景，不依赖 PRO。正式账号 / 计费接入另行实施。
- 在对应场景生成回传接入信息，只把统一地址 `/api/v1/scene-feedback` 和场景专用 Key 交给数据发送方。无需 channel_id，图片 / 视频一次上传即展示；同一场景 Key 在本次服务内复用，只在详情展开时显示，不要投屏。
- 先验证一条状态、一份结构化数据、一张图片；视频文件另测浏览器实际解码和播放。实时流协议需单独确认，不把短视频文件演成直播。
- 网络侧 HTTP 回执只证明收到响应；业务结果由其内容或独立场景回传解释。
- 服务为单进程内存演示：重启会清除账号、订阅和回传缓存；不要在演示中途重启。

接口、上传格式、配置方法及限制统一见 [接口对接参考](reference/integration.md)。

---

## 2026-06 原工作台旧流程（历史记录，不代表当前交互与接口）

> **归档范围：下文所有问答、命令和页签描述只用于修改前工作台的历史核对，不可用于本次展示。** 特别是“参考回显兜底”“状态轨迹已实现”“全量计费审计”等旧口径，不代表新版 live 场景能力。原版工作台已经增量更新，当前讲解以本文上半部分为准，接口以接口参考为准。


日期：2026-06-12 ｜ 面向：现场讲解人 + 需要对接的业务同事
启动：`python server.py` → http://localhost:8000 ｜ 演示前建议重启一次服务（内存态清零，从"新 AF 入驻"讲起）

---

## 一、测试项 → 演示动作 对照表

> 测试要求原文归纳为 T1/T2/T3 三项。

### T1：能通过服务化接口、类 MCP 接口、意图接口调用 6G 新业务能力（通算、通感等）

| 接口 | 演示动作 | 界面证据 |
|---|---|---|
| 服务化接口（REST） | 「API 直调」选 `target_detection`（通感）或 `compute_offload`（通算）→ 发送 | 左侧请求报文（带 Bearer Key）、右侧 200 响应 + 🔐 鉴权回执 |
| 类 MCP 接口 | 「MCP 接口」点 `tools/list` → 选工具 `tools/call`；或「AF 智能终端」整链路 | JSON-RPC 报文、`subscribed` 标记、调用结果 |
| 意图接口 | 「意图受理」点示例"机器狗巡检，雾天也要看得清" → 发送 → 看状态推进 | 两段鉴权（第一道 NEF 按套餐受理 + 第二道网络侧 Planning Agent 运行时逐能力授权）、Intent ID、阶段流+进度条、执行轨迹回传 |
| （加分）场景级 | 「场景方案」选主推场景 → ▶ 一键运行 | 场景级回执：CAPIF 鉴权流水线→路由判定(命中后台 service_id)→受理→编排执行→回执 |

### T2：验证第三方应用访问权限合法性 → 调用内部新业务服务 → 获取结果 → 向第三方反馈

演示串法（一条线讲完）：
1. **权限合法性**：顶栏「注册账号」（注册即签发 Key）→「订阅与鉴权」展示 🔐 CAPIF 鉴权流水线（7 级逐级点亮：接入·限流/凭证解析/令牌校验/身份识别 Invoker/权限范围 scope/授权判定/审计落账，依据 3GPP CAPIF——AEF 对 API Invoker 逐次鉴权）；每次 API/MCP/意图/场景调用都会播放这条流水线，未授权时在「授权判定」级变红并触发 402；
   - 反例 1：不带 Key 调用 → 401（API 直调把 Key 清掉演示，或终端页未注册状态）；
   - 反例 2：调未订阅能力 → **402 Payment Required**（权限不足≠身份非法，给出订阅/按次两种合法化路径）→ 确认支付 → 通过。
2. **调用内部新业务服务**：意图受理提交 → NEF 转交网络内部 Network Agent → 状态推进（语义解析→业务编排→执行）。
3. **获取结果并反馈第三方**：状态到 completed，执行轨迹+结果摘要回传到 AF 界面（这就是"向第三方反馈服务结果"的呈现位）。

### T3：运营商网络调用第三方能力（网络 Agent 先获取第三方信息，再发起调用，结果反馈网络内部 Agent）

演示动作（「双向开放 · AF」页）：
1. **第三方信息注册**：左侧表单注册能力（名称/类型 ai_model/tool/data_source、描述、**定价**、端点 URL）→ 上架能力超市（third_party 标记）——这就是"网络 Agent 获取第三方的 API/tool 信息"的来源；
2. **内部发现端点**：`POST /internal/mcp`（第二个 MCP Server，面向网络内部 Agent/网元，信任域内免 AF 鉴权）——内部 Agent 经 tools/list 发现第三方工具（含提供方/定价/端点），tools/call 经 NEF 出向网关反向调用并自动入台账；看板「网络内部 Agent 视角」面板有 🔭 一键模拟按钮；
3. **网络发起调用**：右侧看板 ⚡模拟网络调用（顶部链路图逐节点点亮：AF 能力→NEF 超市→Network Agent→NEF 出向网关[鉴权·计费·审计]→AF Endpoint）；
4. **结果反馈网络内部 Agent**：调用日志显示调用方 Agent、耗时、状态、计费；顶部计费汇总卡（总调用/累计计费/70-30 分成/AF 收益）。

---

## 二、推荐演示动线（25-30 分钟，含讲解）

> 主线原则：**订阅与鉴权贯穿全程**——每个测试用例都先看到 🔐 鉴权回执，再看到业务结果；权限不足时看到 402 计费提醒而非冷报错。

| 时间 | 环节 | 动作与讲解点 |
|---|---|---|
| 0-3min | 开场·能力超市 | hero + 33 能力磁贴墙（8 大类：通感/AI 服务/通算/连接/定位/数据/安全身份/生态）+ 主推两场景（机器狗巡检 / 城市车流量测量）；讲"一张网络，无限调用"（低空目标识别追踪等为非主推；无人机执行单元属后续 AF 增值接入） |
| 3-6min | 注册与账号等级 | 注册账号（即签发 Key）→ 订阅与鉴权页：CAPIF 鉴权流水线（逐级点亮）、FREE/PRO/MAX 等级（PRO 含 basic 免订阅、MAX 含 basic+advanced）；现场升级 PRO，免订阅可用能力数变化 |
| 6-11min | T1-服务化接口 | API 直调：先调一个未授权能力 → 402 计费卡 → 确认按次支付 → 成功（鉴权回执+账单）；再以 PRO 身份直调 basic 能力；调用链轨迹条对照场景套餐 |
| 11-15min | T1-MCP 接口 | tools/list（✓/💳 标记、scenario_*、pipeline_*）→ tools/call；讲标准 /mcp 端点可被 Claude Code 直连 |
| 15-19min | T1-意图接口 + T2 | 用 PRO/MAX 或已订阅套餐的账号提交"机器狗巡检雾天看得清" → 第一道 NEF 受理鉴权（按套餐/等级）通过 → 转交 → 第二道由网络侧 Planning Agent 在执行中逐能力鉴权、状态逐步回传；换免费裸账号再发一次 → **第一道就被拒**（免费套餐不支持意图编排，挡住白嫖网络编排） |
| 19-22min | 场景级 + 自助编排 | 场景方案页一键运行场景（CAPIF 流水线 + 内联路由判定命中后台 service_id + 回执）；讲「套餐=优化编排·高精度·一口价 vs 自助编排=自挑 tool·更省·精度自负」；自助编排建 Pipeline → 它自动出现在 API 直调与 MCP 工具列表中并可一键运行 |
| 22-26min | T3-双向开放 | 注册第三方能力（设定价）→ 网络内部 Agent 视角面板（已发现工具）→ ⚡模拟网络调用 → 台账+70/30 分成收益 |
| 26-30min | 高潮·AF 智能终端 + 总结 | 终端发请求 → AF Agent 经 MCP 调 NEF → 计费拦截 → 确认支付 → 答复终端；总结四个测试项均含订阅+鉴权证据 |

---

## 二点五、关键设计口径（答疑用）

**Q：内部业务是按场景粒度实现的，不是我们的 tool 粒度，怎么办？后台收到 tool 级请求分得清吗？**
A：用 **NEF 路由判定**（每次调用的鉴权流水线末尾内联展示；后端 `GET /api/v1/dispatch-table`）化解：
- tool 粒度是 NEF 的**目录与计费粒度**，不要求业务侧按它实现。
- 每个暴露能力落地到二者之一：`backend:<service_id>`（后台按场景粒度声明实现的，演示初值=三个主推场景）或 `nef-ref`（NEF 参考回显兜底）。
- **NEF 只把后台声明过的 service_id 转发出去**，转发报文带显式信封 `{request_id, service_id, tool_id, params}`，后台靠 `service_id` 无歧义分发；没实现的 tool 级请求根本不出向，由 NEF 参考回显兜底——**后台绝不会收到看不懂的 tool 请求**，歧义在 NEF 这一层消化。（路由结果在每次调用的「路由判定」行直接可见，无需单独的表。）
- 业务侧返回的 steps 可以只有 1 步（整场景）也可多步，界面按返回 steps 渲染，多少步都能演。
- 该说法仅是旧设计；本期按接口对接参考确认实际格式，不强制异步任务接口。

**Q：场景需要返回什么结果？NEF 只记录状态够吗？**
A：NEF 定位为**受理/鉴权/计费/状态/审计 + 结果转发**，不复制业务画面。建议每个场景返回三层：
1. `status/progress/steps`（NEF 渲染执行轨迹——已实现）；
2. `result.summary` 一句业务结论 + 3-5 个关键指标（NEF 界面展示——待业务侧给 schema）；
3. `result.detail_url` 业务侧自己演示界面的跳转地址（NEF 只放链接/截图位）。
这样 NEF 界面有"状态+结论+审计"的完整闭环，重内容留给业务侧演示，不抢戏也不缺位。

**Q：外部 AI Agent 怎么直连 NEF 的 MCP？**
```
claude mcp add --transport http nef http://<host>:8000/mcp   --header "Authorization: Bearer <api_key>"
```
已实现 initialize / tools/list / tools/call；未授权工具调用返回计费提醒，携 `_confirm_pay: true` 按次付费执行。

**Q：AF 智能终端里那个 AF Agent 怎么实现？要不要 LLM？**
A：AF Agent 的活儿 = 把终端用户的话映射到该调哪个 NEF 工具，这正是 function-calling：把 `tools/list`（每个工具的 name+description+inputSchema）当作可用函数喂给模型即可。后端 `POST /api/v1/af-agent/plan` 实现三档：① 元查询（"有多少 tool / 列出工具 / 你能做什么"）直接作答；② 规则匹配兜底（关键词→能力）；③ 配置了 `ANTHROPIC_API_KEY` 则用 LLM 基于 tools/list 选工具，未配置自动回退规则。**演示默认走规则（零外部依赖、最稳）**；要现场展示"真 LLM 听懂自由表达"，导出 `ANTHROPIC_API_KEY` 后重启即自动启用，终端会显示「🧠 LLM 规划」。

**Q：套餐和自助编排是不是冗余了？**
A：不冗余，是两档。**套餐** = 运营商优化编排好的成套方案（高精度、有 SLA、一口价，不用操心怎么串）；**自助编排** = 自己挑几个 tool 拼，更省更灵活但精度自负。等同云上"托管服务 vs 裸 API"。

## 三、接口对接与后续实施

旧任务桥接与 T3 对接建议已由当前 [接口对接参考](reference/integration.md) 取代。不再要求内部必须提供 task_id、状态查询或进度百分比；旧“只改 intent_status 即可”建议不适用于当前 live 转发路径。

---

## 五、当前页签速查

| 页签 | 作用 | 对应测试项 |
|---|---|---|
| 能力超市 | 能力/套餐目录，注册入驻入口 | 背景 |
| 订阅与鉴权 | Key、CAPIF 鉴权流水线、FREE/PRO/MAX 等级、包月+按次账单 | T2-合法性 |
| API 直调 | REST tool 级调用 + 调用链对照 + 402 流 | T1 / T2 |
| MCP 接口 | JSON-RPC tools/list+call（tool/scenario/pipeline）+ 标准 /mcp 端点 | T1 |
| 意图受理 | NL 提交 → 转交 → 状态跟踪 → 轨迹回传 | T1 / T2-反馈 |
| 场景方案 | 套餐 vs 自助说明 + Skill 双视图 + 场景级一键运行（内联路由判定） | T1 加分项 / 粒度错配答疑 |
| 自助编排 | AF 自组 pipeline | 辅助 |
| 双向开放 · AF | 第三方注册 + 网络反向调用 + 分成 | T3 |
| AF 智能终端 | 终端→AF→NEF 全链路剧场 | 综合叙事 |
