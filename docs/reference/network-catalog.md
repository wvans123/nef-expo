# TRF MCP Server 契约与能力映射

分类：接口参考。更新：2026-09-23。字段和路径按本次联调约定实现；真实 IP、鉴权及 GET 完整回包尚待提供。目前仅验证本地模拟对端。

## 1. 服务、工具、能力和套餐

| 对象 | 当前归属与展示 |
|---|---|
| NF 能力 | NEF 的能力模型与 API / Tool 映射；NF 不必实现 MCP Server，首页现有能力卡不改成服务器卡 |
| MCP Server | TRF 登记服务名、描述、地址和类型；server description 描述服务，不能替代工具参数与调用定义 |
| MCP tool | 从获准服务的 `tools/list` 实际发现；显式发布后才上首页，保留所属 `serverName`，按 `toolType` 分类 |
| 场景 / 自助套餐 | NEF 管理能力组合、价格和权益；不发到 MCP Server 集合接口。已购套餐仍按原契约通知农场 |

TRF 四类为 `nf tool`、`computing tool`、`sensing tool`、`third-party tool`。报文字段沿用已经约定的驼峰 `toolType`，不同时发送 `tool_type`。外部接入固定最后一类。首页也按这四类展示，隐藏规划中能力和旧“生态服务”；历史 category 与既有订阅接口保留兼容。

首页本地能力按 `nf tool`、`computing tool`、`sensing tool` 合并为三个 MCP Server 登记，见第 8 节；不是每项能力一个 Server。三个 url 分别指向 NEF 的 `/mcp/groups/nf/mcp`、`/mcp/groups/computing/mcp`、`/mcp/groups/sensing/mcp`，各自只发现本组工具。TRF 读取模式只展示服务登记；description 不会被自动变成工具参数、订阅权益或可执行步骤。场景与自助套餐不属于这个集合。

## 2. 页面和配置

双向开放只填服务名称（`serverName`）、描述（`description`）、MCP 地址（`url`）。默认名称 `patrol-car-managementx`，描述为巡检任务、预检测开关、图像采样频率管理，URL 留空。名称最长 128 字符，匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，本进程内不可与其他登记重名。

表单“连接并发现工具”负责首次登记、握手、读取工具；已有记录的“重新发现工具”只重读该服务的工具，需先取消发布再操作；发现失败也保留“删除记录”。点击“发布”才上首页并发给 TRF；“取消发布”先本地下架，再撤回远端。远端撤回尚未确认时保留记录与重试入口，不能直接删除而丢失撤回信息。

首页最下方只展示“同步到 TRF”“取消 TRF 注册”“核对状态”及登记状态。来源切换收在 `/?ops=1#market` 的“目录来源设置”折叠区，普通页不显示；双向开放的详细 TRF 运维面板仍只在 `/?ops=1#afreg` 显示。此参数只是显示开关。首页内部目录操作由 NEF 实例执行：仍要求任一有效 NEF 账号 Key 以阻止匿名写入，但不要求 `af:register` scope，账号不进入 TRF 报文或登记状态；双向开放仍按其独立的 AF 权限管理。页面加载或 30 秒本地刷新不会自动请求 TRF。

只改 `config/integration.local.json` 中的 `registry`：

```json
{
  "trf_mcp_servers_url": "http://<TRF-IP>:<端口>/trf/api/v1/mcp-servers",
  "nef_base_url": "http://<对方可访问的NEF-IP>:8069",
  "token_env": null,
  "mcp_servers": {"http://<巡检小车IP>:<端口>/mcp": {}}
}
```

这是 registry 子对象片段，不要覆盖整个统一配置。一个集合地址用于 GET、POST 以及追加 serverName 的 DELETE；未取得地址时保留 null，不填占位 IP。`mcp_servers` 是精确 URL 允许列表，表单登记不会自动授权。认证如需 Bearer，`token_env` 填服务端环境变量名，不写密钥值。

首页发布需要两个地址：`trf_mcp_servers_url` 是接收登记请求的 TRF 集合地址；`nef_base_url` 是 NEF 自身根地址，程序自动追加 `/mcp/groups/{group_id}/mcp` 形成三个实际 MCP 端点。只填 TRF 地址可以查询目录，但不能生成登记中的 NEF 地址。`nef_base_url` 填对方能访问的本机 IP 加端口，或本平台可达域名；不填 TRF 地址、`0.0.0.0` 或 `/mcp` 路径。内网部署按 README 使用 `python start.py` 监听 `0.0.0.0:8069`；仅监听 `127.0.0.1` 的 Windows 后台须通过已配置的 Tunnel 访问，不能直接使用局域网 IP。

