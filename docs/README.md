# 文档索引

更新：2026-09-23。主线：能力供给 → 套餐定义 / MCP 连接发现 → 显式发布 / 取消发布 → 场景订阅 → Intent 与文字结果。首页按四种 toolType 展示已可用能力，底部支持同步/撤回及状态核对，TRF 目录来源切换仅在运维折叠设置中；不展示规划中及旧生态服务。API / MCP 北向接入作为并行开放方式保留。

## 用户指南
- [项目说明](../README.md)：换电脑下载、前台启动与 Windows 独立后台任务、统一 POST 地址配置和修改接口的文件位置；维护中，部署入口以此为准。

## 运行手册
- [curl 联调手册](reference/manual-curl.md)：无 Key 回传、自查、开放 MCP 登记、订购/取消与现场排查；bash 和 PowerShell 命令。公开文档使用地址占位符，真实 IP 填本机配置。
- [演示手册](demo-playbook.md)：Windows 独立后台、跨机器联调和 Tunnel；2026-09-22 已重启加载首页四类同步，旧内存账号清空。记录定向测试、电脑页面验证和待提供的真实服务地址；之前验收保留为历史快照。

## 架构 / 设计决策
- [展示体验设计](superpowers/specs/2026-06-11-frontend-demo-redesign-design.md)：原版七个可见页签、真实基础能力组合、确定性配置检查、LLM 推荐与确认、声明式套餐、TRF 适配边界、MCP Server 注册和发现、网络内部经 NEF 调用 AF 的代理入口 / 发布契约、Intent 文字结果；内部生产接口待对接。
- [鉴权与场景授权设计](superpowers/specs/2026-06-15-dynamic-auth-and-dispatch-design.md)：维护 5G AF–NEF / CAPIF 参考、场景提供方与授权责任、6G 候选扩展以及真实回执边界；已实施场景订阅判定；标准安全接入与资源策略待实现。

## 接口参考
- [基础能力标准复核](../README.md#六能力目录与标准复核)：逐项分类及官方依据；产品接口不能等同于标准北向 API。
- [智能推荐配置](../config/composer.example.json)：远程服务、模型和 Responses 协议沿用既有配置，项目推理档位降为 low；Key 使用服务端环境变量。能力池提示词、可选约束、新错误分类及运行代码加载边界见[演示手册](demo-playbook.md#智能编排准备与现场操作)。
- [场景接口对接说明](reference/integration.md)：无 Key 共享回传、自查、状态 / 数据 / 后端媒体接收、机器狗 text/plain Intent 与 GET/POST 结果拉取；接口格式来自使用者记录，本机仅做模拟对端验证。
- [套餐订购通知与订阅查询](reference/subscription-query.md)：场景所选子能力同步授权、权益来源与取消保留、避免子能力重复计费；固定 `subscriberId=subscriber-001`、折扣计价、取消 DELETE、通知过滤与回包；后端兼容空选择，页面至少选一项；查询另含 external_tool_subscriptions。
- [统一对接配置](../config/integration.example.json)：`start.py` 自动生成本地配置，集中设置订购、折扣、开放 MCP、TRF 发布及 Intent / 结果地址；已有 local 文件不覆盖、不上传。
- [旧订购通知配置](../config/subscription.example.json)：兼容独立配置模式，新部署优先使用统一文件。
- [TRF MCP Server 契约与能力映射](reference/network-catalog.md)：内部三分类 MCP Server 登记（23 项能力映射到 3 个以 `/mcp` 结尾的端点）、统一七字段 POST、GET 服务身份核对、Server/能力分开计数、旧地址迁移与逐能力记录撤回；真实 IP/回包待提供。
- [农场平台联调](reference/farm-integration.md)：套餐查询、无 Key MCP 登记发现、显式发布/撤回及网络代理调用；同一接入流程用于巡检小车，真实地址待提供。
- [网络目录配置](../config/registry.example.json)：运维侧 TRF MCP 集合地址和独立 NEF 代理入口、内部调用方授权及 MCP 服务允许列表示例；不含实际密钥。
- [配置模板](../config/bridge.example.json)：从接口契约配套维护的可复制配置；示例域名不可用，必须按实际接口替换。

## 报告 / 快照
- [内网变更同步](sync/README.md)：2026-09-20 按另一台文字说明重建，记录基线、保留功能、启动删除开关、发布前复验及公开地址脱敏；不是原始 patch。

## 历史实施计划
- [原前端实施计划](superpowers/plans/2026-06-11-frontend-demo-redesign.md)：历史记录，不作为当前实施清单。

## 展示资产
- [原版活动工作台](../static/index.html)：原能力超市、订阅弹窗、拖拽编排、API / MCP 调试与鉴权交互上的增量更新；七个可见页签，隐藏 Skill / 场景方案和 AF 终端。
- [增量控制逻辑](../static/workbench.js) / [增量样式](../static/workbench.css) / [订购交接](../static/purchase.js)：场景订阅与 Intent、账号跳转、可选网络能力范围、通知状态与重试、网络目录、自动准备调用页回传接口；沿用 index.html 原样式。
- [首页 TRF 交互](../static/trf-catalog.js)：四类能力、登记圆点、同步/撤回和 TRF 只读展示。
- [旧目录发布交互](../static/catalog-ui.js)：兼容资产，活动页不再加载；新 TRF 操作由 workbench.js 负责。
- [工具发现客户端](../static/showcase-mcp.js) / [结果语义](../static/showcase-story.js)：活动工作台复用的纯协议和回执模块。
- [旧展示书签](../static/showcase.html)：兼容跳转至原工作台，不再维护第二套活动界面；其余未引用的 showcase 样式和控制脚本为旧迭代资产。
