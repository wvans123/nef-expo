# 选定网络能力与场景目录发布

分类：接口参考。更新：2026-09-17。

用途：将 NEF 能力超市中明确选中的本地原子能力或场景元数据交给网络目录。它与农场 MCP 登记、账号订购通知是三个不同方向；本接口不发布账号购买信息，也不调用 PA/CA 执行业务。

**状态：代码与本地模拟 HTTP 对端测试已完成，真实 ARF/NRF 的地址、字段及接收规则待同事确认。上传不会更新已有进程，新机器按 README 启动后验收。** 此处是本项目契约，不是 3GPP NRF NFRegister 的实现，不能直接假设 NRF 会接受。

## 请求

| NEF 路径 | 用途 |
|---|---|
| `POST /api/v1/network/catalog/publication` | 只预览发布正文，不联系目录 |
| `POST /api/v1/network/catalog/publish` | 向运维配置的目录地址实际发送正文 |

两者使用相同 JSON：

```json
{
  "capability_ids": ["target_detection"],
  "service_ids": ["robot_patrol"]
}
```

带 `Authorization: Bearer <NEF账号Key>`，要求 `af:register` scope；公网另需 Access 凭据。只选能力或只选场景均可，但不能全空。能力最多 64 项，场景最多 16 项；重复、未知、规划中能力或额外字段返回 422。无 Key 为 401，scope 不足为 403。

请求体不能传接收地址、凭据或任意元数据。新部署配置在 `config/integration.local.json` 的 `registry` 中；旧 `NEF_REGISTRY_CONFIG` 显式覆盖仍兼容。`nef_base_url` 指向网络可访问的 NEF 地址，例如 `http://<NEF电脑IP>:8069`，`publish_url` 是目录接收地址，`token_env` 仅引用服务端凭据变量。预览也要求有效 `nef_base_url`；缺失返回 503 `gateway_not_configured`。

## 发布正文

| 字段 | 含义 |
|---|---|
| `type` | 固定 `nef_catalog_publication` |
| `schema_version` | `1.0` |
| `source` | `NEF` |
| `catalog_id` | 从 NEF 公开入口生成的稳定目录标识 |
| `revision` | 规范化正文的 SHA-256 摘要 |
| `update_mode` | `upsert_selected`；只更新所选项，不表示删除未选目录项 |
| `items` | 所选能力和场景的真实目录声明 |
| `access` | NEF 账号 Bearer、需要权益，以及真实调用头 `X-NEF-Execution: live` |
| `execution_readiness` | `not_verified`；目录声明不证明真实执行可用 |

原子能力项包含 `kind=capability`、`id/name/description/status/source/category`、`inputSchema`、`standard_basis` 及 API/Tool 入口。场景项包含 `kind=scene`、`id/name/description/status/source`、`modes/components` 及其实际支持的 Intent/API/Tool 入口。`interfaces` 中带 `mode/method/url`，工具入口带准确 `tool_name`，适用时带 `inputSchema`。

不导出其他账号的私有 MCP 工具、用户订阅、模型 Key、上游真实执行地址或任何 Bearer 凭据。AF 登记的目录报文另见[农场平台联调](farm-integration.md)，不把 AF 服务冒充 NEF 原子能力。

## 接收与重试

预览返回完整正文；发布时向 `publish_url` POST 同一结构，不跟随重定向。仅当对方 HTTP 成功且 JSON 明确为 `{"accepted":true}` 时，NEF 才返回 `sync_status=synced`；其他成功响应记为 `submitted`。返回另含 `catalog_id/revision/item_count/accepted`，并不宣称目录中的能力可以执行。

配置缺失、无效、凭据缺失或上游失败均不标记成功。请求不是后台自动同步；调用方需先核对实际回执再决定重发，接收方可按 catalog_id 与 revision 识别重复。这个接收规则与订购回调的 2xx 送达判定不同，不能混用。

## 联调顺序

1. 网络同事确认接收方究竟是 ARF、NRF 或其适配服务，提供实际 POST 地址、认证方式、字段样例和确认格式。
2. NEF 运维配置地址及凭据，先用预览核对选中的能力、入口 URL 与 schema。
3. 在获准测试目录发布一项能力和一个场景，核对目录存储及明确接收回执。
4. 另行验收目录消费者到 NEF 的真实调用与权益。发布成功不替代执行验证，也不授予账号新的订阅。
