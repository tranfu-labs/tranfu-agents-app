# Board spec delta：Sub2API Token Usage 稳定契约

- `/api/token-usage` MUST 作为外部分发平台的唯一浏览器可见边界，浏览器不得持有分发平台凭证。
- Sub2API provider MUST 使用 `/api/v1/admin/*`；认证 MUST 优先使用 `x-api-key`，迁移期 MAY 显式使用服务端登录 Access Token，并在处理 inventory 时移除明文 Key。
- schema v2 MUST 使用明确 USD、Token、请求、错误和毫秒单位；缺失增强指标 MUST 表示未知而非 0。
- 聚合 MUST 按稳定 `api_key_id`，不得因 Key 当前 `user_id` 变更遗漏历史数据。
- 当前/历史缓存、single-flight 和并发上限 MUST 防止页面轮询放大为无界上游请求。
- 上游失败 MAY 返回 24 小时内最后一次成功快照，但 MUST 标记 stale；无快照时 MUST 明确失败。
- Sub2API 升级 MUST 先通过只读响应契约检查；未知新增字段兼容，缺少必需字段阻止晋升。
