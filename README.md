# 6G NEF 能力开放平台 Demo

## 运行

```bash
pip install -r requirements.txt
python server.py
```

打开 http://localhost:8000

## 快速体验

1. 右上角「注册账号」→ 输入名称（如 `developer_zhang`）
2. 能力超市点击任意能力/套餐 → 一键确认支付 → 自动生成 API Key
3. 依次体验 8 个 Tab：API 调试 / MCP 工具 / Intent 意图 / Skill 文档（外部/内部视图切换）/ 能力编排器（拖拽组 Pipeline）/ AF 注册

## 结构

```
server.py   FastAPI 后端（REST + MCP + Intent + Pipeline + Skill 双文档）
skills.py   能力目录唯一数据源（17 能力 / 5 套餐 / Agent-NF Tool 映射）
stubs.py    能力调用模拟返回
intent.py   Intent → Skill → Agent → Tool 链路
static/index.html  单页前端（无框架，暗色主题）
```

注意：API Key / Pipeline 存于内存，重启服务后需重新订阅（账号本身存于浏览器 localStorage）。