这两个配置不会从浏览器的 Host 自动猜测。修改 JSON 后刷新或核对即可，不需要为地址变更重启清空账号；如果页面仍与文件不一致，先确认访问的 NEF 机器及端口，再检查进程是否设置了覆盖统一文件的 `NEF_REGISTRY_CONFIG` 或 `NEF_INTEGRATION_CONFIG`。页面的“本 NEF 的访问地址”提示对应 `registry.nef_base_url`；真实可达性仍需由对方验证。

新协议发布原始 MCP 地址，TRF 消费者可能直接访问它；现有 NEF 代理入口仍独立保留，但不会偷偷替换这次约定的 url。取消发布会关闭 NEF 展示和新代理调用，不会关闭外部 MCP 服务本身。

## 3. NEF 发给 TRF

### 发布

`POST {trf_mcp_servers_url}`，`Content-Type: application/json`，双向开放发送六个基础字段，加可选字段 `isThirdParty: true`：

```json
{
  "serverName": "patrol-car-managementx",
  "serverType": "Streamable HTTP",
  "toolType": "third-party tool",
  "description": "管理巡检小车，如在巡检小车上启动或关闭巡检任务、配置目标预检测开关、图像采样频率等。",
  "url": "http://<巡检小车IP>:<端口>/mcp",
  "serverStatus": "active",
  "isThirdParty": true
}
```

`serverType` 按更正后的枚举发送 `Streamable HTTP`，由 `_trf_publication()` 生成。固定值由后端生成，前端不能覆盖。字段大小写为 `isThirdParty`：首页本地能力显式发送布尔 false，双向开放发送布尔 true，两处统一使用七字段注册结构。GET 若返回该字段须与外发值相同，旧 GET 省略时保持兼容。不附加工具数组、source_account、NEF Key 或套餐字段。

### 查询与确认

`GET {trf_mcp_servers_url}`，无正文。支持完整数组，以及 `items`、`data`、`servers`、`records`、`mcpServers`、`mcp_servers` 列表包装；也支持两层包装，例如 `{"code":200,"message":"OK","data":{"items":[...],"total":3}}`。GET 至少返回 serverName、toolType、url；兼容 server_name / tool_type / server_type / server_status / is_third_party 别名，若同时返回两种名称且值冲突则报错。未返回的描述、类型、运行状态保留为空，不自行填 active；可选布尔 isThirdParty 保留。数据库 id、时间戳等额外字段忽略。POST 仍使用约定的七个驼峰字段，不发别名。

包装中的 `code` 可省略或为 `0` / `200`（兼容字符串）；明确 `success:false`、非空 `error` 或其他 code 返回 `trf_response_rejected`。`total` / `totalCount` / `totalElements` 若存在必须等于列表长度；非空下一页游标、hasMore、pagination 或多页标志返回 `trf_incomplete_list`，不把不完整列表用于“未登记/已删除”的判断。未知包装、缺失身份字段及重复 serverName 返回 `trf_schema_invalid`，不会当作空目录。真实 TRF 如采用其他成功 code 或分页契约，需提供回包后调整适配。运维查询保留未知类型供排查；首页仅显示四种约定类型，并报告跳过数量。

发布的 HTTP 2xx 不直接等于同步成功：随后 GET，以 serverName、toolType、url 确认服务身份（url 允许末尾斜杠差异）；若 GET 带 isThirdParty，值也须匹配。description、serverType、serverStatus 不要求逐字回显，首页用 metadata_differences 提示差异，不因此把存在的登记计成 0。已登记不等于运行状态 active，也不证明后续工具可执行。旧 GET 可省略 isThirdParty，但这不证明它已被对方保存。查不到匹配项或查询暂不可用记 submitted，请求或 schema 错误按实际记录。

### 撤回

`DELETE {首次发布集合地址}/{serverName}`，无请求体。随后 GET 确认同名记录缺席才记 `synced`；DELETE 返回 404 也会读回确认。失败或仍存在时保留撤回责任并可重试。

首次发布的地址及名称保存在进程内；配置改址后该记录仍在原目标重试 / 撤回，避免删除新环境的同名服务。确认撤回后可删除本地登记，再用新配置重新登记。超时可能已经到达对端，不自动声称未发送；当前没有对方幂等规则，重试需核对实际记录。

POST 和 GET 使用同一个 `registry.trf_mcp_servers_url`，统一去掉末尾 `/`；DELETE 仅在该集合地址后追加 URL 编码后的 `/serverName`，无正文。不需要另配查询/删除 IP，也不使用旧 `withdraw_url`。所有请求不走系统代理、不跟随重定向。

