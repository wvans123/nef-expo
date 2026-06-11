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
3. 依次体验 8 个 Tab：API 调试 / MCP 工具（只列已订阅）/ Intent 意图 / Skill 文档（AF/伙伴 Agent 视图切换）/ 能力编排器（拖拽组 Pipeline）/ AF 注册
4. Intent 转发：提交自然语言需求 → 查看 Bearer API Key 鉴权、账号识别、scope 校验、审计 ID → 获取伙伴网络 Agent 的任务 ID 与状态地址
5. AF 反向调用：「AF 注册」Tab 注册能力 → 点「⚡ 模拟网络调用」查看网络调用链路与台账

## 能力超市与调用规则

- 能力以磁贴墙展示（32 项，按 6 大类分组），「规划中」能力标灰展示，不可订阅或调用
- MCP `tools/list` 只返回当前 API Key 已订阅的能力 + 第三方注册能力 —— 订阅了什么，工具箱里才有什么
- 鉴权采用 Bearer API Key，并演示凭证校验、账号识别、scope 授权和请求审计 ID
- Intent 链路：NEF 鉴权与受理 → 转发合作伙伴网络 Agent → 返回伙伴任务 ID 和状态地址。语义理解、业务执行、状态与结果由伙伴系统负责

## 结构

```
server.py   FastAPI 后端（REST + MCP + Intent + Pipeline + Skill 双文档 + 反向调用）
registry.py 第三方能力注册表 + 反向调用台账
skills.py   能力目录唯一数据源（32 能力·含 9 项规划中 / 8 场景套餐 / Agent-NF Tool 映射）
stubs.py    能力调用模拟返回
intent.py   Intent 安全受理与合作伙伴网络 Agent 转交回执
static/index.html  单页前端（无框架，深空电信蓝主题）
tests/      pytest 冒烟与 API 测试
```

注意：API Key / Pipeline / 第三方注册能力 / 反向调用台账均存于内存，重启服务后清空，需重新订阅与注册（账号本身存于浏览器 localStorage）。
