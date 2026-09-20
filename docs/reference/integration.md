# 场景接口对接说明

分类：接口参考。面向场景开发同事，更新：2026-09-20。

启动、改地址用 [README](../../README.md#二换电脑启动与配置)，bash / PowerShell 命令见 [curl 联调手册](manual-curl.md)。套餐读取和通知另见[订阅契约](subscription-query.md)。机器狗地址和报文来自用户提供的另一台电脑联调记录，本机未访问真实对端。

## 一、把结果回传给我们

内网首选 **`POST http://<NEF电脑IP>:8069/api/v1/scene-feedback/{scene_id}`**，无需 NEF Key，也无需先注册账号或创建通道。`scene_id` 只允许 `robot_patrol`、`traffic_flow_detection`、`collaborative_tracking`；未知值返回 404，detail 列出可用值。

三个固定通道分别为 `scene_robot_patrol`、`scene_traffic_flow_detection`、`scene_collaborative_tracking`，owner 为 null。它们按场景共享，不隔离账号，不代表某次意图的专属结果。只能放获准共享的测试数据，不应直接暴露公网。旧 Tunnel 的 Access 策略未改变，经过它的机器仍需单独交付的 Access 凭据。

### 1. 文字或结构化数据

`Content-Type: application/json`，推荐正文：

```json
{"final_result":"今天下午3点十字路口东南侧的车流量处于中等水平"}
```

`final_result` 必须是非空字符串，最多 16000 字符；只允许再带可选 `request_id`。也接受已有事件格式：

```json
{"kind":"status","title":"现场巡检","text":"巡检已完成"}
```

```json
{"kind":"data","title":"车流统计","data":{"vehicle_count":18}}
```

`data` 必须是对象或数组。JSON 必须使用 UTF-8，最多 64 KiB；JSON 不合法返回 422，提示 PowerShell 使用管道传递 JSON。不要用未经确认的 `curl.exe -d '{"..."}'` 写法，部分 Windows PowerShell 会去掉内部引号。正确命令见手册。

成功响应 HTTP 200：`{"received":true,"event_id":1}`。只证明 NEF 存入事件，不证明场景执行完成。重复 POST 会新增事件，不是幂等更新。

### 2. 图片和视频

同一场景 POST 地址接受原始文件字节，不是 multipart 或 Base64 JSON。支持 `image/png`、`image/jpeg`、`image/webp`、`video/mp4`、`video/webm`，校验类型和文件头；其它媒体类型返回 415。单文件最多 16 MiB，全进程媒体最多 64 MiB。

后端仍接收并记录媒体事件，**本轮页面已移除媒体查看器，不会自动显示图像或视频**。已登录账号可从共享通道的 `GET /api/v1/exhibition/channels/scene_<scene_id>/media/<asset_id>` 获取原始媒体。私有通道仍仅拥有者可读。文件头通过不代表媒体一定能解码。

### 3. 同事自查和页面轮询

无需 Key：

```http
GET /api/v1/scene-feedback/traffic_flow_detection?after=0
```

返回 `channel_id/service_id/name/events/next_cursor/reset_required/history_truncated`。`after` 为非负整数，只取事件 `id > after`；游标超过当前序号时 `reset_required=true` 并从头返回保留记录。每通道仅保留最新 100 条，超出窗口会标记 `history_truncated`。服务重启清空事件，通道按场景重建。

页面进入场景即每 2 秒读取共享通道，无需账号；文字和结构化数据分别显示保留历史中的最新一条，尚无数据或旧数据已移出历史时隐藏数据列。文字移出历史后恢复等待，不把过期内容当最新结果。媒体事件仍能通过 GET 查看元数据。HTTP 200 但无文字，先检查 scene_id 与 kind，再确认页面选的是同一场景。

### 4. 兼容凭证接口与请求关联

旧 `POST /api/v1/scene-feedback` 保留，只接受 `Authorization: Bearer <场景接收Key>`，由 Key 路由。页面账号调用 `POST /api/v1/services/{scene_id}/feedback-access` 可拿到共享通道及 `open_endpoint/feedback_endpoint/receiver_key`；同一场景任意账号拿到相同通道与备用 Key。`general` 和手工创建的通道保持私有。

NEF 出向 Intent 带 `X-NEF-Request-ID`。可在回传 JSON 的 `request_id` 或同名 HTTP 头原样带回，图片/视频用头；头须为 1–1000 字符，正文和头同时存在须相同。关联仅是标签，不把它当执行完成证明。

需按 request_id 筛选时，已登录账号使用 `GET /api/v1/exhibition/channels/<channel_id>/events?after=0&request_id=...`。共享场景任意账号可读，私有通道仍隔离；接收 Key 是只写凭证，不能替代账号 Key 读取。`?ops=1` 显示页面“回传地址”和通知细节，仅是展示开关，不是安全权限。

## 二、NEF 向现场发送

配置均位于 `config/integration.local.json` 的 `bridge.scenes`。发布模板的场景 URL 均留空，填写同事实际地址后才发送；已有 local 配置不覆盖。配置热读，不需要为改地址重启。显式 `NEF_BRIDGE_CONFIG` 仍优先覆盖。请求不走系统代理、不跟随重定向、不自动重发执行请求。

### 车流量联调

```http
POST http://<车流服务IP>:5432/car/start
Content-Type: application/json
X-NEF-Request-ID: <本次请求标识>

{"user_request":"今天下午3点，十字路口东南侧的车流量情况怎么样"}
```

对应配置 `bridge.scenes.traffic_flow_detection.intent`，`body={"user_request":"$text"}`。结果回传到 `/api/v1/scene-feedback/traffic_flow_detection`，无需 Key。

### 机器狗巡检

已提供的协议为纯文本，不是 JSON：

```http
POST http://<机器狗服务IP>:8000/in/intent
Content-Type: text/plain; charset=utf-8
X-NEF-Request-ID: <本次请求标识>

<页面输入原文>
```

`bridge.scenes.robot_patrol` 配置：

```json
{
  "intent":{"url":"http://<机器狗服务IP>:8000/in/intent","method":"POST","content_type":"text/plain","body":"$text","timeout_seconds":8},
  "result":{"url":"http://<机器狗服务IP>:8000/data/perception2/latest","method":"GET","timeout_seconds":8,"delay_seconds":0}
}
```

结果 200 + JSON 表示有数据，204 或空内容表示暂无结果。Intent 发送成功立即拉取一次，响应附 `sensing_result.status=stored/unchanged/empty/unavailable`；拉取失败不使 Intent 失败。后续页面每 3 秒调用 NEF 的 `POST /api/v1/services/robot_patrol/result`，需账号 Key 及该场景权益，也可点“刷新感知结果”。切换场景、页签、账号或取消开通停止循环。轮询只拉结果，不重复发送 Intent。

后端规范化内容后去重，与上次拉取内容相同则不重复存入；`final_result` 存文字事件，其它对象/数组存数据事件，纯文本存文字。拉取地址也支持 `method=POST`、`body={"user_request":"$text"}`，使用当前账号最近一次成功发送的该场景 Intent。GET 不带请求体；`delay_seconds` 最多 5 秒。

`GET /api/v1/services` 每个场景含 `result_pull`，决定页面是否显示刷新按钮。没有配置 result URL 就不自动拉取。

### 端网协同与通用 Intent

`bridge.scenes.collaborative_tracking.intent` 仍缺同事地址，模板 `body={"user_request":"$text"}`。不指定场景的 Intent 使用独立 `bridge.intent`。端网协同参数化 API / Tool 保留 `device_id/video_source/target` 三个字符串；实际执行路由另填 `invoke`。

## 三、回执与部署边界

- 转发默认 8 秒超时，配置限制在 1–30 秒；响应最多 1 MiB。JSON 或 UTF-8 文本保存在 `upstream.body`，状态在 `upstream.http_status`。200/202 只表示响应，不等于任务完成。
- 非 2xx 返回 502，超时返回 504；不盲目重发 Intent，先确认现场是否已受理。结果拉取失败可再刷新。
- `GET /api/v1/instance` 无 Key 返回进程随机 16 位十六进制 ID。页面启动时检查，收到旧 Key 的 401 时也检查，实例变化则清空浏览器旧账号并提示重新注册。
- 启动用 `python start.py`，监听 `0.0.0.0:8069`；同事使用网卡 IP，不用 `0.0.0.0`。不要关闭整个防火墙或公司代理；可用获准内网直连方式检查。完整排查顺序见 curl 手册。
