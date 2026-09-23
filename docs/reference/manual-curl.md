# curl 联调手册

分类：运行手册。更新：2026-09-23。用于获准内网测试，接口定义见[场景接口](integration.md)、[订购通知](subscription-query.md)、[农场 MCP](farm-integration.md)、[目录发布](network-catalog.md)。所有示例 `<...>` 都需替换；不要把命令中的 NEF 地址写为 `0.0.0.0`。

## 1. 最短验证顺序

先启动 `python start.py`，同事先 POST 场景结果，再 GET 同一地址自查，最后在页面选择同一场景。无 Key 回传不需要先订购；发送 Intent、取消和主动拉取结果需要页面账号 Key 与对应权益。

下方提供两套同名 shell 函数。任选一套初始化，然后按请求表依次执行；函数只在当前终端有效，不生成文件。Key 不写入脚本或 Git。

### bash

```bash
NEF='http://<NEF电脑IP>:8069'
KEY=''
nef() {
  local method="$1" route="$2" body="${3-}"
  local args=(-sS --noproxy '*' -X "$method" "$NEF$route" -H 'X-NEF-Execution: live')
  [ -z "$KEY" ] || args+=(-H "Authorization: Bearer $KEY")
  if [ -n "$body" ]; then
    printf '%s' "$body" | curl "${args[@]}" -H 'Content-Type: application/json' --data-binary @-
  else
    curl "${args[@]}"
  fi
}
```

### PowerShell

```powershell
$NEF = 'http://<NEF电脑IP>:8069'
$KEY = ''
$OutputEncoding = [System.Text.UTF8Encoding]::new()
function nef([string]$method, [string]$route, [string]$body = '') {
    $curlArgs = @('-sS', '--noproxy', '*', '-X', $method, "$NEF$route", '-H', 'X-NEF-Execution: live')
    if ($KEY) { $curlArgs += @('-H', "Authorization: Bearer $KEY") }
    if ($body) {
        $body | curl.exe @curlArgs -H 'Content-Type: application/json' --data-binary '@-'
    } else {
        curl.exe @curlArgs
    }
}
```

JSON 用 UTF-8 管道，避免 Windows PowerShell 吃掉 `-d` 参数内的双引号。函数带 `X-NEF-Execution: live`，显式选择真实转发；场景 Intent 默认 live，旧通用入口省略该头时默认 demo。`--noproxy '*'` 仅限获准直连的测试网；不修改系统代理。以下命令在两种 shell 中调用方式相同。

## 2. 无 Key 接口

