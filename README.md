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
- **CAPIF 鉴权流水线**：每次 API/MCP/意图/场景调用都逐级执行 7 级鉴权（依据 3GPP CAPIF，AEF 对 API Invoker 鉴权），前端逐级点亮，未授权时在「授权判定」级变红。
- **路由分发表**（`GET /api/v1/dispatch-table`）：化解「NEF 是 tool 粒度、后台只实现到场景粒度」的错配——NEF 只把后台声明过的 `service_id` 转发出去（带显式请求信封），没实现的 tool 由 NEF 参考回显兜底，后台不会收到看不懂的请求。
- **标准结果信封**：每次调用返回 `summary`（一行业务结论）+ `metrics`（关键指标）+ `result`（原始数据）+ `nef_auth`（鉴权回执）+ `billing`（按需）。
- **两个 MCP Server**：`/mcp`（对外，AF 的 AI Agent，Bearer 鉴权）与 `/internal/mcp`（对内，网络 Agent/网元，信任域内免 AF 鉴权，用于发现并反向调用第三方能力）。
- **能力分层**：`tier` = basic / advanced / premium；账号等级 `PLAN_TIERS` 决定免订阅可用的层级。

### 外部 AI Agent 直连 MCP

```bash
claude mcp add --transport http nef http://localhost:8000/mcp \
  --header "Authorization: Bearer <你的 api_key>"
```

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

## 六、推送到 GitHub

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
