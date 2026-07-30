## MODIFIED Requirements

### Sub2API Token Usage 缓存与刷新

- 冷缓存 MUST 先返回 inventory/trend 核心数据并标记 partial；当前窗口增强完成后 MUST 在
  对比、延迟和错误统计完成前可见。
- complete 缓存到期 MUST 继续提供旧完整数据并后台 single-flight 刷新，不得退回 partial；
  刷新状态、缓存年龄和失败降级 MUST 可诊断。
- 所有 Sub2API 请求 MUST 在进程级共享配置的并发上限，不得因不同查询或后台任务叠加而放大。
- 缓存 MUST 有过期淘汰和容量上限；version/inventory MAY 使用独立短缓存。
- trend/snapshot/stats MAY 按上游实际日期参数建立组件缓存以复用跨分钟查询；errors 的缓存键
  MUST 保留精确开始和结束时间。
- 前端 MUST 对 partial 同步使用有界退避，不得固定高频下载未变化的完整 payload。

### 可验证行为

- complete 条目超过 60 秒后首次请求立即返回旧完整数据且只启动一次后台刷新。
- 两个不同范围同时增强时，观测到的上游网络总并发不超过配置值。
- 当前窗口 snapshot 完成、对比或错误仍阻塞时，当前 Key 金额和模型已经可读取。
- 后台刷新失败时旧完整金额仍可读取并标记 stale；缓存条目数不超过配置上限。
