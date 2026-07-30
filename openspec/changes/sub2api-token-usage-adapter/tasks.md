# 任务：sub2api-token-usage-adapter

- [x] 实现 Sub2API Admin 客户端、严格 envelope 校验、脱敏和错误分类。
- [x] 实现 inventory/trend/snapshot/stats/errors 聚合、历史 Key union 与 USD schema v2。
- [x] 实现限并发、single-flight、60 秒/15 分钟缓存和 24 小时 stale-if-error。
- [x] 改造 `/api/token-usage`、`/errors` 并新增 `/status`，保留有退出条件的 legacy aliases。
- [x] 前端消费 USD/完整度字段，删除 500000 换算和其它粒度预取。
- [x] 增加 v0.1.166 fixtures、契约失败、分页、缓存、并发、历史归属和密钥泄漏测试。
- [x] 增加只读契约检查脚本与手动 GitHub workflow。
- [x] 更新 Compose、环境变量示例、README、module map、ADR 和升级说明。
- [x] 运行 pytest、coverage、前端 unit/build、编译和安全扫描。
- [ ] 在 Coolify 预发布实例运行只读契约 workflow，并完成候选 digest 晋升/回滚演练与生产验收。
