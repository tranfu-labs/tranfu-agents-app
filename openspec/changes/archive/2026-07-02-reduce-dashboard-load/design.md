# 设计:reduce-dashboard-load

## 已确认的决策

1. **推送协议用 SSE,不用 WebSocket。** 本期只有服务端向浏览器推送看板状态,不需要浏览器向服务端发实时命令。SSE 更贴近目标,实现与反代配置也更简单。
2. **SSE 必须有 polling fallback。** 浏览器、反向代理或部署环境不支持 SSE 时,看板仍必须可用。
3. **纯心跳 batch 默认 15 秒。** 服务进程异常退出时最多丢 15 秒 `last_seen` 刷新,用户确认可以接受。状态变化、步骤变化、done/error、skill、profile、shim 版本变化仍即时写。
4. **保持单容器 + SQLite。** 不引入 Redis、MQ、外部 DB 或多 worker 协调层。
5. **不把健康检查做重。** `/healthz` 继续是 async 轻量 handler;本变更通过降低读写压力保护它,而不是让 healthz 读取状态或 DB。

## 数据流

### SSE 状态推送

```
Browser EventSource /api/state/stream
→ server 发送初始 state 事件(完整 /api/state payload)
→ ingest / heartbeat flush / admin cleanup 等写路径标记 state dirty
→ board 域 coalescer 在短 debounce 后触发一次快照刷新
→ 所有 SSE client 收到同一份 state payload
→ SSE 断开或失败:前端回退到自适应 polling /api/state
```

SSE event 建议形态:

```
event: state
data: {"now":"...","sessions":[...],"feed":[...],"leverage":...}

: keepalive
```

`/api/state/stream` 返回 `text/event-stream`,带 `Cache-Control: no-cache`。首包必须尽快返回一份 state,避免用户进入页面后等待下一次事件。连接长期空闲时发送 keepalive comment,防止中间代理静默断开。

### State dirty 与快照单飞

`board` 域维护进程内状态:

- `_state_cache`:沿用现有 TTL 缓存。
- `_state_compute_lock` / `_state_compute_inflight`:保证同一时刻最多一个线程运行 `_snapshot`。
- `_state_dirty_revision`:写路径标记状态可能变化时递增。
- SSE client queue 列表:每个连接一个小队列,慢连接丢旧快照保最新快照,避免反压拖慢全局。

`_state_compute_or_cache` 的新语义:

1. 缓存仍在 TTL 内且未被强制刷新时,直接返回缓存。
2. 缓存过期但已有计算在途时:
   - 若已有缓存,优先返回旧缓存(stale-while-revalidate),避免请求堆积。
   - 若没有缓存,等待在途计算完成。
3. 没有计算在途时,当前请求成为唯一计算者,运行 `_snapshot` 后更新缓存并唤醒等待方。

SSE broadcaster 不为每个 client 单独计算快照。dirty 后由 coalescer 统一调用同一套 `_state_compute_or_cache(force=True)` 产出一次 payload,再广播给所有 client。

### 前端读取策略

前端状态 hook 分两层:

1. **SSE-first**
   - mount 后创建 `EventSource('/api/state/stream')`。
   - 收到 `state` event 后解析为 `StatePayload`,沿用现有 demo/offline 降级逻辑。
   - `open` 后认为 live transport 可用;`error` 或连接关闭时进入 fallback。

2. **adaptive polling fallback**
   - 首次立即请求 `/api/state`。
   - `document.visibilityState === 'hidden'`:暂停或降为 60 秒。
   - 页面可见且上一份 state 的 `totals.live > 0`:约 3 秒。
   - 页面可见且 `totals.live === 0`:约 15 秒。
   - 请求仍在进行时跳过下一轮,不并发叠加。
   - 网络错误时指数退避,但手动 refresh 仍可立即触发。

TopBar、Pods、Agents、AgentDetail 继续消费同一份 state;不会在不同组件里各自建立独立 state 请求。

## 写侧 batch 设计

### 纯心跳判定

纯心跳必须同时满足:

- 该身份 + runtime + agent key + session_id 的上一行存在。
- `status` 与 `current_step` 相对上一行不变。
- 本次事件没有新 skill 需要落库。
- 本次事件没有 profile 字段需要更新。
- 本次事件没有新的或变化的 `shim_version` 需要写 sticky 表。

只有纯心跳进入 batch。其它情况沿用即时写路径。

### Pending map

