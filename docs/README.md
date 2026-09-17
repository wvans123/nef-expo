# 文档索引

更新：2026-09-17。主线：能力供给 → 套餐定义 / MCP 能力源注册 → 网络目录同步 → 场景订阅 → Intent 与文字结果。API / MCP 北向接入作为并行开放方式保留。

## 用户指南
- [项目说明](../README.md)：安装、入口、运行及真实 / 模拟边界；维护中。

## 运行手册
- [演示手册](demo-playbook.md)：智能编排、五分钟展示主线、跨机器联调和 Cloudflare Tunnel 部署；包括 Access、HTTPS / TLS、限定 API 路径的兼容规则、验收与回滚。2026-09-17 已恢复本机服务并核验 Tunnel 就绪、本机接口和公网未授权拦截；此前登录后页面已验证，有效机器凭据调用及回传仍待验收；旧九页签流程明确归档。

## 架构 / 设计决策
- [展示体验设计](superpowers/specs/2026-06-11-frontend-demo-redesign-design.md)：原版七个可见页签、真实基础能力组合、确定性配置检查、LLM 推荐与确认、声明式套餐、TRF / ARF 适配边界、MCP Server 注册和发现、网络内部经 NEF 调用 AF 的代理入口 / 发布契约、Intent 文字结果；内部生产接口待对接。
- [鉴权与场景授权设计](superpowers/specs/2026-06-15-dynamic-auth-and-dispatch-design.md)：维护 5G AF–NEF / CAPIF 参考、场景提供方与授权责任、6G 候选扩展以及真实回执边界；已实施场景订阅判定；标准安全接入与资源策略待实现。

## 接口参考
- [基础能力标准复核](../README.md#六能力目录与标准复核)：逐项分类及官方依据；产品接口不能等同于标准北向 API。
- [智能推荐配置](../config/composer.example.json)：远程服务、模型和 Responses 协议沿用既有配置，项目推理档位降为 low；Key 使用服务端环境变量。能力池提示词、可选约束、新错误分类及运行代码加载边界见[演示手册](demo-playbook.md#智能编排准备与现场操作)。
- [场景接口对接说明](reference/integration.md)：直接交付场景同事的简明说明，包含统一回传地址、状态 / 数据 / 媒体示例、执行接口资料清单及联调顺序；回传已实现，实际内部执行接口待联调。
- [套餐订购通知与订阅查询](reference/subscription-query.md)：唯一维护跳转账号、POST `subscriberId/servicePlan`、可选 `networkCapabilities`、价格、失败重试和 1.1 已购详情查询。通知已通过模拟对端测试但运行服务尚未加载；实际回调地址及价格待提供。查询本机可用，跨机有效 Access 凭据待验收。
- [订购通知配置](../config/subscription.example.json)：运维侧回调地址、账号允许列表、价格及服务端凭据变量模板；默认不外发。
- [选定网络目录发布](reference/network-catalog.md)：显式选择本地能力/场景，预览并发布元数据到目录；不是标准 NRF 注册，真实 ARF/NRF 接口待确认，当前运行进程尚未加载。
- [农场平台联调](reference/farm-integration.md)：面向农场开发同事的双向联调步骤，覆盖套餐查询、MCP 注册 / 发现 / 网络发布、网络经 NEF 访问农场工具、双方配置与验收清单；真实农场与目录地址待提供。
- [网络目录配置](../config/registry.example.json)：运维侧 TRF / ARF 拉取 / 发布接口和 NEF 网络可达入口、内部调用方授权及 MCP 服务允许列表示例；不含实际密钥。
- [配置模板](../config/bridge.example.json)：从接口契约配套维护的可复制配置；示例域名不可用，必须按实际接口替换。

## 历史实施计划
- [原前端实施计划](superpowers/plans/2026-06-11-frontend-demo-redesign.md)：历史记录，不作为当前实施清单。

## 展示资产
- [原版活动工作台](../static/index.html)：原能力超市、订阅弹窗、拖拽编排、API / MCP 调试与鉴权交互上的增量更新；七个可见页签，隐藏 Skill / 场景方案和 AF 终端。
- [增量控制逻辑](../static/workbench.js) / [增量样式](../static/workbench.css) / [订购交接](../static/purchase.js)：场景订阅与 Intent、账号跳转、可选网络能力范围、通知状态与重试、网络目录、自动准备调用页回传接口；沿用 index.html 原样式。
- [工具发现客户端](../static/showcase-mcp.js) / [结果语义](../static/showcase-story.js)：活动工作台复用的纯协议和回执模块。
- [旧展示书签](../static/showcase.html)：兼容跳转至原工作台，不再维护第二套活动界面；其余未引用的 showcase 样式和控制脚本为旧迭代资产。
