# ADR-0026 Sub2API Token Usage 由 TranfuAgents BFF 提供稳定契约

## 状态

Accepted

## 背景

Token Usage 页面原先直接适配 NewAPI 风格的聚合接口，并依赖 Access Token、`New-Api-User`、Cookie 和隐含的 `500000 quota = 1 USD` 换算。Sub2API v0.1.x 已改为版本化 Admin API，认证、字段和统计能力不同；若把变化继续堆在页面或路由里，上游升级会直接破坏浏览器契约并扩大密钥泄漏风险。

## 决策

- 不修改或 Fork Sub2API。浏览器只访问 TranfuAgents `/api/token-usage`、`/errors` 和 `/status`。
- `server/token_usage_sub2api.py` 是 Sub2API 协议的唯一适配器，使用 `/api/v1/admin/*`。认证优先使用服务端 `x-api-key`；迁移期允许显式复用现有 `TF_TOKEN_USAGE_ACCESS_TOKEN`，按网页登录协议发送 `Authorization: Bearer` 和 `X-Admin-UI-Request`。路由不持有上游聚合规则。
- schema v2 以 `api_key_id` 为稳定身份，金额字段明确为 USD。当前 inventory 与当前/上一窗口 trend 取并集，历史数据不按 Key 当前 `user_id` 再过滤。
- 冷缓存先返回 inventory/trend 核心数据，逐 Key snapshot/stats/errors 后台增强；当前窗口金额先于对比、延迟和错误阶段发布，未知字段为 `null`。当前窗口缓存 60 秒，闭合历史缓存 15 分钟，成功旧缓存最多 stale-if-error 24 小时。
- complete 缓存过期后继续立即返回旧完整数据并在后台刷新，不用 partial 覆盖；刷新失败使用冷却窗口，避免前端轮询放大故障流量。缓存按 24 小时和固定容量淘汰。
- 相同查询 single-flight，所有查询、错误明细和后台任务共享进程级并发闸门，默认总并发最多 4；version/inventory 使用独立短缓存，互不依赖的 metadata/trend 并行读取。trend/snapshot/stats 按 Sub2API 实际日期参数复用跨分钟组件缓存，errors 保留精确时间范围。Key 明文在 inventory 处理入口立即移除，日志、缓存、错误、CSV 和响应不得包含 Admin Key 或完整 API Key。
- `legacy_newapi` 仅作为显式回滚 provider 保留一个发布周期。新链路连续成功 7 天并完成一次候选版本升级演练后，另行删除旧 Header、Cookie/Access Token 配置、单位换算和兼容测试。
- 网页登录 Access Token 有过期时间，只作为迁移兼容且 401 必须显式失败；不得自动降级到 Demo。生产建立 Admin Key 并连续稳定 7 天后，删除 Sub2API Access Token 兼容分支。
- Sub2API 候选版本必须在 Coolify 预发布实例通过只读响应契约 workflow；版本号仅记录，真实字段契约才是晋升条件。生产按镜像 digest 晋升并保留上一 digest。

## 后果

Sub2API 的兼容变化集中在一个模块，浏览器契约和密钥边界稳定；上游慢或部分失败时页面仍可展示已知事实且不会伪造 0。代价是首次冷读取仍存在短暂 partial 状态，后台刷新期间允许展示最多一个刷新周期的旧完整数据，并需要维护契约 fixture、预发布 Secret 和候选升级门禁。未来破坏性变更不会自动兼容，但不能通过门禁静默进入生产。
