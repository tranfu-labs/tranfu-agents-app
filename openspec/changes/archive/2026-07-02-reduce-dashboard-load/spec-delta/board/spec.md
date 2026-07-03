# spec-delta:board

## 接口新增

- 新增 `GET /api/state/stream` → `text/event-stream`。
  该端点面向浏览器看板推送完整 `/api/state` payload:
  - 连接建立后必须先发送一条 `event: state` 的完整快照。
  - 后续当 state 被写路径标记 dirty 时,服务端合并短时间内的多次 dirty,最多重算一次快照并广播给所有 SSE client。
  - 长时间无业务事件时发送 SSE comment keepalive,避免代理静默断连。
  - payload 字段与 `GET /api/state` 保持同结构;前端可用同一 `StatePayload` 解析。
  - SSE 失败不得影响 `/api/state` 普通 HTTP 请求。

## 规则新增 / 修改

- `/api/state` 与 `/api/state/stream` 必须共用同一份进程内快照缓存。
- `/api/state` 快照重算必须具备 single-flight 保护:
  - 同一进程内同一时刻最多一个执行单元运行 `_snapshot`。
  - 缓存仍有效时直接复用。
  - 缓存过期但已有重算在途时,若旧缓存存在,其它请求可返回旧缓存(stale-while-revalidate),不得并发重复重算。
  - 首次无缓存且已有重算在途时,其它请求等待该次重算结果。
- 写侧会在以下情况标记 state dirty:
  - `/v1/events` 插入真实事件行(status/current_step 变化等)。
  - 纯心跳 batch flush 成功更新 `last_seen`。
  - profile、skill usage、shim version 发生实际写入。
  - 管理清理 / 恢复等会影响 `/api/state` 的操作完成后。
- SSE broadcaster 必须合并 dirty,不得每个浏览器连接各自独立重算快照。
- 慢 SSE client 不得拖慢全局推送;实现必须优先保留最新快照,允许丢弃该 client 队列里的旧快照。

## 前端规则新增 / 修改

- 看板 state 数据读取优先使用 `/api/state/stream` SSE。
- SSE 不可用、断开或解析失败时,前端必须回退到 `/api/state` adaptive polling。
- fallback polling 规则:
  - 首次加载立即请求。
  - 页面可见且 `totals.live > 0` 时保持约 3 秒刷新。
  - 页面可见且 `totals.live == 0` 时降到约 15 秒刷新。
  - 页面隐藏时暂停或降到约 60 秒刷新。
  - 任一时刻不得并发叠加多个 `/api/state` 请求;上一请求未完成时跳过下一轮。
- TopBar、Pods、Agents 与 AgentDetail 必须复用同一份 state 数据源,不得各自建立独立 `/api/state` 轮询。

## 可验证行为

- 打开 `/api/state/stream` → 第一条业务事件为 `event: state`,payload 含 `/api/state` 的核心字段。
- 触发一次真实事件写入 → 已连接 SSE client 在合并窗口后收到新的 `state` event。
- 同一 TTL 过期点并发请求 50 次 `/api/state` → `_snapshot` 只执行一次或受 single-flight 约束不重复并发执行。
- SSE 连接失败时,前端仍能通过 fallback polling 展示看板。
- 无 live agent 且页面可见时,前端 fallback polling 请求频率低于 live agent 存在时。
- 页面隐藏时,前端不再保持 3 秒高频 fallback polling。
