# 动态鉴权流水线 + 路由分发 设计

日期：2026-06-15 ｜ 分支：main ｜ 面向：运营商现场演示

## 背景与目标

现状两处不足，演示时撑不起"流程感"与"可信度"：

1. **鉴权太静态**：`_auth_evidence` 把四步检查全写死成 `passed`，前端只是四个打勾的卡片，像一张结果截图，不像 NEF 在"逐级鉴权"。
2. **粒度错配 + 无后台实现**：NEF 目录是 tool 粒度，但同事的后台只实现到场景/套餐级，单个 tool 在我们后台没有真实代码。核心疑问是——*若 NEF 把一个 tool 级请求转给后台，后台分得清这是要它干嘛吗？*

目标：把鉴权做成**动态、逐级、客户看得见**的 CAPIF 流水线；并用**显式请求信封 + NEF 分发表**讲清"后台分得清、没实现的由 NEF 兜底"。

## 一、CAPIF 实时鉴权流水线

基于 3GPP CAPIF（AEF 对 API Invoker 逐次鉴权）建模为 7 级流水线。后端按真实条件计算每级 `status`，前端逐级点亮动画（每级 ~120–260ms + ✓/⚠），让客户"看见"。

| 序 | code | 标签 | 动态判定 |
|---|---|---|---|
| ① | access | 接入·限流 | TLS/接入点；配额 used/limit（演示恒过，展示配额计数） |
| ② | credential | 凭证解析 | Bearer 头存在且格式正确 |
| ③ | token | 令牌校验 | 签名/有效期/未吊销（演示恒过） |
| ④ | invoker | 身份识别 | API Key → AF 账号（CAPIF API Invoker ID） |
| ⑤ | scope | 权限范围 | required_scope ∈ key.scopes |
| ⑥ | authz | 授权判定 | `_entitled`：订阅 ∪ 等级 ∪ 第三方；不满足 → 拒（402） |
| ⑦ | audit | 审计落账 | 写 request_id（无论放行/拒绝都落账） |

**分支（动态可感知的关键）**：
- 全部通过 → decision=`allow`，七级全绿。
- 未授权且未确认支付 → ⑥ 变橙 `denied`、⑦ 仍落账 `审计:拒绝`，HTTP 402，前端把流水线渲染到 ⑥ 再弹支付卡。
- 缺/错 Key → ② `denied`，HTTP 401（前端基于固定模板渲染到 ②）。

**数据结构**：`_capif_pipeline(key, rec, cap, scope, *, entitled, paid) -> {request_id, decision, quota:{used,limit}, stages:[{seq,code,label,status,latency_ms,detail}]}`。
放行结果挂在 `result["nef_auth"]`（在原 stamp 基础上增补 `pipeline`/`quota`/`dispatch`，保持原字段不删，兼容老测试）；402 时挂在 `_payment_required_payload` 的 `pipeline` 字段。

## 二、路由判定 + NEF 分发表

**显式请求信封**（NEF 转后台时携带，后台靠 `service_id` 分发，无歧义）：
```json
{ "request_id":"req_…", "service_id":"robot_patrol", "tool_id":"target_detection", "params":{…} }
```

**NEF 分发表**：每个暴露能力 → 落地目标二选一。
- `BACKEND_SERVICES`（演示初值）：`{robot_patrol, traffic_forecast_pkg, uav_track}`——后台真实现的场景级 service_id。
- 单个 tool / 未注册场景 → `nef-ref`（NEF 参考回显，前端标注 mock）。

`_dispatch(kind, id) -> {target:"backend"|"nef-ref", service_id, envelope, note}`：
- 场景 id ∈ BACKEND_SERVICES → `backend`，note="命中后台 service_id"；
- 否则 → `nef-ref`，note="无后台实现 → NEF 参考回显"。

**后台分得清的保证**：NEF 只把 BACKEND_SERVICES 里（后台声明过的）id 转发出去；没实现的 tool 级请求根本不出向，由 NEF 参考回显兜底。歧义在 NEF 这层消化。

新增 `GET /api/v1/dispatch-table` 返回全表，前端在「场景方案」页渲染一张可视分发表。

## 三、贯穿四个入口

同一条流水线 + 路由判定出现在：API 直调、MCP tools/call、意图受理、场景运行。
- API/MCP 单 tool：流水线 → 路由=nef-ref → 结果信封（标 mock）。
- 场景运行：流水线 → 路由=backend(service_id) → 展示转发信封 → 回执轨迹。
- 意图：受理流水线沿用 `_auth_evidence` 升级为同结构 stages。

## 四、改名

`场景蓝图` → **`场景方案`**（tab 按钮 + 区标题 + playbook/README 引用）。运营商一听即懂：每个场景的成套解决方案 + 怎么调 + 一键跑。

## 五、前端

- 复用组件 `renderAuthPipeline(el, pipeline, onDone)`：逐级点亮动画 + 路由判定行。
- API 直调：调用即播放流水线 → 路由 → 结果信封；402 播放到 ⑥ + 支付卡。
- 订阅与鉴权页：用同组件跑一次样例，替换静态四宫格。
- 「场景方案」页：加「NEF 路由分发表」面板（哪些命中后台 / 哪些 NEF 参考回显）。
- MCP / 意图 / 场景：结果区复用流水线渲染。

## 六、测试

- `nef_auth.pipeline` 七级、decision=allow（已授权调用）。
- 402 payload 含 pipeline 且 ⑥ authz=denied。
- `/api/v1/dispatch-table`：tool→nef-ref，featured 场景→backend。
- 场景运行回执含 dispatch.target=backend + envelope.service_id。
- 全量回归（39 测试）保持绿。

## 范围外（本次不做）

- 全局滚动审计台账面板（仅流水线内 ⑦ 落账行）。
- 令牌生命周期可视化（签发/吊销/刷新）。
- 真实小模型实现 tool（保持 NEF 参考回显 + 契约叙事）。
