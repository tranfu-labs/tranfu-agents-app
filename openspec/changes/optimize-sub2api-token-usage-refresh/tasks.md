# 任务：optimize-sub2api-token-usage-refresh

- [x] 增加冷/热/过期/并发/分阶段/有界缓存测试。
- [x] 实现共享上游并发闸门和 metadata/trend 并行读取。
- [x] 实现 complete stale-while-revalidate 与有界缓存。
- [x] 实现当前、对比、延迟/错误分阶段增强。
- [x] 前端 partial 轮询改为有界退避并显示后台刷新。
- [x] 合并 spec delta，更新 ADR、模块地图和操作约束。
- [x] 运行全量 Python/coverage、前端 unit/lint/build 与生产只读性能复测。
