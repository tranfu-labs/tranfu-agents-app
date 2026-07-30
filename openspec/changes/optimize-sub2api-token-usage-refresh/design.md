# 设计：optimize-sub2api-token-usage-refresh

## 方案

### 缓存与异步刷新

- 冷缓存同步读取 metadata 与当前/对比 trend，返回 core/partial，并启动后台增强。
- complete 缓存超过 live/history TTL 后，在 24 小时可用期内立即返回并标记
  `refreshing=true`，后台执行 single-flight 全量刷新；只有真正冷启动才展示 partial。
- 后台刷新失败保留旧完整快照并标记 stale-if-error，成功后原子替换。
- 缓存写入时清理超过 24 小时的条目，并按最旧写入时间限制最大条目数。
- trend、逐 Key snapshot 和 stats 按 Sub2API 实际使用的日期参数、Key 与粒度建立组件缓存，
  使跨分钟的新 BFF 查询复用 60 秒内的上游结果；errors 继续使用精确时间戳。

### 并发与阶段发布

- Sub2APIClient 的所有网络请求共享按上游配置隔离的 bounded semaphore，使不同查询、错误
  明细和后台刷新合计不超过 `TF_TOKEN_USAGE_MAX_CONCURRENCY`。
- version 与 inventory 并行读取并缓存 5 分钟；当前与对比 trend 并行读取。
- 逐 Key snapshot 仍由有界线程池读取。当前 snapshot 完成后立即写入 partial 缓存；对比
  snapshot 完成后再次写入。latency 与当前/对比错误统计最后并行读取，再原子发布 complete。
- 单 Key latency 失败只令该字段未知，不丢弃已经成功的金额、token 和模型数据。

### 前端刷新

partial 状态从固定 1.5 秒轮询改为 1.5/3/5 秒有界退避；complete 的后台刷新保持已有数据，
状态显示 `LIVE` 刷新标识，不清空金额和模型。

## 权衡

没有直接提高默认并发，因为多个浏览器和不同查询会把每查询并发放大。共享闸门优先保证上游
负载可控；并行化只改变互不依赖请求的调度。进程内缓存不跨实例共享，符合当前单容器部署边界。

## 风险

- 后台刷新期间展示的数据最多陈旧一个刷新周期；响应明确给出 cache age 和 refreshing。
- 分阶段写入增加并发状态复杂度；测试覆盖同键 single-flight、不同键全局并发、失败保留和
  中间状态不覆盖旧 complete。
- 回滚只需恢复本变更，schema v2 和上游凭证均不改变。
