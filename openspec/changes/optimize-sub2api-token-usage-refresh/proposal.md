# 提案：optimize-sub2api-token-usage-refresh

## 背景

生产 `/token-usage` 的 SPA 外壳可在 0.4 秒内出现，但新的时间范围首次读取核心数据约需
3.8 秒，逐 Key 增强约需 8.5 秒。当前缓存到期后会用 partial 覆盖 complete，且每个查询
各自创建并发池；不同范围同时刷新可能把配置的并发上限放大。缓存也没有容量淘汰。

## 提案

- 完整快照到期后继续返回旧数据，并在后台 single-flight 刷新，不回退到 partial。
- 冷启动分阶段发布当前窗口、对比窗口和延迟/错误增强结果。
- 对所有 Sub2API 请求使用进程级共享并发闸门，并并行读取互不依赖的核心端点。
- 缓存版本与 Key inventory，给所有缓存增加过期清理和容量上限。
- 前端对 partial 刷新使用有界退避，减少重复下载完整大响应。

## 影响

影响 `server/token_usage_sub2api.py`、Token Usage 前端请求状态、相关测试、ADR、模块地图和
board spec。保持 schema v2、URL、认证和 USD 统计语义；不修改 Sub2API、Agent 遥测、SQLite
或工作流图，本次为 `no_graph_change`。
