# 套餐订购通知与订阅查询

分类：接口参考。协议版本：1.1。更新：2026-09-22。

交付状态：代码包含 1.1 查询与第 10 节订购通知，通知通过本地模拟对端验证，真实农场接收仍待联调。换电脑按 [README](../../README.md#二换电脑启动与配置) 运行 `python start.py` 并填写统一配置。上传 GitHub 本身不会重启任何进程；本机单独重启与验收记录见运行手册，不是新机器预置账号或交付保证。

**当前主流程：农场页面跳转 NEF → 按约定编号订购 → NEF 服务端 POST 套餐给农场。** 跳转和通知契约见[第 10 节](#10-跳转订购与套餐通知)。下面的 GET 查询保留作首次加载、刷新与补偿查询，响应版本仍为 1.1。

面向另一个应用的开发同事：查询 NEF 演示账号已订阅的工具、套餐与场景，构建“我的工具”界面。无需与 NEF 互通登录账号；双方约定同一个账号编号即可。此接口只查询，不注册、不开通、不扣费，也不返回任何调用凭据。

**农场平台主要读取 `purchased_packages` 即可展示“已购网络套餐 + 详情”**，不需要自行把工具拼成套餐。1.1 以兼容追加方式提供该字段，原有字段仍保留。农场 MCP 登记与网络调用的实际联调步骤见[农场平台联调](farm-integration.md)。

## 1. 接口信息

| 项目 | 约定 |
|---|---|
| 接口名称 | 查询指定演示账号的订阅 |
| HTTP 方法 | `GET` |
| 路径 | `/api/v1/integration/subscriptions` |
| 公网 Base URL | `https://nef.2012wtlab.com` |
| 公网完整示例 | `https://nef.2012wtlab.com/api/v1/integration/subscriptions?account_id=1` |
| 本机 Base URL | `http://127.0.0.1:8069`，仅 NEF 所在电脑可用 |
| 内网 Base URL | `http://<NEF电脑IP>:8069`，换电脑联调首选，不依赖旧域名 |
| 请求体 | 无 |
| 成功响应 | HTTP 200，`application/json`，UTF-8 |
| 缓存 | `Cache-Control: no-store` |
| OpenAPI | `GET /openapi.json`，响应模型 `SubscriptionSnapshot`；公网同样受 Access 保护 |
| 查询作用范围 | 当前 NEF 服务进程中的演示账号与订阅 |

`python start.py` 默认监听 `0.0.0.0:8069`，另一台电脑填写 NEF 网卡 IP，不使用 `127.0.0.1` 或 `0.0.0.0` 作为请求地址。

## 2. 账号编号与初始化

`account_id` 是 **NEF 注册账号的精确名称**，不是数组下标、注册顺序、自动生成编号、API Key 或对方系统登录 ID。

联调前，NEF 操作员在页面“注册账号”中分别填写 `1`、`2`、`3`，选择对应账号并在商城完成订阅。对方应用将自己的用户映射到这些约定编号，查询时传相同字符串即可。

| 对方约定编号 | NEF 注册账号名 | 查询参数 |
|---|---|---|
| 1 | `1` | `account_id=1` |
| 2 | `2` | `account_id=2` |
| 3 | `3` | `account_id=3` |

原有名为 `alice` 的账号可以直接传 `account_id=alice`，不会自动映射到编号 `1`。`1` 和 `01` 不同，英文字母大小写有区别。不存在的编号返回 404，不会自动创建账号或代替它查第一个账号。

**存储说明：** 订阅数据存于 `server.py` 的 `API_KEYS` 账号记录；`ACCOUNT_KEYS` 将账号名映射到该记录。记录中的 `subscriptions`、`packages`、`scene_subscriptions` 和 `plan` 分别维护直订、旧套餐、场景及等级。第三方 MCP 工具的账号订阅另存于 network_registry.py 的内存状态，查询统一汇总至 external_tool_subscriptions。浏览器只保存演示账号凭据，不是订阅数据源。当前没有数据库持久化；NEF 重启后，须重新注册相同编号并恢复订阅。未恢复账号时查询返回 404，重新注册但未订阅时返回 200 空列表。

不要在联调中途重启 NEF；不要使用多 worker 部署，因为各进程内存不共享。场景套餐支持取消开通及对端 DELETE 通知，详见第 10 节；原子能力和旧基础套餐仍无取消接口。此版本没有订阅有效期或订阅查询增量游标。代码支持单套餐订购 / 取消通知和手动重试，不是完整订阅变更事件流。

## 3. 请求头

| Header | 公网必填 | 说明 |
|---|---|---|
| `CF-Access-Client-Id` | 是 | NEF 方单独交付的机器凭据 Client ID |
| `CF-Access-Client-Secret` | 是 | NEF 方单独交付的机器凭据 Secret |
| `Accept` | 否 | 建议 `application/json` |
| `Authorization` | 否 | 本查询接口不需要 NEF 账号 Key；不要传模型 Key 或场景回传 Key |

内网直连无需 Cloudflare 请求头。编号只用于定位数据，不是认证凭据；能访问内网查询接口的客户端可查询任意已知演示编号。旧公网入口仍由 Cloudflare Access 保护。**两种部署均不是按用户隔离的生产授权接口。** 只使用测试账号与测试订阅；正式多租户接入必须另加调用方身份与账号范围校验。

请从对方应用后端调用，将 Access 凭据放在服务端环境变量。不要在浏览器前端嵌入机器 Secret；本次未新增跨域 CORS 放行。浏览器正常登录 NEF 后也可凭已有会话访问，但不作为后端机器调用的替代方式。

## 4. Query 参数

| 参数 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| `account_id` | string | 是 | 1–128 字符；首尾不得为空白；与 NEF 账号名精确匹配；非数字名称须 URL 编码 | `1` |

不要重复传多个同名参数，不要通过 JSON 请求体传账号编号。

```http
GET /api/v1/integration/subscriptions?account_id=1 HTTP/1.1
Host: nef.2012wtlab.com
Accept: application/json
CF-Access-Client-Id: <单独交付>
CF-Access-Client-Secret: <单独交付>
```

## 5. 响应字段

所有顶层字段都会返回；无数据时数组为 `[]`，不返回 `null`。嵌套场景的 `tool` 和已购套餐的 `intent_example` / `tool` 允许为 `null`。

| 字段 | 类型 | 含义 |
|---|---|---|
| `schema_version` | string | 当前 `1.1` |
| `account_id` | string | 本次查询匹配的 NEF 账号名 |
| `generated_at` | string | 本次快照生成时间，ISO 8601 UTC；不是订阅最后变更时间 |
| `storage` | string | 固定 `memory`，说明重启不会保留 |
| `plan` | string | `free` / `pro` / `max` |
| `direct_subscriptions` | string[] | 单独订阅的基础或已注册第三方能力 ID |
| `subscribed_capabilities` | string[] | 直接订阅、旧套餐包含能力及已购场景所选子能力的并集；不含纯等级赠送 |
| `entitled_capabilities` | string[] | 已开放且被直订、旧套餐、场景所选子能力或等级覆盖的原子能力 ID；与 `tools[].capability_id` 一致 |
| `packages` | object[] | 旧能力套餐，结构见下表 |
| `scene_subscriptions` | string[] | 独立开通的场景服务 ID |
| `tools` | object[] | 可供“我的工具”展示的原子工具及参数定义；不混入未订阅的按次付费工具 |
| `scene_services` | object[] | 已开通场景、内部组成和其支持的入口 |
| `external_tool_subscriptions` | object[] | 已订阅第三方 MCP 工具；含 available 可用标志和准确 mcp_name，不混入 purchased_packages |
| `purchased_packages` | object[] | 农场平台首选：合并已购场景套餐和旧能力套餐的详情；不包含未购商品、纯等级赠送能力或编排草稿 |

### purchased_packages 每项

| 字段 | 类型 | 含义 |
|---|---|---|
| `kind` | string | `scene`：场景服务；`capability_package`：旧原子能力组合套餐 |
| `id` | string | 套餐或场景 ID；以 `(kind, id)` 共同作为列表键，不能只按 id 去重 |
| `name` | string | 套餐名称 |
| `description` | string | 当前目录中的套餐说明，不是实时执行结果 |
| `components` | object[] | `{capability_id, name, standalone_entitled}`；展示组成能力以及是否具备独立调用权益 |
| `modes` | string[] | 场景实际支持的 `intent/api/tool` 入口；旧能力套餐为 `[]`，不在本接口宣称它有场景执行入口 |
| `intent_example` | string 或 null | 场景的意图请求示例；旧能力套餐为 null |
| `tool` | object 或 null | 支持 Tool 的场景定义 `{name, description, inputSchema}`；其他为 null |

此处“已购”指演示账号已开通的权益，不表示真实支付成功，也没有订单号或到期日。网络目录中的未购套餐和自助编排保存的定义不进入此列表；TRF 查询记录没有购买接口，不能把同步目录当成已经购买；显式发布的第三方 MCP 工具支持独立演示订阅，记录在 external_tool_subscriptions。场景开通时勾选的子能力同时获得独立调用权益；未选组件仍可作为套餐设计信息展示，其 `standalone_entitled` 由其他有效权益决定。

### external_tool_subscriptions 每项

`id` 是 serverId:toolName，另含 `server_id/serverName/name/description/inputSchema/mcp_name/toolType/price/billing/available`。`mcp_name` 是经 NEF `/mcp` 调用的准确名称，不应以原工具 name 替代。没有订阅返回 []；提供方下架后保留记录但 available=false，删除登记清理记录。当前 price=0、billing=demo_free，不增加估算月费。

此字段按查询的精确账号独立返回，不携带上游 URL、来源账号或密钥；无 Key 编号查询仍仅供获准演示网，调用必须另带本账号 Key 与有效订阅。订阅/取消的唯一接口契约见 [第三方工具订阅](network-catalog.md#5-第三方工具的账号订阅与调用)，该操作不触发农场套餐通知或 TRF 发布。

### tools 每项

| 字段 | 类型 | 含义 |
|---|---|---|
| `capability_id` | string | 稳定能力 ID |
| `name` | string | MCP `tools/call` 使用的准确工具名；原子工具与能力 ID 相同 |
| `display_name` | string | 页面显示名称 |
| `description` | string | 工具说明 |
| `inputSchema` | object | JSON Schema 参数定义，与本工具 MCP 定义同源；不是实际参数值 |
| `grant_sources` | string[] | 权益来源，可同时包含 `direct`、`package:<套餐ID>`、`scene:<场景ID>`、`plan:<等级>` |

例如同一能力既单独订阅又在套餐中，只返回一个工具，`grant_sources` 保留两个来源。想展示“我单独买的工具”，取 `direct_subscriptions`；想展示“订阅或等级包含的工具”，取 `tools`。

页面带 Key 的 `GET /api/v1/auth/info` 同时返回 `capability_grant_sources`（能力 ID → 直订/旧套餐/场景来源数组），首页据此展示“套餐已包含”及具体场景名。等级覆盖仍通过 `entitled_capabilities` 和 plan 字段判定。关联权益从已购记录派生，不向 `direct_subscriptions` 写入副本，因此撤回一个场景不会误删其他来源。

### packages 每项

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | string | 旧能力套餐 ID |
| `name` | string | 套餐名称 |
| `capability_ids` | string[] | 套餐包含的原子能力 |

### scene_services 每项

| 字段 | 类型 | 含义 |
|---|---|---|
| `service_id` | string | 场景 ID |
| `name` | string | 场景名称 |
| `modes` | string[] | 支持 `intent`、`api`、`tool` 中哪些入口 |
| `components` | object[] | `{capability_id, name, standalone_entitled}`；最后一项为 boolean，表示该组件能否作为独立工具获得订阅或等级覆盖 |
| `tool` | object 或 null | 支持 Tool 的场景返回 `{name, description, inputSchema}`；仅 Intent 场景返回 `null` |

当前三场景为 `robot_patrol`、`traffic_flow_detection`、`collaborative_tracking`。只有端网协同场景另有 Tool，准确名称为 `scene_collaborative_tracking`。

**场景与组件规则：** 开通场景时按购买选择同步授予子能力权益，API / MCP 的独立调用也使用这些权益，不必再逐项订阅。只选部分能力时只授权所选项；省略选择按默认全选，显式空数组只开通场景入口。取消场景或减少选择会撤回相应来源，保留单独订阅、其他套餐或等级仍覆盖的能力；不会因为子能力可用而开通其他场景入口。实际设备、数据和内部资源权限仍由执行方检查。

旧 `packages` 和新 `scene_services` 不是同一种权益，即使某个 ID 都叫 `robot_patrol` 也不能合并。自助编排保存的套餐定义、导入的网络目录和 AF MCP Server 登记不是订阅，本接口不将它们作为已订阅工具返回。旧 `scenario_*` / `pipeline_*` 包装工具也不包含在本接口的原子 `tools` 数组中。

## 6. 完整成功示例

前置条件：当前进程注册了账号 `1`，等级为 free，仅单独订阅 `target_detection`，无套餐或场景订阅。时间仅为示例，不代表当前账号的真实业务数据。

```json
{
  "schema_version": "1.1",
  "account_id": "1",
  "generated_at": "2026-09-17T02:00:00+00:00",
  "storage": "memory",
  "plan": "free",
  "direct_subscriptions": ["target_detection"],
  "subscribed_capabilities": ["target_detection"],
  "entitled_capabilities": ["target_detection"],
  "packages": [],
  "scene_subscriptions": [],
  "tools": [
    {
      "capability_id": "target_detection",
      "name": "target_detection",
      "display_name": "目标检测",
      "description": "[目标检测] 检测指定区域内的物体（人、车辆、无人机等），返回目标类型、位置和置信度",
      "inputSchema": {
        "type": "object",
        "properties": {
          "area": {"type": "string", "description": "检测区域标识或坐标范围"},
          "object_types": {
            "type": "array",
            "description": "关注的目标类型，如 person/vehicle/uav",
            "default": ["person", "vehicle", "uav"]
          },
          "sensitivity": {
            "type": "string",
            "description": "检测灵敏度",
            "enum": ["low", "medium", "high"],
            "default": "medium"
          }
        },
        "required": ["area"]
      },
      "grant_sources": ["direct"]
    }
  ],
  "scene_services": [],
  "purchased_packages": [],
  "external_tool_subscriptions": []
}
```

查询返回订阅快照，不发起模型或业务调用。有权益不保证网络执行接口已配置、入口 scope 允许、资源足够或实际任务成功。真正调用仍需原 NEF 账号凭据并由执行接口重新鉴权；查询编号不能替代调用凭据。

## 7. 错误与处理

| HTTP 状态 | 来源 / 含义 | 处理方式 |
|---|---|---|
| 200 | 查询成功；数组可能为空 | 以响应内容为准 |
| 302 或 HTML 登录页 | Cloudflare Access 尚未通过 | 检查机器凭据；不要当成后端成功 |
| 403 | 可能为入口策略拒绝 | 检查 Access 策略或 Cloudflare 响应，不解释为账号无订阅 |
| 404 + `account_not_found` | 当前 NEF 进程未注册此账号 | 核对编号，或重启后重新注册 |
| 404 + 其他正文 | 路径不对或运行中的服务尚未加载新接口 | 检查路径与版本 |
| 422 | 缺少参数、空白或超长账号名 | 修正请求 |
| 405 | 使用了 POST 等错误方法 | 改用 GET |
| 5xx / 超时 | 服务、Tunnel 或网关异常 | 保留之前展示但标为未更新，稍后重试 |

未知账号：

```json
{
  "detail": {
    "code": "account_not_found",
    "message": "该账号尚未在当前 NEF 服务中注册"
  }
}
```

422 使用 FastAPI 的 `detail` 数组，包含 `loc`、`msg`、`type` 等；例如缺少账号时 `loc` 为 `["query", "account_id"]`。不要依赖整段错误文案做业务判断。

## 8. 调用示例

### curl

在对方后端机器预先安全设置 Access 环境变量；不需要 NEF 账号 Key。不使用 `-L` 自动跟随登录跳转。

```bash
curl --get "https://nef.2012wtlab.com/api/v1/integration/subscriptions" \
  --data-urlencode "account_id=1" \
  --header "Accept: application/json" \
  --header "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  --header "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  --connect-timeout 5 --max-time 10 --include
```

### Python / httpx

```python
import os
import httpx

response = httpx.get(
    "https://nef.2012wtlab.com/api/v1/integration/subscriptions",
    params={"account_id": "1"},
    headers={
        "Accept": "application/json",
        "CF-Access-Client-Id": os.environ["CF_ACCESS_CLIENT_ID"],
        "CF-Access-Client-Secret": os.environ["CF_ACCESS_CLIENT_SECRET"],
    },
    timeout=10,
    follow_redirects=False,
)
if response.status_code != 200:
    raise RuntimeError(f"NEF query failed: HTTP {response.status_code}")
if "application/json" not in response.headers.get("content-type", ""):
    raise RuntimeError("NEF did not return JSON; check Access authentication")
snapshot = response.json()
for tool in snapshot["tools"]:
    print(tool["name"], tool["display_name"], tool["grant_sources"])
```

## 9. 联调验收与刷新

1. NEF 操作员注册约定账号 `1`，对方查询得到 200 和空数组。
2. NEF 为 `1` 单独订阅一个工具，对方重新查询，核对 `tools` 与 `direct_subscriptions`。
3. 对方查询 `2`：若已注册但未订阅，应为空；若未注册，应为 404，不可返回 `1` 的数据。
4. NEF 为 `1` 开通场景，核对所选组件进入 `tools`、带 `scene:<id>` 来源且 `standalone_entitled=true`；未选项不被这个场景授权。取消后只移除该场景来源，其他来源保留。
5. 检查响应无 API Key、Access Secret、回传 Key；无 Access 凭据的公网请求不能取得订阅快照。
6. 另行验收真正的工具调用或场景回传，不用查询成功替代业务验收。

建议进入页面及订阅完成后查询；需要持续刷新时每 10–30 秒查询一次。错误不当作空订阅覆盖界面。接口只读，可有限重试网络错误和 5xx；建议最多 3 次并采用递增等待，不对 302、404、422 无限重试。订购通知见下节，不承诺实时性、可靠消息队列或生产 SLA。

当前验证记录、运行端口及是否已重启加载新接口，以[运行手册](../demo-playbook.md#订阅查询联调)为准。本文是请求/响应契约的唯一维护文档。

## 10. 跳转订购与套餐通知

### 10.1 跳转入口

农场页面按钮直接导航至 `http://<NEF电脑IP>:8069/?account_id=1`；旧 Tunnel 部署可用 `https://nef.2012wtlab.com/?account_id=1`。编号 `1` 可替换为约定的 `2`、`3`；此跳转只接受一项 `account_id`，值为 1–32 位数字字符串。页面接入或切换到对应演示账号，然后由用户选择套餐并点击开通，不因访问链接就自动购买。无该参数时保持原账号操作流程。

只有旧公网跳转经过 Cloudflare Access 登录，内网直连不需要。机器 Access Secret 不能放进跳转 URL 或浏览器代码。本次没有放宽 Access 策略。账号编号不是身份认证，不能将这种自助演示账号用于生产。

回调目的地只由 NEF 服务端运维配置；URL 查询参数中的 `callback_url` 等不生效，避免浏览器把订购信息发送到任意地址。当前没有订购完成后自动跳回农场页面的约定。

### 10.2 NEF 向农场发送

| 项目 | 约定 |
|---|---|
| 方向 | NEF 服务端 → 农场平台服务端 |
| 方法 | `POST` |
| URL | `http://<实际IP:端口>/business/v1/service-plans`；实际协议、IP 和端口由农场提供 |
| Content-Type | `application/json` |
| 触发 | 场景开通或旧能力套餐订阅成功后；一次请求发送一个套餐 |
| 非触发项 | 单独订阅原子工具、模型推荐、保存编排草稿、导入网络目录 |
| 鉴权 | 待确认；支持运维配置服务端 Bearer 环境变量，不复用 NEF 用户 Key 或模型 Key |
| 重定向 | 不跟随；3xx 视作通知失败 |

请求体为 `subscriberId` + `servicePlan`，不再发送旧版四字段平铺结构。按本次联调约定，外发 `subscriberId` 固定为 `"subscriber-001"`；本地账号 `1/2/3`、查询参数 `account_id` 和通知访问权限保持不变，无需修改跳转链接或配置中的 `account_ids`。这意味着不同本地账号的通知在农场侧均属于同一个测试订购者，不用于验证多用户隔离。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `subscriberId` | string | 是 | 固定 `"subscriber-001"`，服务端设置，不取本地账号编号或浏览器传值 |
| `servicePlan` | object | 是 | 本次订购的套餐 |
| `servicePlan.planId` | string (UUID) | 是 | 服务套餐标识；同一套餐跨账号、跨重启稳定，不是订单 ID |
| `servicePlan.showName` | string | 是 | 套餐名称，取 NEF 当前目录 |
| `servicePlan.description` | string | 是 | 套餐描述，取 NEF 当前目录 |
| `servicePlan.price` | number (float) | 是 | 所选能力总价 × discount，保留两位小数；无 discount 时取 plan_prices；必须非负有限数值 |
| `servicePlan.networkCapabilities` | object[] | 否 | 默认附带全部可用能力，页面至少选一项；后端兼容空选择并省略字段，不传 null 或空数组 |

每个 `networkCapabilities` 元素：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `capabilityName` | string | 是 | 能力池稳定标识，如 `target_detection`；作为机器匹配名称，不使用易变中文名 |
| `showName` | string | 是 | 中文展示名，如“目标检测” |
| `description` | string | 是 | 该网络能力的描述，来自同一能力池 |
| `price` | number (float) | 否 | 本版发送能力目录单价的数字部分，例如 `19.9/月` 转成 `19.9`；免费能力为 0 |

**编排语义：** 存在 `networkCapabilities` 时，网络内部 Planning Agent（PA）与 Computing Agent（CA）应在该列表范围内编排；不存在时交给 PA 自主选择能力。NEF 只传套餐和约束，不实现 PA 自主编排，也不声明已经完成 PA/CA 对这些约束的接收或执行验证。列表不是有序执行步骤，不发送整个能力池替代所选项。

以下示例只选择目标检测，按当前模板 8 折计价为 `15.92`，原子能力单价 `19.9`：

```http
POST /business/v1/service-plans HTTP/1.1
Host: <实际IP:端口>
Content-Type: application/json
Idempotency-Key: sub_<本次通知标识>
X-NEF-Event-ID: sub_<本次通知标识>
```

```json
{
  "subscriberId": "subscriber-001",
  "servicePlan": {
    "planId": "36b3d800-2774-5e2d-a647-c26194fba4ae",
    "showName": "机器狗巡检",
    "description": "巡检任务下发、异常信息与巡检结果回传。",
    "price": 15.92,
    "networkCapabilities": [
      {
        "capabilityName": "target_detection",
        "showName": "目标检测",
        "description": "检测指定区域内的目标。",
        "price": 19.9
      }
    ]
  }
}
```

示例 UUID 对应场景 `robot_patrol`，能力描述为简写；实际正文来自目录。UUID 规则为 Python `uuid5(NAMESPACE_URL, "urn:nef:service-plan:" + kind + ":" + id)`，其中 `kind` 是查询响应中的 `scene` 或 `capability_package`。因此同名旧套餐和新场景不会撞号。`planId` 标识套餐模板，不随用户所选范围改变；接收方将本次选择归入固定测试订购者 `subscriber-001`，并按事件头去重。同一套餐从不同本地账号购买仍属于该测试订购者，需按双方业务约定处理更新。GET 查询仍按本地账号返回内部 `kind/id`，不含价格或本次通知的能力选择。

旧接口仍兼容显式空能力选择，页面现在要求至少一项。以下为未配置 discount 且固定 plan_prices 为 19.9 的兼容请求；配置折扣时空选择价格为 0，同一订购者无需另加账号头：

```json
{
  "subscriberId": "subscriber-001",
  "servicePlan": {
    "planId": "36b3d800-2774-5e2d-a647-c26194fba4ae",
    "showName": "机器狗巡检",
    "description": "巡检任务下发、异常信息与巡检结果回传。",
    "price": 19.9
  }
}
```

订购弹窗提供当前套餐内的可用网络能力复选框，默认全部勾选，页面至少保留一项，并按选择实时重算报价。开通完成后留在当前页；只有主动点击“进入场景”才进入意图受理。所选项既作为交给网络侧的范围约束，也作为本地原子工具的套餐权益来源；不改变场景执行实现。首页及能力详情显示“套餐已包含”，不再提示重复购买。

页面调用 NEF 的场景订购接口可带 `{"network_capability_ids":["target_detection"]}`；省略请求体或传 `{}` 默认发送套餐能力组合，只有显式 `{"network_capability_ids":[]}` 表示不限定范围。仅接受当前套餐已开放的能力 ID，重复、未知或越出套餐的能力返回 422，且不产生订购。NEF 仍从认证账号确认本地权益和通知归属，但外发 `subscriberId` 使用固定值；不接受场景请求体覆盖该字段。

旧 `POST /api/v1/subscribe` 同样支持 `network_capability_ids`，但非空选择时要求 `package_ids` 只有一个套餐，避免把不同套餐的范围混在一起。旧接口的演示账号身份规则未升级为生产认证。

### 10.3 NEF 服务端配置

新部署只改 `config/integration.local.json` 的 `subscriptions` 对象。`start.py` 自动从 `config/integration.example.json` 创建文件；每次发送或重试重新读取。将下面对象填在 `subscriptions` 内，不要覆盖其余 `bridge` / `registry`。真实 URL、价格、鉴权需由双方填写，模板默认不发送套餐通知。

```json
{
  "callback_url": "http://<实际IP:端口>/business/v1/service-plans",
  "token_env": null,
  "account_ids": null,
  "notify_plans": null,
  "discount": 0.8,
  "reset_partner_plans_on_start": false,
  "plan_prices": {
    "scene:robot_patrol": 19.9
  }
}
```

`account_ids=null` 允许所有本地账号通知；数组仅允许指定账号，空数组不发送。`notify_plans=null` 通知所有套餐；数组按完整价格键限制，例如 `["scene:collaborative_tracking"]`。旧套餐键为 `capability_package:<内部套餐ID>`。

`discount` 必须为有限数且 `0<d<=1`，配置后价格为所选能力目录单价之和乘折扣，四舍五入保留两位。全选月价：机器狗 115.68、车流量 119.76、端网协同 119.6。`GET /api/v1/services` 返回全选 `price` 和 `discount`；不配置折扣时回退 `plan_prices`，缺失固定价格则 `price_not_configured`，不自动报价为零。

“订阅与鉴权”的估算月费用来自 `GET /api/v1/auth/info` 的 `estimated_monthly_cost`：等级基础月费（FREE 0、PRO 99、MAX 299）加未被覆盖的单项包月订阅、旧能力套餐固定价和已开通场景的购买价。单项能力已被等级、旧能力套餐或已购场景所选能力覆盖时不重复计费；场景包含的子能力不额外收单项月费。取消场景后，原本独立订阅且不再被其他权益覆盖的能力恢复其单项月费。场景在开通时保存所选能力的报价，之后修改折扣不会改写已购金额，取消后移除该项。例如只选目标检测、八折时场景价为 15.92，FREE 合计 15.92、PRO 合计 114.92、MAX 合计 314.92（无其他订阅时）。按次消费另列，不计入固定月费；这些是演示估算，不执行真实扣费。

带凭证的非回环地址必须用 HTTPS；当天获准局域网测试可配置不带凭证的 HTTP，仍会明文发送套餐和 `subscriberId`。地址不允许内嵌用户名/密码、query 或 fragment。不从浏览器传入地址或密钥，不修改现有 Tunnel。

兼容旧部署：`NEF_SUBSCRIPTION_CONFIG` 显式指定的独立文件优先；没有统一文件时仍读取 `config/subscription.local.json`，其结构模板为 `config/subscription.example.json`。新部署不必设置这些旧路径。修改 JSON 无需重启；更新 Python 或新增进程环境变量需安排重启，重启清空内存账号和 Key，勿在同事测试中途操作。

### 10.4 响应、失败与重试

NEF 先记录本地开通权益，再同步尝试通知。通知失败不撤销订购，页面显示对应状态；订购响应增加 `notification`，批量订阅旧套餐时 `notification.notifications` 包含每项结果。HTTP 客户端超时为 5 秒，读取时另检查耗时和 64 KiB 回包上限；不是严格的全链路 5 秒 SLA。

| `notification.status` | 含义 |
|---|---|
| `delivered` | HTTP 2xx，或约定的 400/2053 已存在、DELETE 404/2051 不存在；不证明新价格已覆盖旧套餐 |
| `not_configured` | 未设置回调地址、账号未启用或价格未配置；未发送 |
| `failed` | 配置无效、缺凭据、连接/超时/3xx/4xx/5xx 或响应超限 |
| `not_applicable` | 只订原子工具，或套餐不在 notify_plans 中 |

状态记录含 `event_id/account_id/plan_id/status/code/attempts/http_status/last_attempt_at`，并新增 `action=create|delete`、`price`、`capability_ids`、`request={method,path,headers,body}`、`response={http_status,body}`。request 不含 host 或 Authorization；response 保留最多 64 KiB 的实际回包，已知配置 token 与 host 会脱敏，不展示上游凭据。仍应避免对端将其它秘密写入业务响应。记录只允许所属账号读取。

POST 400 且顶层 `errorCode=2053` 记 `delivered/already_exists`；DELETE 404 且 `errorCode=2051` 记 `delivered/not_found`。其它 4xx 不冒充成功。配置代码为 `not_configured/account_not_enabled/price_not_configured/invalid_config/callback_key_missing`，范围过滤为 `plan_not_enabled`，实际发送失败为 `callback_failed`。

页面客户文案仅显示“订购完成”“订购完成，已同步至合作平台”或“已取消开通”。事件编号、HTTP 状态和重试按钮在 `?ops=1` 时显示，这个查询参数仅控制 UI，不提供额外权限。

两个运维/页面接口均使用所属账号的 `Authorization: Bearer <NEF账号Key>`，公网另加 Access 机器凭据：

| 接口 | 用途 |
|---|---|
| `GET /api/v1/integration/notifications` | 返回当前账号最近 20 条通知，`Cache-Control: no-store` |
| `POST /api/v1/integration/notifications/{event_id}/retry` | 无请求体；重试本人通知，返回单条状态 |

无 Key 返回 401；不存在或属于其他账号返回 404；正在发送返回 409。已送达通知再次重试不重复发送。重试保持同一 `Idempotency-Key` 和第一次准备好的正文；对方应按这个头去重。首次因缺价格而未形成正文时，补齐后再准备正文；正文形成后改价不会改变该通知。

请用重试接口，不要用“再订购一次”代替重试：后者创建新的事件标识。网络超时可能发生在对方已保存之后，因此仅靠 NEF 重试不能保证 exactly-once。对方需提供成功/失败响应示例；若 HTTP 200 内还有业务失败码，需要另补响应解析规则，当前不猜测。

全进程最多保留 1000 条内存通知，没有后台自动重试或持久队列；重启会丢失记录和未送达事件。它只适合本次约定的短期联调。

### 取消开通与启动重置

页面账号发送 `DELETE /api/v1/services/{scene_id}/subscribe`，需账号 Key，未开通返回 404“该场景尚未开通”。NEF 先删除本地权益，再发 `DELETE {callback_url}/{planId}?subscriberId=subscriber-001`，无正文，带同样的事件/幂等头。响应为 `{service_id,subscribed:false,account,notification}`。通知失败不恢复权益；在运维视图重试原 delete 事件。

所有账号外发订购者与套餐 ID 都相同，因此取消影响农场侧同一测试套餐；其它本地账号的权益不会随之清除。这不是多用户生产语义。不要重试已经被后续开通/取消替代的历史通知。

固定 planId：

| 场景 | planId |
|---|---|
| robot_patrol | 36b3d800-2774-5e2d-a647-c26194fba4ae |
| traffic_flow_detection | 896e300c-72cf-5c47-8801-fa39c7ff207b |
| collaborative_tracking | 7e49ca9c-d2b9-57a3-b8d0-f956041d215a |

另一台电脑的版本每次启动自动 DELETE 三个套餐。本机同步版为避免普通重启误删对端数据，采用 **`subscriptions.reset_partner_plans_on_start=false` 默认关闭**；明确需要清理时设 true，下次启动按相同取消规则逐项发送并打印 `Partner plan reset scene:xxx: HTTP ...`。仍受 account_ids、notify_plans、callback_url 和凭据配置约束，空 account_ids 不发送。该操作不启动本地订阅，也不证明对端业务数据已重建。

### 10.5 本次验收清单

1. 农场提供完整 POST 地址、鉴权方式、成功/失败响应；双方确认套餐价格和 `capabilityName` 的稳定标识映射。
2. NEF 配好 URL 和明确价格，协调新后端加载；重新准备演示账号后，农场按钮跳转到带 `account_id` 的商城页面。
3. 用户开通一个场景，农场核对 `subscriberId="subscriber-001"`、嵌套 `servicePlan`、稳定 UUID 和幂等头。切换本地账号后外发标识仍相同，本地查询和通知访问权限仍隔离。分别验收选中部分能力时的精确列表，以及全不选时没有 `networkCapabilities` 字段；PA/CA 在范围内编排和 PA 自主编排由网络侧独立验收。
4. 让模拟对端返回 503，确认本地权益保留，再重试同一事件，核对不重复处理。不要故意中断正在使用的真实农场服务。
5. 需要补偿时使用第 1–9 节的只读查询；分别验收套餐资料收到、账号归属正确和页面显示，不以单一 HTTP 200 代替三项验收。
