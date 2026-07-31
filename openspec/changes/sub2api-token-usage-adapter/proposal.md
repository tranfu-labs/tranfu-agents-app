# 提案：sub2api-token-usage-adapter

## 背景

生产分发平台已从 NewAPI 切换为 Sub2API v0.1.166。现有 Token Usage BFF 仍调用
`/api/data/keys`、`/api/log/` 并发送 `New-Api-User`，因此生产 `/api/token-usage`
稳定返回上游 404。Sub2API 已提供版本化 Admin API，但认证、响应 envelope、费用单位和
聚合粒度均与 NewAPI 不同。

## 提案

- 不修改 Sub2API；在 TranfuAgents 服务端建立唯一的 Sub2API 只读适配层。
- `/api/token-usage` 升级为 schema v2，使用明确 USD 字段并短期保留旧字段别名。
- 通过受控并发、single-flight、按范围缓存和 stale-if-error 聚合 Key、趋势、模型、延迟与错误。
- 新增只读状态端点和候选 Sub2API 契约检查，阻止不兼容版本进入生产。
- Admin API Key 只存在服务端环境变量，任何响应、日志、CSV 和缓存均不得包含明文 Key。

## 影响

- `server/`：新增 Sub2API 客户端与聚合模块，Token Usage 路由改为稳定 BFF。
- `frontend/`：消费 USD 字段，停止粒度预取放大，显示完整度、陈旧缓存和降级状态。
- 部署/CI：新增 Sub2API 配置、只读契约门禁和升级回滚说明。
- 不影响 Agent 事件协议、shim、SQLite、Pods/Agents/SKILLS 页面或 Sub2API 源码。
