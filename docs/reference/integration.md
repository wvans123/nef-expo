# 场景接口对接说明

分类：接口参考。面向场景开发同事 · 更新：2026-09-17

另一个应用查询“账号 1 / 2 / 3 订阅了哪些工具”请使用独立的[订阅查询接口](subscription-query.md)。本文只维护场景执行与回传契约。

**你们提供执行接口，我们把调用发过去；我们提供回传地址，你们把状态、数据和画面发回来。**

## 车流量联调

换电脑运行 `python start.py`，启动与统一配置见 [README](../../README.md#二换电脑启动与配置)。页面选“车流量检测”，开通后输入意图，点击发送。

**NEF 发给车流量服务：**

```http
POST http://10.70.113.122:5432/car/start
Content-Type: application/json
```

```json
{"user_request":"今天下午3点，十字路口东南侧的车流量情况怎么样"}
```

地址在 `config/integration.local.json` 的 `bridge.scenes.traffic_flow_detection.intent.url`；请求字段在同一对象的 `body` 中，`"$text"` 替换成用户原文。默认等待 8 秒；长任务请及时返回受理回执，完成后异步回传，不自动重试执行请求。

**车流量服务回给 NEF：**

```http
POST http://<NEF电脑IP>:8069/api/v1/scene-feedback
Authorization: Bearer <页面“接口信息”中的场景Key>
Content-Type: application/json
```

```json
{"final_result":"今天下午3点十字路口东南侧的车流量处于中等水平xxxxxx"}
```

正文只需要 `final_result`，非空字符串且最多 16000 字符。Key 放请求头，不加到 JSON；成功返回 `{"received":true,"event_id":1}`。先在调用页获取接口信息，重启后重新提供 Key。多个账号通过各自 Key 隔离；不带 request_id 时按场景展示，不推断属于哪一次请求。内网直连无需旧域名或 Cloudflare 头。

## 一、把结果回传给我们

我们会提供**完整回传地址和场景专用 Key**，不需要你们创建通道、调用点或填写场景 ID。同一场景在本次服务中复用同一份对接信息，重启后我们重新提供 Key。

统一接口：`POST /api/v1/scene-feedback`

所有请求都带：`Authorization: Bearer <场景Key>`

**内网回传地址：`http://<NEF电脑IP>:8069/api/v1/scene-feedback`；旧公网回传地址：`https://nef.2012wtlab.com/api/v1/scene-feedback`。** 仅公网接入还需带上我们单独提供的两个请求头，状态、数据、文件上传均相同；本地或内网直连不需要：

```http
CF-Access-Client-Id: <我们提供的Client ID>
CF-Access-Client-Secret: <我们提供的Client Secret>
```

公网入口和调用凭据已配置，凭据需单独交付，有效凭据回传尚待联调。以下示例省略这两个头，使用公网地址时请补齐；凭据不要写入前端页面或代码仓库。直接使用我们提供的 **HTTPS 地址**，不需要特殊 User-Agent；不要先向 HTTP 地址发送密钥再依赖跳转。

### 1. 发送状态或文字结果

设置 `Content-Type: application/json`，请求体：

```json
{
  "kind": "status",
  "text": "巡检完成：发现一处待复核区域，其余巡检点正常。"
}
```

### 2. 发送数据

同样使用 `Content-Type: application/json`，业务数据放在 `data` 中，字段按场景约定：

```json
{
  "kind": "data",
  "data": {
    "location": "A路口",
    "vehicle_count": 18
  }
}
```

### 3. 发送图片或视频

向**同一个地址**发送文件原始字节，上传后自动显示，不需要再调用其他接口。

例如发送 JPEG 图片（将地址和 Key 替换成我们提供的值）：

```bash
curl -X POST "<完整回传地址>" \
  -H "Authorization: Bearer <场景Key>" \
  -H "Content-Type: image/jpeg" \
  --data-binary @frame.jpg
```

图片支持 `image/png`、`image/jpeg`、`image/webp`；视频支持 `video/mp4`、`video/webm`。更换文件时同步修改 Content-Type。**不是表单上传，也不是 Base64 JSON；直播流另行对接。**

### 4. 如何判断回传成功

成功时返回 HTTP 200，例如：

```json
{"received": true, "event_id": 1}
```

确认 `received` 为 true 即可，event_id 不需要再用于其他调用。公网请求若返回 302 或 HTML 登录页，说明尚未通过入口验证，不是回传成功。失败时把 HTTP 状态码和返回内容发给我们排查，不要无限重试；重复提交会产生重复记录。

### 5. 关联某次意图与增量读取

NEF 转发真实 Intent 时附带 `X-NEF-Request-ID`。同事收到后，可在回传 JSON 的 `request_id` 字段或同名 HTTP 头中原样带回；图片/视频用 HTTP 头。头值要求 1–1000 字符，JSON 与头同时存在时必须相同，否则返回 422 且不写入。没有关联值仍可按场景回传，不会自动匹配最近一次意图。

供持有该账号 NEF Key 的读取方使用：

```http
GET /api/v1/exhibition/channels/<channel_id>/events?after=0&request_id=<原request_id>
Authorization: Bearer <NEF账号Key>
```

通道信息由 `POST /api/v1/services/{service_id}/feedback-access` 获得；回传同事仍无需自行创建通道。公网请求另带 Access 凭据。读取不能使用只写的场景回传 Key，也不能跨账号。

`after` 是非负事件序号，返回严格大于该值的事件；`request_id` 可省略。响应新增 `next_cursor`（通道当前序号，即使筛选结果为空也推进）、`reset_required`（请求游标大于当前序号）和 `history_truncated`（需要的早期事件已超出保留范围）。每通道只保留最后 100 条事件，不能依赖它补齐全部历史。换 request_id 过滤条件时重新从 after=0 读取；通道不存在返回 404，服务重启后需重新获取接口信息和 Key。

请求关联是回传方提供的标签，NEF 不验证其是否确属先前某次执行，不将匹配 ID 当成业务完成证明。新代码已支持 JSON 请求头关联和增量读取；上传 GitHub 不会更新已有运行进程，部署后需验收接口版本。

## 二、请提供你们的执行接口

每个场景请给我们以下资料：

- **接口地址、HTTP 方法和鉴权方式**，实际密钥单独交付。
- **一份完整请求示例**，说明必填字段和参数含义。
- **成功、失败的响应示例**，说明返回的是“已受理”还是“已完成”。
- **大致响应时间**，以及会回传哪些数据、图片或视频。

**已有接口就发已有格式，我们负责适配。** 如果还没有确定格式，可以参考下面两类；这些是建议示例，不是要求你们改成固定格式。

### 1. 三个场景：以接收 Intent 为主

机器狗巡检、车流量检测、端网协同识别追踪均以 Intent 为主。每个场景提供接收地址，NEF 将业务意图原文发过去：

```json
{"text": "请检测A路口车流情况，并返回检测画面和统计数据"}
```

意图由你们的场景服务或内部 Agent 处理，不要求新增 Intent ID 或任务状态查询接口。可以在执行接口响应中直接返回 `{"text":"业务结果摘要"}`；耗时较长时先返回受理回执，完成后通过上面的统一接口发送文字结果。数据和画面按需附加。

#### 机器狗与车流接口分别配置

使用 `python start.py` 启动时，若本地文件不存在，会从 `config/integration.example.json` 生成 `config/integration.local.json`；已有文件不会被覆盖。机器狗配置在 `bridge.scenes.robot_patrol.intent`，车流配置在 `bridge.scenes.traffic_flow_detection.intent`，互不共用执行地址。

机器狗模板如下，`url` 留空时拒绝发送；填入同事提供的完整地址后才可调用：

```json
{
  "url": "",
  "method": "POST",
  "body": {"intent": "$text"},
  "timeout_seconds": 8
}
```

`intent` 只是待确认的参数名，不是已约定契约；若对方叫 `prompt`，改为 `"body": {"prompt": "$text"}`。`$text` 替换成页面输入的完整意图，保留原文。已有本地文件缺少 `robot_patrol` 时，仅补入这个场景配置，不覆盖车流或其他配置。未设置旧版 `NEF_BRIDGE_CONFIG` 覆盖项时，保存统一配置后下一次调用读取新值；改配置不需要重启。

响应格式待确认，不预设任务 ID、进度或完成字段。当前转发将 2xx 响应的 JSON 值或 UTF-8 文本保存在 `upstream.body`，HTTP 状态保存在 `upstream.http_status`；页面展开“接口原始回执”可查看，未知字段不要求先写解析代码。非 2xx 当前返回上游错误状态，不透传其响应正文；响应超过 1 MiB 会拒绝。收到 200/202 不等于巡检完成，后续异步结果仍可使用第一节的统一回传接口。真实机器狗地址、参数名、鉴权与完成判据均待同事确认；模板及本地测试不代表已接通机器狗。

### 2. 可选的 API / Tool：接收业务参数

端网协同也保留参数化调用，例如：

```json
{
  "device_id": "terminal-01",
  "video_source": "camera-01",
  "target": "指定移动目标"
}
```

`video_source` 在这个示例中是视频源标识，不是视频文件。

外部的 **API 和 Tool 调用由 NEF 转成普通 HTTP 业务请求**，可以共用你们的一个执行接口，**不需要另做 MCP 接口**。

耗时任务建议先返回受理结果，再通过回传接口发送后续反馈。当前转发默认超时 8 秒，可配置；请提前说明接口是否需要更长时间。收到受理响应不等于业务已经完成。

## 三、联调顺序与注意事项

1. 我们提供回传地址和 Key，你们先发一条状态或数据，确认页面能看到。
2. 再发一张图片或一个短视频，确认展示正常。
3. 你们提供执行接口，我们发起真实调用，核对请求和回传结果。

- **大小限制**：单条 JSON 不超过 64 KiB，单个图片 / 视频文件不超过 16 MiB。
- **地址与密钥**：使用双方可访问的部署地址；场景 Key 只用于回传，不用于执行接口。当前演示环境重启后，Key 需要重新提供。
- **请求关联**：可按第 5 节回送 NEF 请求编号；内部任务 ID、真实进度和完成判据仍由场景方提供，不由 NEF 推算。
