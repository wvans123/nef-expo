# 6G NEF 能力开放平台 Demo

一个面向运营商现场演示的 **6G 网络能力开放功能（NEF, Network Exposure Function）** 原型。
后端为 FastAPI，前端为单文件原生 HTML/JS（无构建步骤），用于向第三方应用（AF, Application Function）
开发者展示"一张网络、无限调用"的能力开放生态：服务化接口（REST）、类 MCP 接口、意图接口、
场景一键运行、自助编排、以及 AF 双向开放与网络反向调用。

> 状态全部存于内存，重启服务即清零——演示从"新 AF 入驻"讲起即可。

---

## 一、环境要求

| 项目 | 版本 / 说明 |
|---|---|
| Python | 3.10+（已在 3.14 上验证） |
| 操作系统 | Windows / macOS / Linux 均可（开发环境为 Windows + PowerShell） |
| 依赖 | `fastapi`、`uvicorn`（运行）；`pytest`、`httpx`（测试） |

---

## 二、本地搭建

### 1. 克隆仓库

```bash
git clone <你的仓库地址>.git
cd nef-expo
```

### 2. 创建虚拟环境（推荐）

**Windows / PowerShell：**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux：**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

```bash
python server.py
```

启动后访问 **http://localhost:8000** 。
> 端口被占用时，先结束旧进程：Windows 用
> `Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`。

### 5. 运行测试（可选）

```bash
pytest -q
```

---

## 三、快速体验（5 分钟）

1. 右上角 **「注册账号」**：输入名称（如 `developer_zhang`）→ 注册即签发 API Key（订阅与签发已解耦）。
2. **「订阅与鉴权」**：查看 🔐 CAPIF 鉴权流水线（7 级逐级点亮：接入·限流 / 凭证解析 / 令牌校验 / 身份识别 Invoker / 权限范围 scope / 授权判定 / 审计落账，依据 3GPP CAPIF）；
   可切换账号等级 **FREE / PRO / MAX**（PRO 含 basic 层免订阅，MAX 含 basic+advanced）。
3. **「API 直调」**：调一个未授权能力 → 弹 **402 Payment Required**（身份认证通过≠已授权）→ 确认按次支付 → 成功；
   响应以"业务结论 + 关键指标 + 可折叠原始 JSON"的标准信封呈现。
4. **「MCP 接口」**：`tools/list` →`tools/call`；工具列表按订阅/等级标记 ✓ / 💳，含 `scenario_*`、`pipeline_*`。
5. **「意图受理」**：提交自然语言（如"机器狗巡检，雾天也要看得清"）→ 看鉴权证据 + 状态推进 + 执行轨迹回传；未授权步骤被标 🚫。
6. **「双向开放 · AF」**：注册第三方能力（设定价）→ 网络内部 Agent 经 `/internal/mcp` 发现并反向调用 → 台账与 70/30 分成。

详细的现场演示动线（25–30 分钟，对应测试项 T1/T2/T3）见 **[docs/demo-playbook.md](docs/demo-playbook.md)**。

---

## 四、核心概念

- **注册即签发 Key**：`POST /api/v1/register` 立即返回 API Key；订阅只记录权益（entitlement）。
- **认证 ≠ 授权**：未订阅 / 等级不足时身份认证通过但授权失败，返回 402（可订阅 / 升级 / 按次支付三条合法化路径）。
- **CAPIF 鉴权流水线**：每次 API/MCP/意图/场景调用都逐级执行 6 步鉴权（取出凭证→校验密钥→识别身份→检查接口权限→判定能力授权→记录审计；依据 3GPP CAPIF，AEF 对 API Invoker 鉴权），前端逐级点亮，未授权时在「授权判定」步变红。鉴权只在调用发生时展示，不在订阅页常驻。
- **调用去向**（路由判定，后端 `GET /api/v1/dispatch-table`）：化解「NEF 是 tool 粒度、后台只实现到场景粒度」的错配——命中后台声明过的 `service_id` 才经 NEF 出向网关转发（带显式请求信封），其余由 NEF 网元直接执行（参考实现），后台不会收到看不懂的请求。每次调用的鉴权回执末尾内联展示这一行。
- **两道意图鉴权**：第一道在 NEF 受理时按套餐/等级判定「意图受理资格」（免费裸账号不能发起意图——一条意图会触发网络侧多步编排，开销大）；第二道（逐能力鉴权）由网络侧 Planning Agent 在执行过程中进行（**当前为 NEF 模拟占位，待网络侧 PA 接入后替换**）。
- **场景/Pipeline 参数**：场景套餐与自助 Pipeline 一键运行时按主用例**预填逼真默认参数**（如 `area`），可在表单中修改；留空则用默认，调用始终带着像样的参数转发。
- **标准结果信封**：每次调用返回 `summary`（一行业务结论）+ `metrics`（关键指标）+ `result`（原始数据）+ `nef_auth`（鉴权回执）+ `billing`（按需）。
- **两个 MCP Server**：`/mcp`（对外，AF 的 AI Agent，Bearer 鉴权）与 `/internal/mcp`（对内，网络 Agent/网元，信任域内免 AF 鉴权，用于发现并反向调用第三方能力）。
- **能力分层**：`tier` = basic / advanced / premium；账号等级 `PLAN_TIERS` 决定免订阅可用的层级。