登记与状态目前仍在内存，重启会清空。首页内部能力可在配置不变时，通过显式“核对状态”或“取消 TRF 注册”GET 精确匹配并恢复撤回信息，不依赖上一次本地缓存；没有自动启动删除。双向开放登记仍需重启前撤回，或由对方按 serverName 清理，不能凭名称前缀推断归属。

## 4. 页面调用 NEF 的接口

本节双向开放登记接口需 `Authorization: Bearer <NEF账号Key>` 与 `af:register` scope，公开市场除外；首页内部目录操作见第 8 节，使用任一有效账号 Key，不要求 AF scope。

| 方法 / 路径 | 正文与行为 |
|---|---|
| POST `/api/v1/network/servers` | `{serverName,description,url}`；只保存；旧 `name` 保留兼容 |
| POST `/api/v1/network/servers/{id}/discover` | 无正文；连接允许列表地址并发现工具 |
| GET `/api/v1/network/servers/{id}/publication` | 预览六字段及 isThirdParty=true，不外发；外部发布无需 nef_base_url |
| POST `/api/v1/network/servers/{id}/publish` | 无正文；要求至少发现一个工具，上首页并 POST / GET TRF |
| POST `/api/v1/network/servers/{id}/unpublish` | 无正文；下架并 DELETE / GET TRF；旧 `/sync` 为 publish 别名 |
| DELETE `/api/v1/network/servers/{id}` | 无正文；删除未发布且无需远端撤回的本地记录；繁忙、已发布或待撤回返回 409 |
| GET `/api/v1/network/servers` | 当前账号私有登记与全部 open 登记；包含 discovery/publication/sync 状态 |
| GET `/api/v1/network/trf/servers` | 真实请求 TRF；`{status:"loaded",servers:[...]}`，未配置为 `not_configured` / 空数组 |
| GET `/api/v1/network/market` | 无 Key；只返回显式发布的工具/套餐公开投影，工具带 serverName、toolType，不含上游 URL |

未授权 401/403；私有记录越权 404；同名冲突/繁忙/未先撤回 409；字段无效 422；配置无效 503；上游协议/HTTP 失败 502、超时 504。发布操作可能 HTTP 200 但 `sync_status=failed`，调用方必须读状态。

发现失败、未发布、确认撤回后的记录可删除；open 登记可由具备该 scope 的其他账号管理，私有登记仅所有者可管理。

## 5. 第三方工具的账号订阅与调用

发布决定所有账号能否在商城看到工具；订阅决定当前账号能否经 NEF 调用。点击商城工具卡可“订阅工具”，订阅后可“取消订阅”或“去 MCP 调用”；订阅与鉴权页另列第三方工具订阅。不同账号互不继承，PRO/MAX 与发布者身份均不自动开通。价格暂为演示免费（price=0、billing=demo_free），不增加月费用，不代表商业定价。

| 方法 / 路径 | 请求与响应 |
|---|---|
| GET `/api/v1/network/market/subscriptions` | 账号 Bearer；`{subscriptions:[...]}`，只读当前账号 |
| POST `/api/v1/network/market/subscriptions` | 账号 Bearer + capabilities:invoke；`{"tool_id":"<公开市场items中的id>"}`，订阅已发布的实际工具，幂等 |
| DELETE `/api/v1/network/market/subscriptions` | 同一 Key/scope 和正文，取消当前账号该工具权益，已下架也可取消 |
| GET `/api/v1/auth/info` | 新增 external_tool_subscriptions；不混入原基础能力列表 |
| GET `/api/v1/integration/subscriptions?account_id=1` | 在原 1.1 响应追加 external_tool_subscriptions；演示编号查询，无 Key；不改变 purchased_packages |

订阅写接口只接受 tool_id，不接受 account、价格或上游 URL，返回 `{tool_id,subscribed,billing:"demo_free"}`。记录字段含 id、server_id、serverName、name、description、inputSchema、mcp_name、toolType、price、billing、available，不含上游 URL、来源账号或凭据。

公开市场工具项新增 mcp_name、price、billing。调用者通过 NEF `/mcp` 初始化和 tools/list，找到准确 mcp_name 后 tools/call；`/api/v1/mcp/tools/call` 兼容入口做相同校验。名称按服务与原工具名生成，避免不同服务同名冲突。tools/list 中已发布外部工具附 subscribed 标志；可见不代表有权调用。参数按实际发现的 inputSchema 校验，返回上游原始 CallToolResult，isError 不被改写；不会自动执行或重试有副作用的工具。

