# 6G NEF Demo 前端优化设计（深空电信蓝换肤 + AF 反向调用）

日期：2026-06-11
状态：已与用户确认

## 背景与目标

nef-expo 是面向运营商伙伴的现场讲解演示（讲解人操作，界面扮演 AF 开发者视角）。
目标：让观众感受到 6G NEF「多种调用方式、繁荣的调用生态、双向开放」。

本期决策记录：

- 视觉风格选定「深空电信蓝」（候选中的 B：深海军蓝 + 青紫霓虹 + 玻璃拟态）。
- 信息架构保持现有 8-Tab 不变（候选中的 A：保守增强）。
- 不做多调法对比工作台。
- 不做 A2A（已另行记录：将来采用"NEF=总代理 Agent"任务委托模式）。
- 新增「AF 反向调用」：网络内部调用 AF 注册进来的能力，触发方式 = Intent 联动为主 + 手动模拟按钮兜底。
- AF 注册 Tab 采用「左注册表单 · 右生态看板」布局（候选布局 A）。

## 1. 范围

| 内容 | 是否本期 |
|---|---|
| 全局换肤（CSS 变量 + hero）| 是 |
| AF 注册 Tab 重做（反向调用看板）| 是 |
| Intent 与第三方能力联动 | 是 |
| 后端反向调用模拟接口 | 是 |
| A2A / 多调法对比 / Tab 重组 | 否 |

技术形态不变：FastAPI 后端 + 无框架单文件 `static/index.html`，所有状态内存存储。

## 2. 全局换肤（深空电信蓝）

只动 CSS 与少量 HTML，不改交互逻辑。

- CSS 变量替换（`:root`）：
  - 背景：深空渐变 `#050b1f → #0a1733`（body 用 fixed 渐变）
  - 面板 `--panel: #0a142e`，卡片 `--card: #0e1d3f`，边框 `--border: #2a4a8a`
  - 主强调 `--accent: #39d2ff`（青），辅助紫 `#bc8cff`，成功 `#39ffb0`，警示橙 `#ffc857`
- 顶栏：玻璃拟态（半透明背景 + backdrop-filter blur），平台名青→紫渐变文字（background-clip: text）。
- 能力超市 banner 升级为开场 hero：渐变大标题「一张网络，无限调用」+ 现有统计数字（N 项能力 / 3 种调用方式 / 5 个套餐）+ REST·MCP·Intent 徽标行。讲解开场画面。
- 能力卡片 hover 辉光（box-shadow 青色微光）、primary 按钮蓝紫渐变、分类色点加 glow。
- 各 Tab 的表格、pre、弹窗、pill、agent-block 同步适配新变量（多数自动继承）。

## 3. AF 注册 Tab 重做（布局：左注册 · 右生态看板）

### 顶部：反向链路图（常驻）

```
AF 能力 ─注册─▶ NEF 能力超市 ─发现─▶ Planning Agent ─编排─▶ NEF 出向网关 ─反向调用─▶ AF Endpoint
                                                        (鉴权·计费·审计)
```

- 静态常驻；当一条反向调用发生（手动或 Intent 联动）时，节点按链路顺序逐个点亮（CSS class 切换动画，总时长约 1.5s）。

### 左列：注册表单

现有字段（名称/类型/描述/端点）+ 新增「Intent 关键词」输入框（逗号分隔，选填；为空则默认用能力名称作关键词）。

### 右列：「我注册的能力」生态看板

当前账号注册的每项能力一张卡片：

- 状态徽章：`registered`（无调用记录）/ `已被网络发现`（有调用记录）
- 统计：被调用次数、最近调用时间、累计模拟收益（每次调用 +0.05 元）
- 「⚡ 模拟网络调用」按钮：调一次 simulate-call 接口
- 调用日志（最近 10 条，倒序）：时间 / 调用方 Agent / 触发源（Intent 文本摘要或「手动模拟」）/ 耗时 ms / 结果状态 / 计费
- 空态：未注册任何能力时显示引导文案（「注册你的第一个能力，让网络发现并调用它」）

刷新机制：该 Tab 激活时每 3 秒轮询 `my-calls` 接口；手动模拟后立即刷新。

## 4. Intent 联动

- `intent.py` 的 `match_capabilities` 匹配范围扩展为 `CAPABILITIES + THIRD_PARTY`。
- 第三方能力进入执行计划时：
  - 步骤标记 `source: "third_party"`、`direction: "reverse"`
  - 执行语义为「NEF 出向网关调用 AF 端点」，调用 stub 返回模拟 AF 响应
  - 同时向 `REVERSE_CALLS` 写入一条台账（触发源 = intent 文本）
- 前端 Intent 结果渲染：third_party 步骤用绿色左边框 + 「↩ 反向调用 AF 能力」徽章，与内部 Agent 步骤形成对比；该步骤的"调用方 Agent"取 Planning Agent 分派的域 Agent（按能力类型映射，ai_model→Computing Agent，data_source→Data Agent，tool→Data Agent）。

## 5. 后端新增（全部内存模拟）

- `REVERSE_CALLS: dict[cap_id, list[record]]`，record 字段：`ts, caller_agent, trigger("manual"|"intent"), trigger_detail, latency_ms, status, fee`
- `POST /api/v1/third-party/{cap_id}/simulate-call`（需鉴权）：生成一条模拟记录（latency 20–80ms 随机，caller_agent 按能力类型映射），返回该记录 + 模拟的请求/响应 payload。
- `GET /api/v1/third-party/my-calls`（需鉴权）：返回当前账号注册的全部第三方能力及各自台账、汇总统计。
- `RegisterAfReq` 增加 `intent_keywords: list[str] = []`；`register_af` 写入 `Capability.intent_keywords`（为空时默认 `[name]`）。
- `stubs.py`：第三方能力 id（`tp_` 前缀）返回通用模拟 AF 响应（含 `provided_by: "third_party_af"`、echo payload、模拟结果字段）。

## 6. 错误处理与边界

- simulate-call 对不存在/不属于当前账号的 cap_id 返回 404/403。
- 服务重启后 THIRD_PARTY 与 REVERSE_CALLS 清空——demo 可接受，README 注明。
- 轮询接口失败时看板静默保持上次数据，不弹错误打断演示。

## 7. 验证

- 新增后端接口写最小 pytest 冒烟测试（subscribe → register-af → simulate-call → my-calls → intent 命中第三方能力）。
- 前端启动后按演示动线人工过一遍：超市 hero → 订阅 → API/MCP/Intent → Skill → 编排 → AF 注册+反向调用（手动 + Intent 联动两条路径）。