`ingest` 域维护进程内 pending map:

```
event_id -> latest_last_seen_iso
```

当纯心跳命中时:

1. 仍完成鉴权、身份归一化、token 校验和上一行查询。
2. 将 `last_seen` 最新值写入 pending map,覆盖同一 event id 的旧值。
3. 返回 `{"ok": true, "heartbeat": true, "verified": ...}`。
4. 不立即 `UPDATE events`。

后台 flush 线程默认每 `TF_HEARTBEAT_BATCH_SECONDS=15` 秒运行一次:

1. 拿走 pending map 快照并清空。
2. 在 `app._lock` 下用一个 SQLite 事务批量 `UPDATE events SET last_seen=? WHERE id=?`。
3. flush 成功后标记 state dirty,让 SSE 推送新 state。

`TF_HEARTBEAT_BATCH_SECONDS=0` 表示禁用 batch,退回每次纯心跳即时更新,便于排障或小规模部署保守运行。

### 真实事件与 pending 的关系

- 状态 / 步骤变化插入新 `events` 行时,该 session 之前挂起的旧行 pending 可以删除,因为新的事件行已经提供更准确的时间边界。
- `done` / `error` 等终止事件必须即时写,不能等待 batch。
- skill/profile/shim version 写入必须在心跳短路前处理;若它们产生了实际写入,本次请求不能被视为"只有 last_seen 的纯心跳"。
- 进程关闭时可 best-effort flush pending;异常退出允许最多丢 15 秒 liveness 刷新。

## shim_version no-op 写

现有协议要求 shim 在每次心跳尽量带顶层 `shim_version`,但服务端 sticky 表的语义是"当前内容版本",不是"每次心跳时间"。因此:

- 非空 `shim_version` 首次出现:插入。
- 非空 `shim_version` 与当前值不同:更新版本与 `updated`。
- 非空 `shim_version` 与当前值相同:不写。
- 缺失或空白 `shim_version`:不清空 sticky 值。

实现可用 SQLite 条件 UPSERT 或先查后写,但必须避免相同版本每次心跳都制造写事务。

## 为什么不是只调大 TTL

只调大 `TF_STATE_TTL` 能减少部分重算,但解决不了三个关键问题:

- 多浏览器仍会持续产生 HTTP 请求。
- TTL 过期瞬间仍可能并发穿透。
- `/v1/events` 纯心跳与相同 `shim_version` 仍会高频写 SQLite。

因此本方案同时处理前端请求数、读侧重算次数和写侧 SQLite 写放大。

## 为什么不用 WebSocket

WebSocket 可以实现,但本期没有双向实时交互需求。SSE 的自动重连、HTTP 语义与单向推送更适合状态流;若未来要做浏览器端实时控制命令,再新增 WebSocket 变更更清晰。

## 风险与对策

- **SSE 被反代断开或不支持**:前端自动 fallback adaptive polling;SSE 端发送 keepalive。
- **慢客户端拖慢广播**:每个 SSE client 使用小队列,满了丢旧快照保留最新快照。
- **batch 导致 still-running active time 展示最多落后 15 秒**:接受;终止事件即时写,最终活跃时长不依赖 pending 心跳才能闭合。
- **进程崩溃丢 pending last_seen**:最多 15 秒 liveness 刷新丢失,不丢真实状态变化;用户已确认可接受。
- **后台线程与测试不稳定**:把 flush 函数拆成可直接调用的纯逻辑,单测不依赖真实 sleep。
- **多 worker 下每进程各有 pending / SSE clients**:当前规格仍默认单 worker;多 worker 支持另起 change。

## 可测性

本变更包含可测逻辑,必须补单测:

- state cache single-flight:并发 N 次请求只触发一次 `_snapshot`。
- stale-while-revalidate:缓存过期且计算在途时可返回旧缓存,不重复计算。
- SSE 首包:连接 `/api/state/stream` 能收到 `state` event,其 payload 与 `/api/state` 结构一致。
- SSE fallback:前端 EventSource error 后进入 polling,不会同时保留 SSE 与 polling 双通道。
- 纯心跳 batch:连续相同 status/step 心跳在 flush 前不更新 DB,last_seen flush 后变为最新。
- 真实状态变化即时写:running → done/error 不进入 batch。
- skill/profile/shim version 变化不被 batch 吞掉。
- 相同 shim_version 不重复更新 sticky 表;版本变化立即更新。
