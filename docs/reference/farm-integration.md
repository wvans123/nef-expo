# 农场平台双向联调

分类：接口参考 / 联调流程。更新：2026-09-21。面向农场平台、NEF 和网络侧开发同事；巡检小车使用相同 MCP 接入流程。

## 1. 本次范围

订购通知、补偿查询与双向 MCP 分别验收，不要求农场与 NEF 互通登录系统：

```text
订购：农场页面 --跳转并带账号编号--> NEF --POST subscriberId + servicePlan--> 农场后端
查询：农场平台后端 --账号编号--> NEF --已购套餐及详情--> 农场页面
开放：农场 MCP --> NEF 登记并发现工具 --> 显式发布六字段及 isThirdParty=true 至 TRF（原始 MCP 地址）
可选代理调用：网络客户端 --> NEF 代理入口 --> 农场 MCP --> 原路返回结果
```

当天使用内存测试数据，重启后重新准备账号、订阅和 MCP 登记。换电脑首选 `python start.py`，地址为 `http://<NEF电脑IP>:8069`，无需旧域名或 Cloudflare 头；步骤见 [README](../../README.md#二换电脑启动与配置)。旧 Tunnel 部署仍可使用 `https://nef.2012wtlab.com` 和 Access。上传不会重启已有服务；回调路径和价格规则见 [curl 手册](manual-curl.md)，实际 IP 在本机配置填写，本机尚未访问真实对端。

真实农场 MCP 地址、鉴权和网络目录发布地址尚未提供。现有自动测试通过真实本地 TCP 验证完整流程，但农场和目录都是模拟对端，不代表生产网络已经接通。

本文维护 MCP 登记与双向联调流程；订阅响应的完整字段以[订阅查询接口](subscription-query.md)为唯一契约。场景执行与回传另见[场景接口说明](integration.md)。

## 2. 三方先交换什么

| 提供方 | 必须提供 |
|---|---|
| NEF | 内网地址、约定账号编号；仅旧公网入口需要 Access。6.0 开放登记无需 NEF Key，私有分步登记另提供账号 Key |
| 农场平台 | 可访问的 `/business/v1/service-plans` 完整 POST 地址、鉴权及业务响应；另提供完整 MCP HTTP URL、鉴权、工具/schema、测试参数及预期结果 |
| 网络侧 | 接收 MCP 登记的完整 HTTP POST 地址、鉴权方式、成功确认格式；哪个客户端将调用农场工具 |
| NEF 运维 | 精确 URL 允许列表、NEF 对农场的凭据、目录发布配置、网络调用方独立凭据和可访问 AF 账号范围 |

先选一个只读工具，例如 `get_field_status(field_id)`。该名称只是双方可采用的联调示例，不是已经存在的农场业务工具；已有其他工具就使用对方真实名称和 schema。首次不测试灌溉、设备移动等会改变现场状态的操作。

## 3. 地址和凭据不能混用

所有从另一台电脑访问 NEF 公网的请求，都需要：

```http
CF-Access-Client-Id: <NEF单独提供>
CF-Access-Client-Secret: <NEF单独提供>
```

不要跟随 302 后把 HTML 登录页当作成功。机器凭据放农场后端环境变量，不放浏览器脚本。

| 操作方向 | 额外 Authorization |
|---|---|
| 农场查询已购套餐 | 不需要，只传 `account_id` |
| 农场开放登记 MCP（6.0） | 不需要 NEF Key；归属配置的开放登记账号 |
| 农场登记 / 发现 / 发布自己的 MCP | `Bearer <账号1的NEF Key>`，需要 `af:register` scope |
| 网络客户端经 NEF 调用农场 | `Bearer <独立网络调用Key>`；不能用账号1的 NEF Key |
| NEF 连接农场 MCP | 运维设置的农场 Bearer Key，NEF 服务端读取 |
| NEF 向网络目录发布 | 运维设置的目录 Bearer Key，NEF 服务端读取 |

编号是数据定位符，不是授权凭据。只读查询可查询其他约定演示编号；不将其用于生产租户数据。私有 MCP 登记通过凭据确定 `source_account`，开放登记则取服务端 `open_registration_account`，均不接受正文伪造来源。无 Key 接口只适用于获准测试网络。

## 4. 第一条链路：订购通知与查询

农场按钮导航到 `http://<NEF电脑IP>:8069/?account_id=1`；使用旧公网域名时需通过 Access 登录。订购通知结构为 `subscriberId` + `servicePlan`，套餐包含 UUID、名称、描述和价格；默认勾选全部可用组成能力并附加 `networkCapabilities`。页面可缩小范围但至少选一项，后端仍兼容空数组并省略该字段。NEF 不实现 PA/CA 决策，四字段平铺旧格式不再使用。

本次外发 `subscriberId` 固定为 `"subscriber-001"`，本地账号 `1/2/3` 和跳转链接不变；不同本地账号的通知在农场侧都属于同一个测试订购者。字段、选能力/不选能力两种完整示例、价格配置与重试见[套餐订购通知](subscription-query.md#10-跳转订购与套餐通知)。接收方按事件头去重；HTTP 2xx 仅表示通知送达，业务入库响应待确认。浏览器跳转不要携带机器 Secret。

原 GET 查询保留作首次加载和失败后的补偿读取：

1. NEF 操作员在页面注册/切换账号 `1`；重启前浏览器保存的 Key 已失效，重新注册同名账号取得当前 Key。
2. 农场后端查询，以真实已购状态为准；新注册空账号才应得到 `purchased_packages: []`。
3. NEF 操作员在商城为 `1` 开通一个场景套餐。
4. 农场再次查询并刷新页面，以 `purchased_packages` 展示已购项和详情。

```http
GET /api/v1/integration/subscriptions?account_id=1
Accept: application/json
CF-Access-Client-Id: <Client ID>
CF-Access-Client-Secret: <Client Secret>
```

农场页面使用方法：

- 遍历 `purchased_packages`，显示 `name`、`description`。
- 使用 `(kind, id)` 作为唯一键；同名旧能力套餐和新场景不可合并。
- 详情展开 `components`，显示组成能力名称；`standalone_entitled` 是组件的独立调用权益。
- `modes` 是场景支持的入口，`intent_example` 是意图示例；有 `tool` 时可查看 MCP 名称与输入 schema。
- 不能把场景组件直接转换成可独立调用的工具。购买场景不等于独立购买全部组件。
- `kind=capability_package` 的 `modes=[]`，表示本查询不声明它拥有新场景执行入口。

本次“已购”是演示开通记录，没有真实支付订单。动态网络目录或自助编排草稿未实现购买流程，不会因展示或同步就进入已购列表。

完整字段、响应、错误与 Python 示例见[订阅查询接口](subscription-query.md)。只读查询可以编号调用；真正执行网络能力仍需 NEF Key，并独立验收实际执行配置。

## 5. NEF 运维配置

新部署在 `config/integration.local.json` 的 **`registry` 对象内**填写下面字段，不要覆盖整个统一配置。旧部署仍可用 `NEF_REGISTRY_CONFIG` 显式指定独立文件或 JSON 字符串，该变量优先。下面是**待替换示例，不是现有有效配置**；内网部署的 `nef_base_url` 使用 `http://<NEF电脑IP>:8069`：

```json
{
  "trf_mcp_servers_url": "http://<TRF-IP>:<端口>/trf/api/v1/mcp-servers",
  "token_env": "NEF_DIRECTORY_TOKEN",
  "nef_base_url": "https://nef.2012wtlab.com",
  "mcp_servers": {
    "https://farm.example.invalid/mcp": {
      "token_env": "NEF_FARM_MCP_TOKEN"
    }
  },
  "network_clients": {
    "farm-test-network": {
      "token_env": "NEF_FARM_NETWORK_TOKEN",
      "af_accounts": ["1"]
    }
  }
}
```

`.example.invalid` 全部不可访问，必须替换为双方实际地址。字段含义：

| 字段 | 说明 |
|---|---|
| `trf_mcp_servers_url` | TRF MCP 集合地址，发布 POST、查询 GET、撤回 DELETE 追加 serverName；空时不外发 |
| `token_env` | NEF 向目录发送 Bearer Key 所用环境变量名 |
| `nef_base_url` | 网络客户端能访问的 NEF 地址，用于独立代理链路；AF 发布不依赖此字段；首页本地能力单工具入口发布需要此字段 |
| `mcp_servers` | 精确匹配登记 URL 的允许列表；页面登记不会自动加入允许列表 |
| `open_registration_account` | 开放登记来源账号，默认 `1` |
| `allow_unlisted_mcp_servers` | 默认 false；获准隔离测试网才可放宽，风险见 6.0 |
| `mcp_servers.<url>.token_env` | NEF 连接该农场 MCP 使用的 Bearer Key 环境变量名 |
| `network_clients` | 独立网络调用者配置；每个调用者绑定一个 Key 环境变量及允许的 AF 账号 |
| `af_accounts` | 精确允许访问的农场账号名，本例只允许 `1`，不是所有账号 |

只有确实无鉴权的获准测试对端才将 `token_env` 设为 null；配置了环境变量名但值缺失会失败，不自动降为匿名。当前出向认证配置只支持 Bearer，若农场或目录需要额外自定义头、OAuth 或 Cloudflare Access 头，应先对齐适配，不能声称任意鉴权都能直接用。

配置文件中的 URL 等变动会在相关请求时重新读取；启动时没有设置的进程环境变量，需要安排重启后才能生效。实际秘密不要写进 JSON、文档或登记请求。登记 URL 必须由 NEF 主机可达；农场电脑的 `127.0.0.1` 不是 NEF 可用地址。不要为联调关闭 Access、整个防火墙或允许任意出向 URL。

## 6. 第二条链路：农场 MCP 注册到网络

### 6.0 无 Key 一步注册（内网）

`POST /api/v1/af/mcp-servers`，JSON 为 `{"serverName":"farm-management","url":"http://<农场IP>:<端口>/mcp","description":"..."}`。参数限制与 6.1 相同，无需 NEF Key；同一 URL 重复调用更新开放登记，不重复创建，不修改同 URL 的私有登记。

NEF 以 `registry.open_registration_account`（默认 `1`）登记并标记 `registered_via:open`，立即执行 initialize、notifications/initialized、tools/list。登记与发现不会发布，即使已配置 `trf_mcp_servers_url` 也保持草稿；随后由页面账号显式发布。按新 TRF 契约发布原始 MCP URL，独立 NEF 代理入口继续保留。

成功返回登记记录、`created`、`discovery_status=ok`、`publication_status=draft`、`sync_status=pending`，提示等待显式发布。发现失败返回 502/504（允许列表拒绝为 403/503），detail 保留登记 ID 和 `discovery_status=failed`。列表接口发现成功的状态词仍为 `discovered`。

开放登记对所有登录账号可见，任意具备 `af:register` scope 的账号可 discover、publication、publish、unpublish、delete；私有登记不变。`registry.allow_unlisted_mcp_servers` 默认 false，只有精确允许列表 URL 可连接；获准隔离测试网可设 true，允许无 Key 调用者让 NEF 连接任意合法 HTTP(S) URL，存在内网探测风险，勿对不可信网络启用。此开关不取消网络反向调用的独立凭据与 af_accounts 校验。

农场 MCP URL、TRF 集合实际地址及 GET 完整响应仍待提供。本机只验证本地模拟对端，具体命令见 [curl 手册](manual-curl.md)。以下 6.1 起保留带 Key 的分步流程。

以下路径均相对于 NEF 公网 Base URL，所有请求携带第 3 节 Access 头。除特别说明外再带：

```http
Authorization: Bearer <账号1的NEF Key>
Accept: application/json
```

### 6.1 登记 MCP

```http
POST /api/v1/network/servers
Content-Type: application/json
```

```json
{
  "serverName": "farm-management",
  "url": "https://farm.example.invalid/mcp",
  "description": "提供获准测试地块的只读状态查询"
}
```

| 参数 | 必填 | 限制 |
|---|---|---|
| `serverName` | 是 | 最长 128 字符，匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`；本进程内全局唯一；旧 name 仅兼容 |
| `url` | 是 | 完整 HTTP(S) URL，最长 2048 字符，不能在 URL 中带用户名密码或片段 |
| `description` | 否 | string，最长 2000 字符 |

HTTP 200 响应关键字段：

```json
{
  "id": "srv_<服务返回的ID>",
  "source": "AF",
  "source_account": "1",
  "registration_status": "registered",
  "discovery_status": "not_discovered",
  "sync_status": "pending",
  "tools": [],
  "gateway_path": "/api/v1/network/af-servers/srv_<服务返回的ID>/mcp",
  "access_via": "NEF"
}
```

以上为字段摘录，实际还返回名称、URL、说明。后续请求使用真实返回的 `id`，不要使用示例字符串。登记成功只表示 NEF 保存记录，没有连接农场，也没有发布网络。

同账号、同 URL、同登记类型重复 POST 更新原记录，不创建重复项。已发布时须先取消发布再更新或重新发现；否则返回 409。每账号最多 64 个登记，取消发布不是删除登记；另用 DELETE 删除未发布且无需远端撤回的本地记录。

### 6.2 发现工具

```http
POST /api/v1/network/servers/{server_id}/discover
```

无需请求体。NEF 检查允许列表后，连接农场执行：

```text
initialize -> notifications/initialized -> tools/list（必要时继续分页）
```

成功判据：HTTP 200、`discovery_status=discovered`，`tools` 中出现双方约定工具名和 `inputSchema`。`registration_status=registered` 单独不能算发现成功。

本地只读示例工具定义：

```json
{
  "name": "get_field_status",
  "description": "读取测试地块状态",
  "inputSchema": {
    "type": "object",
    "properties": {"field_id": {"type": "string"}},
    "required": ["field_id"],
    "additionalProperties": false
  },
  "annotations": {"readOnlyHint": true}
}
```

此定义需要农场实际实现并通过 `tools/list` 返回，NEF 不会凭登记描述创造工具。只读标记也不能替代农场实现的权限与副作用控制。

### 6.3 查看将发布什么

`GET /api/v1/network/servers/{server_id}/publication` 只生成预览，不向网络写入。新协议正文为 `serverName/serverType/toolType/description/url/serverStatus` 六字段并带 isThirdParty=true，url 就是填写的外部 MCP 地址，不依赖 nef_base_url；固定值由服务端生成。

唯一契约、字段示例、GET 包装与确认规则见 [TRF MCP Server 契约](network-catalog.md)。旧 publish_url 部署的 NEF 代理登记格式仅保留兼容，不能发到新 MCP 集合接口。

### 6.4 发布与撤回

`POST /api/v1/network/servers/{server_id}/publish`，无正文，要求已发现至少一个工具；旧 `/sync` 为兼容别名。工具立即进入本地首页，再向 trf_mcp_servers_url POST 六字段及 isThirdParty=true，并 GET 读回确认。

| sync_status | 含义 |
|---|---|
| synced | 发布后基础字段读回匹配，GET 若带 isThirdParty 则须为 true；撤回后确认同名记录缺席 |
| submitted | 写请求已获成功 HTTP 响应，但尚无法读回确认 |
| pending | 已在本地发布，TRF 地址尚未配置 |
| failed | 配置、请求或响应格式错误；本地状态不伪装成远端成功 |
| not_required | 从未外发的记录已下架，或自助套餐只本地发布 |

`POST /api/v1/network/servers/{server_id}/unpublish` 本地下架并阻止新的 NEF 代理调用，随后向首次发布集合地址的 `/{serverName}` 发 DELETE（无正文）并 GET 确认。未知或失败可重复 unpublish 重试；对方 MCP 本身不会因此关闭。目标地址/名称在进程内锁定，配置改址不会让撤回误删新环境。

### 6.4.1 删除本地登记

`DELETE /api/v1/network/servers/{server_id}`。发现失败、草稿、确认撤回后的记录可删除，页面对应“删除记录”。已发布、繁忙或 TRF 撤回未确认返回 409，需先完成撤回。私有登记仅归属账号可删，open 登记可由具有 af:register scope 的其他账号管理。

自助套餐的 `/packages/{id}/publish`、`/unpublish` 在新协议下只更新本地展示，不发到 TRF MCP 集合。首页可用基础能力可通过独立的批量同步入口注册真实 NEF 单工具适配端点；场景不发送，详见 [首页同步](network-catalog.md#8-首页本地能力同步与-trf-读取模式)。

### 6.5 查看状态

```http
GET /api/v1/network/servers
```

返回 `{"servers":[...]}`，包含当前账号私有登记及所有 `registered_via:open` 登记。查看 `registration_status`、`discovery_status`、`publication_status`、`sync_status`、`tools`、`gateway_path` 和调用后的 `last_call`。不存在独立 `GET /servers/{id}` 接口；从列表按 `id` 选择。公开首页读取 `/api/v1/network/market`，仅包含已发布内容，不暴露来源账号和上游 URL。

消费端账号可在首页订阅发布的单个 MCP 工具，经北向 `/mcp` 使用；与下节网内代理的 network_clients 凭据分开。订阅/取消与准确 mcp_name 见 [第三方工具订阅](network-catalog.md#5-第三方工具的账号订阅与调用)。

## 7. 网络经 NEF 调用农场

由网络侧客户端操作，不是用农场账号 Key。选择独立 NEF 代理链路时，使用登记列表的 gateway_path 拼接 NEF Base URL，公网 Access 头仍必需。新 TRF 的 url 是外部 MCP 原始地址，直接访问它不经过下面的 NEF 代理鉴权：

```http
POST /api/v1/network/af-servers/{server_id}/mcp
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <独立网络调用Key>
CF-Access-Client-Id: <Client ID>
CF-Access-Client-Secret: <Client Secret>
```

按顺序发送以下 JSON：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"farm-network-test","version":"1.0"}}}
```

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_field_status","arguments":{"field_id":"F1"}}}
```

通知不带 `id`，NEF 返回 202；不能用通知形式执行工具。`tools/list` 读取该农场登记已发现的工具；不要改用 NEF 北向 `/mcp` 或旧 `/internal/mcp`，它们不是本条代理链路。

最终检查 HTTP 状态及 JSON-RPC 内容：

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {"type":"text","text":"<农场服务实际返回的内容>"}
    ],
    "isError": false
  }
}
```

NEF 保留农场实际 `CallToolResult`，不伪造业务完成。`isError=true` 是工具报告的业务错误，HTTP 200 不等于成功。返回 JSON-RPC `error` 时也算失败。

农场日志应看到 NEF 使用农场侧 Key，而不是账号 Key 或网络调用 Key。NEF 列表 `last_call` 应出现网络调用者、工具名、`via=NEF` 和 `status=returned` 或 `tool_error`。发生传输异常时可能是 `failed`，不能据此断定农场未执行；不要盲目重试有副作用操作。

## 8. 当前 MCP 兼容边界

这是当前代码支持范围，不宣称完整 MCP 协议符合性：

- 农场必须支持同一 HTTP URL 上的 JSON-RPC POST；协商版本固定为 `2025-03-26`，需声明 `capabilities.tools` 和合法 `serverInfo`。
- NEF 出向发送 `Accept: application/json, text/event-stream` 和 `MCP-Protocol-Version`；支持 JSON 或可在请求时限内读完的 SSE 响应，不支持无限长 SSE 推送流或旧式单独 SSE endpoint 握手。
- 农场初始化返回 `Mcp-Session-Id` 时，NEF 在该轮后续请求带回。实际 `tools/call` 会重新初始化一个会话，不承诺持久会话复用。
- 发现支持 `nextCursor` 分页，最多 1000 个工具。单次上游响应最多 1 MiB，单次上游 HTTP 请求总时限 10 秒；代理调用的整体操作时限 30 秒。
- 不跟随上游 HTTP 重定向，不继承系统代理环境；确保配置 URL 就是可直接调用的地址。
- 网内代理支持 initialize、ping、tools/list、tools/call 和通知受理；不实现 resources、prompts、动态订阅通知或完整会话生命周期。
- 参数按发现的 JSON Schema 校验；涉及外部 schema 引用的调用被拒绝，不替农场下载任意外部 schema。

## 9. 错误定位

| 响应 | 优先检查 |
|---|---|
| 302 / HTML | Access 机器凭据或浏览器登录；还未到 NEF |
| HTTP 401 | 是否用错/缺失 NEF Key 或独立网络 Key；重启后旧 Key 失效 |
| HTTP 403 | `af:register` scope 或农场 URL 不在允许列表 |
| HTTP 404 | 登记 ID 错误、不是当前账号的登记，或网络调用方无该 AF 账号权限 |
| HTTP 409 | 正在发现/同步/调用、未先发现工具，或达到登记数量上限 |
| HTTP 422 | 登记字段或请求格式错误 |
| HTTP 503 | 服务端配置缺失或无效；检查 `detail.code` |
| HTTP 502 / 504 | 上游协议、网络或响应异常 / 超时；查看固定 `detail.code`，不索取明文 Key |
| JSON-RPC `-32602` | 工具名或参数不符合已发现 schema |
| JSON-RPC `-32601` | 方法未实现 |
| JSON-RPC `-32001` | 农场代理忙，避免并发重复执行 |
| JSON-RPC `-32002` | 无法获得农场响应，实际执行结果可能未知 |

HTTP 错误通常为 `{"detail":{"code":"...","message":"..."}}`；NEF 账号认证错误的 `detail` 也可能是字符串。按 HTTP 状态及结构判断，不硬编码完整中文文案。此部署的 403 也可能来自 Cloudflare，先看返回是不是 NEF JSON。

## 10. 现场验收表

| 顺序 | 操作方 / 动作 | 必须看到的证据 |
|---|---|---|
| 1 | 农场后端带 Access 查询账号1 | HTTP 200 JSON，账号正确 |
| 2 | NEF 商城为1开通套餐；农场重查 | `purchased_packages` 出现对应详情；账号2不变 |
| 3 | 农场部署只读 MCP；NEF 配置允许列表 | 地址从 NEF 可达，Key 单独配置 |
| 4 | 农场用账号1 Key 登记 | 返回真实 server_id，source_account=1 |
| 5 | 调用 discover | discovered，工具名和参数与农场一致 |
| 6 | 查看 publication | 六字段及 isThirdParty=true；url 是登记的 MCP 地址，不含 Key |
| 7 | 调用 publish，TRF 读回确认 | synced；GET 中同 serverName 的基础字段匹配，若带 isThirdParty 则须为 true |
| 8 | 单独验收外部 MCP 直连或 NEF gateway_path | tools/list 与登记一致；只读 tools/call 返回实际数据 |
| 9 | 检查异常 | 错账号不能操作私有登记，开放登记可跨账号操作；错网络 Key 拒绝；参数错误不触发农场执行 |

每步记录时间、请求方法/路径、账号编号或登记 ID、状态码和脱敏响应；不要把任何 Key、客户现场数据写入共享截图或日志。步骤 1–2 可以先做，不依赖 MCP 服务或网络目录上线。

本地可重复预演：

```powershell
python -m pytest tests/test_farm_integration.py -q -s -p no:cacheprovider
```

此预演覆盖旧代理发布兼容链路并使用真实 TCP；新六字段契约用 `tests/test_trf_mcp_registry.py` 验证。但所有对端都在本机，农场结果明确 `data_source=mock`；不连接真实农场、不向生产目录发布、不修改现有 8069 账号状态。运行状态与测试记录见[运行手册](../demo-playbook.md#农场双向联调预演)。