服务端逐项校验账号、mcp:tools、此工具订阅、仍已发布、实际工具存在、URL 允许列表和参数；任一不满足均不向外部发起调用。JSON-RPC tools/call 通知不执行工具。NEF 使用服务端配置的 MCP 凭据连接上游，不透传消费者 Key。独立 network_clients 网关继续按原网内授权，不能用商城订阅替代它。

取消订阅拒绝后续调用；提供方下架时保留订阅但 available=false，重发同一工具可恢复可用；删除服务登记会清理其订阅。正在执行的请求不承诺被撤销。已订阅且可用的外部工具可进入编排能力池，保存套餐仍只是声明。订阅只保存在 NEF 进程内，重启清空；不通知农场、不重复发布 TRF、不创造真实订单。

## 6. 旧目录兼容边界

旧 `catalog_url`、`publish_url`、`withdraw_url` 仅为已有部署保留，不是本次 TRF MCP Server 契约。旧 `/catalog/refresh` 导入 `items` 工具/套餐快照；旧 `/catalog/publication` 与 `/catalog/publish` 接受 `capability_ids` / `service_ids`，生成 `type=nef_catalog_publication` 元数据，发送到旧 publish_url。它们不会发送到新的 trf_mcp_servers_url，活动页已移除旧目录导出入口。

显式旧 publish_url 模式保留 `mcp_server_registration`（NEF 代理地址 + tools）、`network_package_declaration` 及 POST withdraw_url 撤回，`accepted:true` 才确认。新配置模式自助套餐仅本地发布，`sync_status=not_required`。不要把旧报文发到 `/trf/api/v1/mcp-servers`。

## 7. 联调与维护验证

1. 同事提供实际 TRF 集合地址、GET 完整回包、认证方式和重复 serverName 的行为。
2. 将巡检小车地址加入允许列表，页面填写三个字段并发现真实工具。
3. 发布后核对 TRF 基础字段及 isThirdParty、首页工具所属服务；取消后核对 DELETE 与 GET 缺席，最后删除本地记录。
4. 真实工具调用单独验收；查询 TRF 不授予订阅或执行权限。

`tests/test_trf_mcp_registry.py` 覆盖 HTTP 契约和失败边界；`tests/test_integration_ui.cjs` 与 `tests/test_catalog_ui.cjs` 在 `tests/workbench_fixture.py --port 8071` 隔离服务上验证桌面/手机页面，后者现在验证运维查询而非旧目录导出。截图在忽略上传的 `.runtime/` 中。测试不访问真实 TRF 或正式 8069 账号。

账号订阅验收由 `tests/test_market_subscriptions.py` 与 `tests/test_market_subscriptions_ui.cjs` 覆盖：三个账号隔离、订阅/取消、两个 MCP 入口、真实本地 AF 回执、下架和删除；后者同样只用隔离测试端口。

## 8. 首页本地能力同步与 TRF 读取模式

首页可用本地能力的分类由 `skills.py` 统一派生，卡片与外发报文使用同一个 `toolType`：

| toolType | 本地能力范围 |
|---|---|
| nf tool | 连接、终端位置、电子围栏、数据、安全、网络智能分析 |
| computing tool | 计算卸载、云渲染、算力服务保障、AI 推理 |
| sensing tool | 目标检测/追踪、环境重构、融合、车流量感知/预测、感知虚拟围栏 |
| third-party tool | 双向开放发现并发布的工具；由其发布者单独同步 |

当前 23 项可用能力归入三个登记：nf tool 覆盖网络 12 项，computing tool 覆盖计算 4 项，sensing tool 覆盖感知 7 项。只选 available、非 ecosystem 的内置能力；规划项、旧能力注册/收益结算、场景套餐、自助套餐不发送。description 列出该类能力名称，url 为 `nef_base_url/mcp/groups/{group_id}/mcp`。TRF 注册不等于执行接口已接通，也不会赋予订阅。

### 首页按钮调用的 NEF 接口

| 方法 / 路径 | 行为 |
|---|---|
| GET `/api/v1/network/trf/catalog` | 无 Key 只读缓存；groups 为三个分类登记，summary 统计 Server 数；items 将分类状态投影到能力卡，capability_summary 统计能力数；legacy_items 为可核对的旧登记；remote_items 为四类服务目录 |
| POST `/api/v1/network/trf/catalog/refresh` | 无正文；任一有效 NEF 账号 Key（不要求 AF scope），NEF 向 TRF 发 GET，核对全局状态 |
| POST `/api/v1/network/trf/catalog/publish` | 同上鉴权；先 GET，跳过已匹配分类，再对未登记分类 POST（最多三次），最后 GET 确认 |
| POST `/api/v1/network/trf/catalog/unpublish` | 同上鉴权；仅 DELETE 本平台本批已发送或已精确匹配的条目，再 GET 确认；不删除第三方/同名冲突记录 |

