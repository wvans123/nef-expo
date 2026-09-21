# curl 联调手册

分类：运行手册。更新：2026-09-21。用于获准内网测试，接口定义见[场景接口](integration.md)、[订购通知](subscription-query.md)、[农场 MCP](farm-integration.md)、[目录发布](network-catalog.md)。所有示例 `<...>` 都需替换；不要把命令中的 NEF 地址写为 `0.0.0.0`。

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
nef POST /api/v1/af/mcp-servers '{"name":"农场管理平台","url":"http://<农场IP>:<端口>/mcp","description":"农场能力"}'
```

最后一条会立即连接所填 MCP 并发现工具，保持草稿，不自动发布到 TRF；之后用账号 Key 显式调用 publish。只对获准目标执行，未配允许列表默认拒绝连接，登记仍保留。对端不可达 502/504，别把“已登记”当工具已发现。

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
nef POST /api/v1/network/servers '{"name":"私有测试MCP","url":"http://<农场IP>:<端口>/mcp","description":"本账号登记"}'
nef POST /api/v1/network/servers/<server_id>/discover
nef GET /api/v1/network/servers/<server_id>/publication
nef POST /api/v1/network/servers/<server_id>/publish
nef POST /api/v1/network/servers/<server_id>/unpublish
nef GET /api/v1/network/market
nef POST /api/v1/network/catalog/publication '{"capability_ids":["target_detection"],"service_ids":["robot_patrol"]}'
nef POST /api/v1/network/catalog/publish '{"capability_ids":["target_detection"],"service_ids":["robot_patrol"]}'
```

将 `<...>` 整段替换后执行。Intent 会真实发给配置的现场地址，subscribe/DELETE 会通知农场；discover 只发现工具，publish 才在首页发布并 POST 至 TRF，unpublish 本地下架并按 `registry.withdraw_url` 通知撤回（没有地址则提示待配置）。旧 sync 是 publish 别名；预览 publication 只返回报文。旧无路径回传 `POST /api/v1/scene-feedback` 要把 KEY 暂时换成 feedback-access 的 receiver_key，不能使用账号 Key 写入。媒体读取 `GET /api/v1/exhibition/channels/<id>/media/<asset_id>` 则用账号 Key。

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