### 外部 AI Agent 直连 MCP

```bash
claude mcp add --transport http nef http://localhost:8000/mcp \
  --header "Authorization: Bearer <你的 api_key>"
```

### AF Agent 如何把用户的话变成 NEF 调用（规则 / 可选 LLM）

「AF 智能终端」演示的是这条链路：**终端用户**用自然语言找 AF 办事 → AF 的 AI Agent 理解意图 → 以 **tool 调用**方式调 NEF 能力 → 把结果答复用户。AF Agent 只负责「理解意图 + 选对工具」，它**不**自己实现网络能力。

规划端点 `POST /api/v1/af-agent/plan` 有两档实现，默认规则、可选 LLM：

1. **规则规划（默认，零依赖）**：按能力的 `intent_keywords` 做关键词匹配选工具，演示稳定、不依赖外网。
2. **LLM 规划（可选）**：配置环境变量后启用，把 NEF 的 `tools/list`（每个工具的 `name` + `description` + `inputSchema`）作为 **function-calling 的函数清单**喂给模型，由模型决定调哪个工具、填什么参数——这正是「让 LLM 理解并适配」的标准做法：模型不需要懂网络，只需读懂工具描述与入参 schema。

启用 LLM 规划：

```bash
pip install anthropic
# Windows PowerShell：
$env:ANTHROPIC_API_KEY = "sk-ant-..."
# 然后正常启动 server.py
```

未安装 `anthropic` 或未设 `ANTHROPIC_API_KEY` 时自动回落到规则规划（演示不会因缺 Key 而失败）。响应里的 `mode` 字段标明本次走的是 `rule` / `llm` / `meta`（元查询，如「有哪些能力」直接作答）。

> 真实对接网络侧时，意图的语义解析与工具编排由**网络侧 Planning Agent**负责（见上文「两道意图鉴权」）；本仓库的 AF Agent 规划是 **AF 侧**把用户话术映射到 NEF 工具的轻量实现，二者分属 AF 域与网络域。

---

## 五、项目结构

```
server.py          FastAPI 后端（REST + MCP + 内部发现 MCP + Intent + Pipeline + Skill 双文档 + 反向调用）
registry.py        第三方能力注册表 + 反向调用台账 + Intent 存储
skills.py          能力目录唯一数据源（32 能力·含规划中 / 9 场景套餐 / Agent-NF Tool 映射）
stubs.py           能力调用模拟返回
intent.py          Intent 安全受理 + 状态推进 + 网络内部 Agent 执行轨迹回传
static/index.html  单页前端（无框架，深空电信蓝主题，9 个页签）
docs/              demo-playbook.md（演示手册与对接需求）+ 设计文档
tests/             pytest 冒烟与 API 测试
```

> 提示：API Key / Pipeline / 第三方注册能力 / 反向调用台账 / Intent 均存于内存，重启即清空，需重新注册与订阅（账号名称存于浏览器 localStorage）。

---

## 六、能力目录（这些 tool 为什么应该有）

每个能力都有出处，不是凭空编的。来源分四级：

- 🟢 **已标准化**：现成的 3GPP NEF 北向 API，运营商网络今天就在暴露。
- 🔵 **6G 通感 ISAC**：对应 3GPP **TR 22.837《Integrated Sensing and Communication》** 列出的感知用例。
- 🟣 **6G 通算 / 算网融合**：边缘计算、网络 AI、算力网络的研究与产业方向（MEC、Rel-18 AI/ML、CAN）。
- ⚪ **垂直增值**：建在上面标准能力之上的产品化封装（面向具体行业场景）。

> Demo 中每个 tool 的执行均为 NEF 参考回显（见「场景方案」页路由分发表）。真实业务按 `docs/demo-playbook.md` 的对接契约接入即替换。