按钮是一次页面操作；现有 TRF 契约一次 POST 只接受一个 MCP Server，因此同步是三次单条 POST，不虚构数组批量接口。部分失败保留逐类结果可重试。同名且精确匹配本 NEF 旧版根地址或 `/mcp/groups/{group_id}` 登记时，同步先 DELETE 旧项、GET 确认缺席，再 POST 新端点；不确定的删除结果不会继续 POST。其他同名不同地址、分类或第三方标识为冲突，不覆盖。撤回保留首次目标，配置改址后不会误删新环境同名登记。

首页取消按钮在已配置 TRF 和 NEF 地址时即可使用，包括本进程尚无登记缓存的情况；点击后先 GET 精确匹配，再按 serverName DELETE。GET 失败或不完整时不盲目 POST/DELETE，也不显示“处理完成”。失败项保留 `sync_error`；可用时附 `sync_diagnostic: {code, method, http_status}`，例如 GET / HTTP 503 或 POST / HTTP 400。页面底部与状态点提示显示具体原因，不回显地址、响应原文或凭证。`can_withdraw` 表示进程内仍有待确认撤回的登记，不再作为取消按钮的唯一启用条件。

状态包括 unknown（灰，尚未核对）、registered（绿，服务身份已确认）、unregistered（红，读回缺席）、submitted（黄，已提交待确认）、failed、conflict。首页显示“MCP Server 3 个 · 已注册 3 个 · 覆盖能力 23 项”，卡片跟随所属分类；GET 失败显示待确认及原因，不把未知状态写成“已注册 0”。缓存与发送记录按 NEF 的 TRF/自身地址组合共享，与当前 AF 账号无关；换账号读到同一状态，重复同步先核对并跳过已登记项。重启后需显式读取核对服务身份，不能按名称前缀直接删除。

### 发往 TRF 的本地能力报文

`serverName = "nef-group-" + sha256(nef_base_url去尾斜线)前8位 + "-" + group_id`，group_id 为 nf / computing / sensing。nef-group- 及旧 nef-cap- 前缀均保留给 NEF，外部登记不得使用。例：

```json
{
  "serverName": "nef-group-<base-hash>-sensing",
  "serverType": "Streamable HTTP",
  "toolType": "sensing tool",
  "description": "NEF 感知能力，包括：目标检测、目标追踪等",
  "url": "http://<NEF-IP>:8069/mcp/groups/sensing/mcp",
  "serverStatus": "active",
  "isThirdParty": false
}
```

旧单工具入口 `POST /mcp/capabilities/{capability_id}` 继续保留兼容和原有鉴权，但不再作为首页 TRF 同步单元。三个分类的 `POST /mcp/groups/{group_id}/mcp` 对 `initialize`、`notifications/initialized`、`ping`、`tools/list` 无需 Key，`tools/list` 只返回该组已开放能力的名称、描述与 inputSchema，不含订阅信息；`tools/call` 要求 NEF Bearer Key、`mcp:tools` scope 及原有权益/付费规则，并按配置执行真实路由。无 id 的通知不执行调用。普通 `GET` 同一路径返回 `{"tools":[...]}`，仅作为 TRF 直接 GET 的 JSON 兼容方式，不是 MCP JSON-RPC `tools/list`；请求 SSE 的 GET 返回 405（不支持 SSE 流）。旧 `/mcp/groups/{group_id}` 路径仍可用，但不再作为登记地址。不要把无 Key 发现误认为无 Key 调用或真实现场执行已经就绪。

升级后 GET 识别旧版 nef-cap- 登记时，须同时匹配本 NEF 地址哈希、能力名、单工具 URL、toolType 及可选 false 标识。它们显示在 legacy_items，不计入三个 Server，也不会在同步时自动删除。显式“取消 TRF 注册”会撤回已核对归属的分类及旧条目；随后再同步即可只保留三个分类。第三方、未知条目或同名不同地址不删除。

运维页底部展开“目录来源设置”，将展示来源切为“TRF 目录”后点击“刷新目录”，即可预览四类记录；不会反向发布、自动连接 MCP 或创建订阅。选择只保存在当前浏览器，并且仅在 `?ops=1` 中生效，返回普通首页始终展示本地能力。未知类型跳过；读取失败保留上次内容并提示过期，不以空列表掩盖失败。`tests/test_trf_catalog.py`、`tests/test_capability_mcp.py` 与桌面 `tests/test_home_trf_ui.cjs` 验证这些边界，真实 IP 暂不测试。
