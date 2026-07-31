# 设计：sub2api-token-usage-adapter

## 架构边界

浏览器只调用 TranfuAgents 同源 API。`server/token_usage_sub2api.py` 负责 Sub2API 协议、
校验、脱敏、聚合和缓存；`server/routes/token_usage.py` 只保留 HTTP 参数与 legacy NewAPI
回滚路径。Token Usage 数据不进入 Agent 遥测数据库。

## 上游读取

- 认证优先使用 `x-api-key`；迁移期兼容网页登录 Access Token，对应 `Authorization: Bearer` 与 `X-Admin-UI-Request`。配置为 base URL、服务端凭证、Admin user ID、IANA 时区和最大并发。
- Key inventory 处理 `/admin/users/{id}/api-keys` 全部分页，并在进入内存模型前删除 `key`。
- 当前与上一时间窗使用 `api-keys-trend` 发现稳定 `api_key_id`；当前 inventory 与历史趋势取并集。
- 每个 Key 使用 `dashboard/snapshot-v2` 的 trend/models，强制 `include_stats=false`；当前窗口
  另用 `usage/stats` 取得延迟。
- 错误先分页读取 `/admin/ops/errors` 并按 Key 聚合；超过 10,000 条时按 Key 查询 total。
- 未知新增字段允许通过；缺少 envelope 或必需 identity/metric 字段视为契约失败。

## BFF 契约

`GET /api/token-usage` 保留既有查询参数，返回 `schema_version=2`、当前数据、上一周期、
`completeness`、`freshness` 与上游版本。规范字段使用 `api_key_*`、`actual_cost_usd`、
`quota_*_usd`、明确 token/request/error/latency 字段；旧 `token_id/token_name/quota` 仅作
一个发布周期的兼容别名。

`GET /api/token-usage/errors` 使用 `api_key_id`，兼容 `token_id`。`GET /api/token-usage/status`
只暴露版本、能力、最近成功时间、缓存年龄和安全错误码。

## 可用性与负载

- 当前范围缓存 60 秒；已闭合历史范围缓存 15 分钟；成功缓存最多陈旧使用 24 小时。
- 相同 cache key 使用 single-flight；逐 Key请求最大并发默认 4，每个请求最多重试一次。
- 冷缓存允许先返回 core/partial，增强刷新继续执行；缺失指标为 null，不伪造为 0。
- 前端不再预取其它粒度，比较周期由一次 BFF 请求返回。
- 401/403、核心 404、envelope 破坏且无可用旧缓存时返回 502；不自动回退 Demo/NewAPI。

## 升级门禁

只读脚本针对候选实例探测 health、version、inventory、trend、snapshot、stats、errors；版本仅记录，
实际响应契约决定是否允许晋升。默认在 Coolify 预发布实例运行，通过后按镜像 digest 晋升，失败保留
上一生产 digest。

## 权衡与退出条件

不修改 Sub2API 使上游升级简单，但完整页面需要 N 个 Key 的聚合调用，因此必须限并发、缓存和
禁止前端预取。legacy NewAPI 只用于显式回滚；Sub2API 连续成功 7 天且完成一次候选升级演练后删除。