### 通感一体 ISAC
| 能力 | 说明 | 来源 |
|---|---|---|
| 目标检测 | 检测区域内人/车/无人机，返回类型·位置·置信度 | 🔵 TR 22.837 物体/入侵检测 |
| 目标追踪 | 持续追踪目标轨迹（位置·速度·航向） | 🔵 TR 22.837 无人机追踪 |
| 车流量感知 | 道路车流密度·车速·拥堵状态实时检测 | 🔵 TR 22.837 交通监测 |
| 环境重构 | 基于无线信号的三维空间建模 | 🔵 TR 22.837 环境监测 |
| 多源感知融合 | 3GPP 无线感知 + 摄像头/激光雷达融合，全天候 | 🔵+⚪ ISAC 增值 |
| 生命体征感知 · 手势识别 | 非接触呼吸/心率、手势姿态（规划中） | 🔵 TR 22.837 |

### 通算一体 Computing
| 能力 | 说明 | 来源 |
|---|---|---|
| 计算卸载 | 把模型部署/转码/渲染卸载到边缘或云 | 🟣 MEC / 3GPP EDGEAPP |
| AI 推理服务 | 调用网络侧已部署 AI 模型实时推理 | 🟣 Rel-18 AI/ML、网络 AI |
| 云渲染卸载 | XR/AR 渲染卸到边缘 GPU，回传渲染流 | 🟣 边缘 XR |
| 算力 QoS 保障 | 保障算力侧优先级/抖动，与通信 QoS 联动 | 🟣 算网融合 CAN/CATS |

### 连接服务 Connectivity
| 能力 | 说明 | 来源 |
|---|---|---|
| QoS 保障 | 为设备/应用保障时延·带宽·可靠性 | 🟢 AsSessionWithQoS (TS 29.522) |
| 事件订阅 | 订阅设备上下线/位置变更等网络事件 | 🟢 MonitoringEvent (TS 29.522) |
| 设备唤醒 | 唤醒省电模式的 IoT 设备 | 🟢 Device Triggering / NIDD (TS 29.122) |
| 移动性洞察 | 分析设备/用户群移动模式 | 🟢 NWDAF UE Mobility 分析 |
| 按需切片 | 按需创建/配置/释放网络切片 | 🟢🟣 Network Slice 开放 (NSCE) |
| 网络诊断 | 输出网络体验评分与优化建议 | ⚪ 基于网络状态的增值 |
| 多路径聚合 · 确定性时延 | ATSSS 聚合、TSC 有界时延（规划中） | 🟢 ATSSS / 5G-TSN |

### 定位服务 Location
| 能力 | 说明 | 来源 |
|---|---|---|
| 精准定位 | 亚米级室内外定位、实时位置/轨迹 | 🟢 LCS 定位 (TS 29.572) |
| 电子围栏 | 进出地理围栏时网络主动告警 | 🟢 MonitoringEvent 兴趣区域 |
| 轨迹预测 | 基于历史轨迹预测未来位置（规划中） | 🟣 NWDAF + 定位 |

### 数据服务 Data
| 能力 | 说明 | 来源 |
|---|---|---|
| 网络分析 | 异常检测/容量预测/UE 行为/业务体验 | 🟢 NWDAF (TS 23.288) |
| 数据服务 | 覆盖图/热力图/性能统计等数据集 | 🟢🟣 数据开放 / AnalyticsExposure |
| 车流量预测分析 | 基于车流感知预测未来车流与拥堵 | ⚪ ISAC+分析 增值 |
| 数字孪生数据底座 | 向数字孪生平台供给网络感知数据（规划中） | 🟣 网络数字孪生 |

### 生态服务 Ecosystem
| 能力 | 说明 | 来源 |
|---|---|---|
| 能力注册 | 把第三方能力注册到网络（双向开放） | 🟢 CAPIF API 发布 (TS 29.222) |
| 身份服务 | 为 Agent/应用颁发网络数字身份 | 🟢🟣 CAPIF 安全 / AKMA |
| 安全检查 | 设备/连接安全状态检查 | ⚪ 增值 |
| 生态收益结算 | 第三方能力被调用后自动分账（规划中） | ⚪ 计费结算 |

---

## 七、推送到 GitHub

本仓库已是 git 仓库。新建远程并推送：

```bash
# 1. 在 GitHub 网页上 New repository 建一个空仓库（不要勾选 README/.gitignore）
# 2. 关联远程并推送当前分支
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin feature/demo-redesign      # 或先 git checkout -b main 再推 main
```

若已安装 GitHub CLI（`gh`），一条命令即可建仓并推送：

```bash
gh repo create <仓库名> --public --source=. --remote=origin --push
```
