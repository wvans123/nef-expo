# TRF MCP Server 契约与能力映射

分类：接口参考。更新：2026-09-21。字段和路径按本次联调约定实现；真实 IP、鉴权及 GET 完整回包尚待提供。目前仅验证本地模拟对端。

## 1. 服务、工具、能力和套餐

| 对象 | 当前归属与展示 |
|---|---|
| NF 能力 | NEF 的能力模型与 API / Tool 映射；NF 不必实现 MCP Server，首页现有能力卡不改成服务器卡 |
| MCP Server | TRF 登记服务名、描述、地址和类型；server description 描述服务，不能替代工具参数与调用定义 |
| MCP tool | 从获准服务的 `tools/list` 实际发现；显式发布后才上首页，保留所属 `serverName`，按 `toolType` 分类 |
| 场景 / 自助套餐 | NEF 管理能力组合、价格和权益；不发到 MCP Server 集合接口。已购套餐仍按原契约通知农场 |

TRF 四类为 `nf tool`、`computing tool`、`sensing tool`、`third-party tool`。当前外部接入固定最后一类；查询到其他三类只作运维信息，不会自动成为可调用工具或进入编排能力池。

若以后要让 TRF 发现 NEF 已包装的基础工具，可以另行登记一个真实 NEF MCP 服务，再由消费者发现其工具；必须先确定服务身份、toolType、认证和公开范围。不能把每个 NF description 或套餐虚构成 MCP Server。本轮不自动登记 NEF 自身或导出旧套餐。

## 2. 页面和配置

双向开放只填服务名称（`serverName`）、描述（`description`）、MCP 地址（`url`）。默认名称 `patrol-car-managementx`，描述为巡检任务、预检测开关、图像采样频率管理，URL 留空。名称最长 128 字符，匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，本进程内不可与其他登记重名。

表单“连接并发现工具”负责首次登记、握手、读取工具；已有记录的“重新发现工具”只重读该服务的工具，需先取消发布再操作；发现失败也保留“删除记录”。点击“发布”才上首页并发给 TRF；“取消发布”先本地下架，再撤回远端。远端撤回尚未确认时保留记录与重试入口，不能直接删除而丢失撤回信息。

普通页面隐藏 TRF 管理。`/?ops=1#afreg` 中“TRF 服务登记 · 运维”可手动查询四类服务；此参数只是显示开关，接口仍要求账号 Key 与 `af:register` scope。页面的 30 秒本地刷新不自动请求 TRF。

只改 `config/integration.local.json` 中的 `registry`：

```json
{
  "trf_mcp_servers_url": "http://<TRF-IP>:<端口>/trf/api/v1/mcp-servers",
  "token_env": null,
  "mcp_servers": {"http://<巡检小车IP>:<端口>/mcp": {}}
}
```

这是 registry 子对象片段，不要覆盖整个统一配置。一个集合地址用于 GET、POST 以及追加 serverName 的 DELETE；未取得地址时保留 null，不填占位 IP。`mcp_servers` 是精确 URL 允许列表，表单登记不会自动授权。认证如需 Bearer，`token_env` 填服务端环境变量名，不写密钥值。

新协议发布原始 MCP 地址，TRF 消费者可能直接访问它；现有 NEF 代理入口仍独立保留，但不会偷偷替换这次约定的 url。取消发布会关闭 NEF 展示和新代理调用，不会关闭外部 MCP 服务本身。

## 3. NEF 发给 TRF

### 发布

`POST {trf_mcp_servers_url}`，`Content-Type: application/json`，严格六字段：

```json
{
  "serverName": "patrol-car-managementx",
  "serverType": "Streamable HTTP",
  "toolType": "third-party tool",
  "description": "管理巡检小车，如在巡检小车上启动或关闭巡检任务、配置目标预检测开关、图像采样频率等。",
  "url": "http://<巡检小车IP>:<端口>/mcp",
  "serverStatus": "active"
}
```

`serverType` 按更正后的枚举发送 `Streamable HTTP`，由 `_trf_publication()` 生成。三项固定值由后端生成，前端不能覆盖。不附加工具数组、source_account、NEF Key 或套餐字段。

### 查询与确认

`GET {trf_mcp_servers_url}`，无正文。目前支持完整数组、单字段 `{"items":[...]}` 或 `{"data":[...]}`，每项包含六字段；额外项字段会从 NEF 投影中去掉。分页或其他外层结构尚未约定，返回明确的 schema 错误，不把未知结构当空列表。

发布的 HTTP 2xx 不直接等于同步成功：随后 GET，读回六字段一致的记录才记 `synced`；查不到匹配项或查询暂不可用记 `submitted`，请求或 schema 错误按实际记录。GET 读取确认不证明后续工具可执行。

### 撤回

`DELETE {首次发布集合地址}/{serverName}`，无请求体。随后 GET 确认同名记录缺席才记 `synced`；DELETE 返回 404 也会读回确认。失败或仍存在时保留撤回责任并可重试。

首次发布的地址及名称保存在进程内；配置改址后该记录仍在原目标重试 / 撤回，避免删除新环境的同名服务。确认撤回后可删除本地登记，再用新配置重新登记。超时可能已经到达对端，不自动声称未发送；当前没有对方幂等规则，重试需核对实际记录。

所有请求不走系统代理、不跟随重定向。登记与状态目前仍在内存，重启会清空；重启前应撤回本进程发布的登记，或由对方按 serverName 清理，NEF 不会在重启后自动猜测并删除 TRF 记录。

## 4. 页面调用 NEF 的接口

均需 `Authorization: Bearer <NEF账号Key>` 与 `af:register` scope，公开市场除外。

| 方法 / 路径 | 正文与行为 |
|---|---|
| POST `/api/v1/network/servers` | `{serverName,description,url}`；只保存；旧 `name` 保留兼容 |
| POST `/api/v1/network/servers/{id}/discover` | 无正文；连接允许列表地址并发现工具 |
| GET `/api/v1/network/servers/{id}/publication` | 预览六字段，不外发；新协议无需 nef_base_url |
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
3. 发布后核对 TRF 六字段记录、首页工具来源；取消后核对 DELETE 与 GET 缺席，最后删除本地记录。
4. 真实工具调用单独验收；查询 TRF 不授予订阅或执行权限。

`tests/test_trf_mcp_registry.py` 覆盖 HTTP 契约和失败边界；`tests/test_integration_ui.cjs` 与 `tests/test_catalog_ui.cjs` 在 `tests/workbench_fixture.py --port 8071` 隔离服务上验证桌面/手机页面，后者现在验证运维查询而非旧目录导出。截图在忽略上传的 `.runtime/` 中。测试不访问真实 TRF 或正式 8069 账号。

账号订阅验收由 `tests/test_market_subscriptions.py` 与 `tests/test_market_subscriptions_ui.cjs` 覆盖：三个账号隔离、订阅/取消、两个 MCP 入口、真实本地 AF 回执、下架和删除；后者同样只用隔离测试端口。
