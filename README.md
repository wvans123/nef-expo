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
4. AF 反向调用：「AF 注册」Tab 注册能力（填 Intent 关键词如 `质检`）→ 点「⚡ 模拟网络调用」看链路点亮；或到 Intent Tab 输入含关键词的意图，回来看台账自动增长

## 结构

```
server.py   FastAPI 后端（REST + MCP + Intent + Pipeline + Skill 双文档 + 反向调用）
registry.py 第三方能力注册表 + 反向调用台账
skills.py   能力目录唯一数据源（17 能力 / 5 套餐 / Agent-NF Tool 映射）
stubs.py    能力调用模拟返回
intent.py   Intent → Skill → Agent → Tool 链路（含第三方能力反向调用）
static/index.html  单页前端（无框架，深空电信蓝主题）
tests/      pytest 冒烟与 API 测试
```

注意：API Key / Pipeline / 第三方注册能力 / 反向调用台账均存于内存，重启服务后清空，需重新订阅与注册（账号本身存于浏览器 localStorage）。