```text
nef GET /api/v1/instance
nef GET /api/v1/services
nef POST /api/v1/scene-feedback/traffic_flow_detection '{"final_result":"今天下午3点十字路口东南侧的车流量处于中等水平"}'
nef GET '/api/v1/scene-feedback/traffic_flow_detection?after=0'
nef POST /api/v1/scene-feedback/robot_patrol '{"kind":"status","title":"巡检","text":"已到达观测点"}'
nef POST /api/v1/scene-feedback/robot_patrol '{"kind":"data","data":{"count":3}}'
nef GET '/api/v1/scene-feedback/robot_patrol?after=0'
nef POST /api/v1/scene-feedback/collaborative_tracking '{"final_result":"目标已识别"}'
nef GET '/api/v1/integration/subscriptions?account_id=1'
nef POST /api/v1/af/mcp-servers '{"serverName":"farm-management","url":"http://<农场IP>:<端口>/mcp","description":"农场能力"}'
nef GET /mcp/groups/nf/mcp
nef POST /mcp/groups/computing/mcp '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
nef POST /mcp/groups/sensing/mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

`POST /api/v1/af/mcp-servers` 会立即连接所填外部 MCP 并发现工具，保持草稿，不自动发布到 TRF；之后用账号 Key 显式调用 publish。只对获准目标执行，未配允许列表默认拒绝连接，登记仍保留。对端不可达 502/504，别把“已登记”当工具已发现。

三组 `/mcp/groups/{nf|computing|sensing}/mcp` 的工具定义无需 Key：标准 MCP 使用 JSON-RPC `POST tools/list`，普通 `GET` 同一地址返回 `{"tools":[...]}` 供直接 GET 的 TRF 读取（非 MCP SSE）；`Accept: text/event-stream` 的 GET 返回 405。旧的不以 `/mcp` 结尾的分类路径仍可用。各组只列本组能力，不返回账号订阅状态。`POST tools/call` 仍需 Bearer Key、`mcp:tools` 权限与权益，且可能请求现场服务；不要用本节无 Key 命令试运行工具。

媒体上传以 JPEG 为例，PNG/MP4/WebM 修改 Content-Type 和文件名：

```bash
curl --noproxy '*' -X POST "$NEF/api/v1/scene-feedback/robot_patrol" -H 'Content-Type: image/jpeg' --data-binary @frame.jpg
```

```powershell
curl.exe --noproxy '*' -X POST "$NEF/api/v1/scene-feedback/robot_patrol" -H 'Content-Type: image/jpeg' --data-binary '@frame.jpg'
```

本轮页面仅显示文字和数据，媒体保留后端接收能力；GET 事件能看到 asset_id，不会在页面自动显示图片。

## 3. 账号接口

先 `nef POST /api/v1/register '{"account":"1"}'`，取响应 api_key。在 bash 设置 `KEY='nef_...'`；PowerShell 设置 `$KEY='nef_...'`。然后：

```text
nef POST /api/v1/services/robot_patrol/subscribe '{"network_capability_ids":["target_detection","sensing_fusion","precision_location","event_subscription"]}'
nef POST /api/v1/services/robot_patrol/intent '{"text":"请查看园区东南侧的现场情况"}'
nef POST /api/v1/services/robot_patrol/result
nef POST /api/v1/services/traffic_flow_detection/subscribe '{}'
nef POST /api/v1/services/traffic_flow_detection/intent '{"text":"今天下午3点，十字路口东南侧的车流量情况怎么样"}'
nef POST /api/v1/services/robot_patrol/feedback-access
nef GET /api/v1/exhibition/channels
nef GET '/api/v1/exhibition/channels/scene_robot_patrol/events?after=0'
nef GET /api/v1/integration/notifications
nef POST /api/v1/integration/notifications/<event_id>/retry
nef DELETE /api/v1/services/robot_patrol/subscribe
nef GET /api/v1/network/servers
nef POST /api/v1/network/servers '{"serverName":"patrol-car-managementx","url":"http://<农场IP>:<端口>/mcp","description":"本账号登记"}'
nef POST /api/v1/network/servers/<server_id>/discover
nef GET /api/v1/network/servers/<server_id>/publication
nef POST /api/v1/network/servers/<server_id>/publish
nef POST /api/v1/network/servers/<server_id>/unpublish
nef GET /api/v1/network/market
nef GET /api/v1/network/market/subscriptions
nef POST /api/v1/network/market/subscriptions '{"tool_id":"<市场工具id>"}'
nef POST /mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"manual-check","version":"1.0"}}}'
nef POST /mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
nef POST /mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
nef DELETE /api/v1/network/market/subscriptions '{"tool_id":"<市场工具id>"}'
nef GET /api/v1/network/trf/servers
nef GET /api/v1/network/trf/catalog
nef POST /api/v1/network/trf/catalog/refresh
nef POST /api/v1/network/trf/catalog/publish
nef POST /api/v1/network/trf/catalog/unpublish
nef DELETE /api/v1/network/servers/<server_id>
```

将 `<...>` 整段替换后执行。Intent 会真实发给配置的现场地址，场景开通/取消会通知农场；discover 只发现工具，publish 才在首页发布并 POST 至 TRF，unpublish 本地下架并向首次发布集合地址追加 serverName 发 DELETE，随后 GET 确认缺席；确认后才可 DELETE 本地登记。TRF 地址统一填 `registry.trf_mcp_servers_url`，正文与状态见 [TRF 契约](network-catalog.md)。发现失败/从未发布的记录可直接 DELETE。旧 sync 是 publish 别名；预览 publication 只返回报文。旧无路径回传 `POST /api/v1/scene-feedback` 要把 KEY 暂时换成 feedback-access 的 receiver_key，不能使用账号 Key 写入。媒体读取 `GET /api/v1/exhibition/channels/<id>/media/<asset_id>` 则用账号 Key。

首页发布需先填写 nef_base_url；publish 按 nf tool、computing tool、sensing tool 发出最多三条 POST，七字段结构中 isThirdParty=false、url 分别是 NEF 根地址加 `/mcp/groups/nf/mcp`、`/mcp/groups/computing/mcp`、`/mcp/groups/sensing/mcp`。summary 统计三个 MCP Server，capability_summary 统计它们覆盖的 23 项能力；GET 核对服务名、分类、URL 和可选标识，兼容驼峰/下划线字段、描述改写及尾斜杠。与旧同名根地址或旧分类路径精确匹配时先 DELETE、GET 确认缺席再 POST 新端点；其他冲突不自动覆盖。unpublish 撤回可核对归属的分类登记及旧版逐能力登记，不删除第三方条目。双向开放仍为 isThirdParty=true。GET catalog 只读缓存，POST refresh 才向相同的 /trf/api/v1/mcp-servers 发 GET；普通页对应“核对状态”，目录来源预览收在 `?ops=1` 的折叠设置中。

这三个 POST 是 NEF 内部目录操作：可用任一有效 NEF 账号 Key，不要求 `af:register` scope；账号只用于拦截匿名操作，不进入向 TRF 发送的报文和共享状态。切换账号后先读同一个 GET catalog，重复发布会跳过已登记项。双向开放的 AF MCP 登记仍使用独立的账号权限。

使用订阅者账号 Key 执行市场订阅，不要复用发布者账号。订阅本身免费且不外发；真正 tools/call 使用 tools/list 返回的准确 mcp_name 和实际 inputSchema，可能触发现场操作，按获准业务意图调用。完整契约见 [第三方工具订阅](network-catalog.md#5-第三方工具的账号订阅与调用)。

## 4. NEF 实际发出的内容

| 目标 | 请求 |
|---|---|
| 车流 | POST `http://<车流服务IP>:5432/car/start`，JSON `{"user_request":"原文"}` |
| 机器狗 | POST `http://<机器狗服务IP>:8000/in/intent`，`text/plain; charset=utf-8`，正文为原文 |
| 机器狗感知 | GET `http://<机器狗服务IP>:8000/data/perception2/latest`，无正文 |
| 农场开通 | POST `http://<农场IP>:6092/business/v1/service-plans`，见下例 |
| 农场取消 | DELETE 上述地址追加 `/{planId}?subscriberId=subscriber-001`，无正文 |

