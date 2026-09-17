# 农场平台双向联调

分类：接口参考 / 联调流程。更新：2026-09-17。面向农场平台、NEF 和网络侧开发同事。

## 1. 本次范围

订购通知、补偿查询与双向 MCP 分别验收，不要求农场与 NEF 互通登录系统：

```text
订购：农场页面 --跳转并带账号编号--> NEF --POST subscriberId + servicePlan--> 农场后端
查询：农场平台后端 --账号编号--> NEF --已购套餐及详情--> 农场页面
开放：农场 MCP --> NEF 登记并发现工具 --> 网络目录接收 NEF 代理入口
调用：网络客户端 --> NEF 代理入口 --> 农场 MCP --> 原路返回结果
```

当天使用内存测试数据，重启后重新准备账号、订阅和 MCP 登记。换电脑首选 `python start.py`，地址为 `http://<NEF电脑IP>:8069`，无需旧域名或 Cloudflare 头；步骤见 [README](../../README.md#二换电脑启动与配置)。旧 Tunnel 部署仍可使用 `https://nef.2012wtlab.com` 和 Access。上传不会重启已有服务；真实农场回调地址和价格待提供。

真实农场 MCP 地址、鉴权和网络目录发布地址尚未提供。现有自动测试通过真实本地 TCP 验证完整流程，但农场和目录都是模拟对端，不代表生产网络已经接通。

本文维护 MCP 登记与双向联调流程；订阅响应的完整字段以[订阅查询接口](subscription-query.md)为唯一契约。场景执行与回传另见[场景接口说明](integration.md)。

## 2. 三方先交换什么

| 提供方 | 必须提供 |
|---|---|
| NEF | 公网地址、约定账号编号、Access 机器凭据；注册 MCP 时另提供该账号的 NEF Key |
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
| 农场登记 / 发现 / 发布自己的 MCP | `Bearer <账号1的NEF Key>`，需要 `af:register` scope |
| 网络客户端经 NEF 调用农场 | `Bearer <独立网络调用Key>`；不能用账号1的 NEF Key |
| NEF 连接农场 MCP | 运维设置的农场 Bearer Key，NEF 服务端读取 |
| NEF 向网络目录发布 | 运维设置的目录 Bearer Key，NEF 服务端读取 |

编号是数据定位符，不是授权凭据。只读查询通过共享 Access 入口后可查询其他约定演示编号；不将其用于生产租户数据。MCP 注册使用凭据确定 `source_account`，不接受请求体自报编号替代身份。

## 4. 第一条链路：订购通知与查询

农场按钮导航到 `http://<NEF电脑IP>:8069/?account_id=1`；使用旧公网域名时需通过 Access 登录。订购通知结构为 `subscriberId` + `servicePlan`，套餐包含 UUID、名称、描述和显式价格；默认勾选全部可用组成能力并附加 `networkCapabilities`。用户可缩小范围，全部取消才省略该字段并交给 PA 自主编排。NEF 不实现 PA/CA 决策，四字段平铺旧格式不再使用。

字段、选能力/不选能力两种完整示例、价格配置与重试见[套餐订购通知](subscription-query.md#10-跳转订购与套餐通知)。接收方需保留 subscriberId 归属并按事件头去重；HTTP 2xx 仅表示通知送达，业务入库响应待确认。浏览器跳转不要携带机器 Secret。

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
  "catalog_url": null,
  "publish_url": "https://directory.example.invalid/mcp-registrations",
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
| `catalog_url` | 网络能力目录拉取地址；本次只登记农场 MCP 时可为 null |
| `publish_url` | ARF/TRF 接收登记的完整 POST 地址，不是农场 MCP 地址；目前只支持一个接收端，不自动双发 |
| `token_env` | NEF 向目录发送 Bearer Key 所用环境变量名 |
| `nef_base_url` | 网络客户端能访问的 NEF 地址，发布时由此生成代理 URL |
| `mcp_servers` | 精确匹配登记 URL 的允许列表；页面登记不会自动加入允许列表 |
| `mcp_servers.<url>.token_env` | NEF 连接该农场 MCP 使用的 Bearer Key 环境变量名 |
| `network_clients` | 独立网络调用者配置；每个调用者绑定一个 Key 环境变量及允许的 AF 账号 |
| `af_accounts` | 精确允许访问的农场账号名，本例只允许 `1`，不是所有账号 |

只有确实无鉴权的获准测试对端才将 `token_env` 设为 null；配置了环境变量名但值缺失会失败，不自动降为匿名。当前出向认证配置只支持 Bearer，若农场或目录需要额外自定义头、OAuth 或 Cloudflare Access 头，应先对齐适配，不能声称任意鉴权都能直接用。

配置文件中的 URL 等变动会在相关请求时重新读取；启动时没有设置的进程环境变量，需要安排重启后才能生效。实际秘密不要写进 JSON、文档或登记请求。登记 URL 必须由 NEF 主机可达；农场电脑的 `127.0.0.1` 不是 NEF 可用地址。不要为联调关闭 Access、整个防火墙或允许任意出向 URL。

## 6. 第二条链路：农场 MCP 注册到网络

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
  "name": "农场管理平台",
  "url": "https://farm.example.invalid/mcp",
  "description": "提供获准测试地块的只读状态查询"
}
```

| 参数 | 必填 | 限制 |
|---|---|---|
| `name` | 是 | string，去除首尾空白后 1–128 字符 |
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

本接口没有幂等键，重复 POST 会生成不同登记；重试前先查列表。每账号最多 64 个登记，本版本没有登记删除接口。

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

```http
GET /api/v1/network/servers/{server_id}/publication
```

只生成发布内容预览，不向网络写入。要求配置 `nef_base_url`。检查：

- `type=mcp_server_registration`。
- `source=AF`、`source_account=1`、`registration_id` 为本次登记 ID。
- `server.url` 指向 `https://nef.2012wtlab.com/api/v1/network/af-servers/{server_id}/mcp`。
- `server.access_via=NEF`，`server.authentication=network-client-bearer`。
- `server.tools` 是刚发现的工具定义。

发布的是 NEF 代理入口，不是农场原始 URL；不包含任何 Key。农场登记、NEF 代理入口与网络目录条目共同保留该注册 ID，便于查错。

### 6.4 发布到网络目录

```http
POST /api/v1/network/servers/{server_id}/sync
```

无需请求体。NEF 向配置的 `publish_url` 发送 6.3 的发布 JSON，目录收到后必须确认：

```json
{"accepted": true}
```

| NEF 返回 | 含义 |
|---|---|
| HTTP 200，`accepted=true`，`sync_status=synced` | 目录明确确认接收 |
| HTTP 200，`accepted=false`，`sync_status=submitted` | 上游有成功 HTTP 响应，但未给出明确接收确认 |
| 503 | 发布地址或 NEF 网关配置缺失/无效 |
| 502 | 上游错误、超时、重定向或响应异常 |

`synced` 只证明收到目录确认，不证明目录已完成生产发布、网络已发现或调用成功。代码允许发现前先同步空工具登记，但本次验收要求**先发现工具再发布**。当前只配置一个发布 URL，不会自动分别发送到 TRF 与 ARF；网络侧接收适配由双方确认。

### 6.5 查看状态

```http
GET /api/v1/network/servers
```

返回 `{"servers":[...]}`，仅包含当前认证账号的登记。查看 `registration_status`、`discovery_status`、`sync_status`、`tools`、`gateway_path` 和调用后的 `last_call`。不存在独立 `GET /servers/{id}` 接口；从列表按 `id` 选择。

## 7. 网络经 NEF 调用农场

由网络侧客户端操作，不是用农场账号 Key。以发布内容中的 `server.url` 为目标，公网 Access 头仍必需：

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
| HTTP 502 | 上游协议、网络或响应异常；查看固定 `detail.code`，不索取明文 Key |
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
| 6 | 查看 publication | 只公布 NEF 代理 URL，不泄露农场地址/Key |
| 7 | 调用 sync，网络目录确认 | accepted=true、synced，目录侧能找到同一 registration_id |
| 8 | 网络客户端访问发布的 URL | tools/list 与登记一致；只读 tools/call 返回农场实际数据 |
| 9 | 检查异常 | 错账号不能操作登记；错网络 Key 拒绝；参数错误不触发农场执行 |

每步记录时间、请求方法/路径、账号编号或登记 ID、状态码和脱敏响应；不要把任何 Key、客户现场数据写入共享截图或日志。步骤 1–2 可以先做，不依赖 MCP 服务或网络目录上线。

本地可重复预演：

```powershell
python -m pytest tests/test_farm_integration.py -q -s -p no:cacheprovider
```

预演覆盖两条链路并使用真实 TCP，但所有对端都在本机，农场结果明确 `data_source=mock`；不连接真实农场、不向生产目录发布、不修改现有 8069 账号状态。运行状态与测试记录见[运行手册](../demo-playbook.md#农场双向联调预演)。