路径和报文来自用户 2026-09-18 的现场记录；公开文档不收录现场 IP。按同事提供的当前 IP/端口填写 `config/integration.local.json`，不得直接使用另一台 NEF 的地址作为本机地址。发布模板不自动连接现场，本机 local 配置不因此改写。所有出向客户端 `trust_env=False, follow_redirects=False`。

```json
{
  "subscriberId":"subscriber-001",
  "servicePlan":{
    "planId":"36b3d800-2774-5e2d-a647-c26194fba4ae",
    "showName":"机器狗巡检",
    "description":"巡检任务下发、异常信息与巡检结果回传。",
    "price":15.92,
    "networkCapabilities":[{"capabilityName":"target_detection","showName":"目标检测","description":"以当前目录为准","price":19.9}]
  }
}
```

上例只选目标检测并打 8 折。全选报价和三个稳定 UUID 见[订购通知](subscription-query.md#取消开通与启动重置)，该文为唯一价格/ID 规则来源。POST/DELETE 带 `Idempotency-Key` 和 `X-NEF-Event-ID`；Intent 带 `X-NEF-Request-ID`。

用户现场记录提供了农场 `400 errorCode=2053 SERVICE_PLAN_ALREADY_EXISTS` 和 `404 errorCode=2051`。本机使用模拟对端验证识别规则，未独立重验真实农场；分别记 delivered/already_exists、delivered/not_found，不能据此判断旧价格已被更新。通知 GET 的 request/response 可用于对报文，先看 action，再看 HTTP 状态和 code。

## 5. 同事 POST 了页面没显示

1. 查看实际服务日志中是否出现正确 POST 路径；没有则先查对方请求地址、路由和公司代理。公司代理的 504 不是 NEF 业务回包。
2. GET 同一场景地址自查 events；有事件但没显示，核对页面场景、最新 kind，图像/视频本轮不显示。
3. 内容变成 `????` 是发出前编码损失，使用 UTF-8 管道重新发送；NEF 无法恢复已变成问号的字符。
4. 422 检查 JSON 双引号、Content-Type、final_result 是否空或超长；404 检查 scene_id。避免把空格或中文标点拼入 URL。
5. 重启后所有账号、Key、权益、事件失效；页面用 instance_id 检测并清掉旧账号，需要重新注册和开通。旧进程未重启不会加载新增 Python 路由。

运行日志可重定向到 `.runtime/nef.out.log`。Windows 重启前用 `Get-NetTCPConnection -LocalPort 8069 -State Listen` 找真正监听 PID，再核对命令行；`Start-Process python` 返回的可能是启动器 PID。不要只凭端口杀未知进程。10048 表示端口已占用，不代表新代码启动成功。
