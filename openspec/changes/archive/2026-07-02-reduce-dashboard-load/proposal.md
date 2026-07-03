# 变更提案:reduce-dashboard-load

- 状态:Proposed
- 关联:ADR-0001(单容器 + SQLite),ADR-0003(心跳去重),openspec/specs/board,openspec/specs/ingest

## 背景 / 问题

生产上出现过阶段性 CPU 冲高,但调查显示不是单一"心跳太多"导致:

- `/api/state` 由看板频繁轮询,而接口内部会聚合 sessions、feed、活跃时长、leverage、skill usage、profile 与 shim version。
- 当时 `/api/state` 只有 `live=1`,但 `sessions_cards=25`、`operators=10`、`agents=25`,说明多数是历史 / idle / done 卡片,仍会参与快照计算。
- 前端顶层每 3 秒无条件拉 `/api/state`;服务端 TTL 默认 1.5 秒,因此多浏览器或错峰请求仍可能持续触发重算。
- `_state_compute_or_cache` 只保护缓存读写,重算在锁外执行;缓存过期瞬间多个并发请求可能同时穿透并重复 `_snapshot`。
- `/v1/events` 对纯心跳虽不插入新事件,但每次仍 `UPDATE events.last_seen`;新 shim 每次心跳还会带 `shim_version`,现有服务端会重复 UPSERT 相同版本,继续制造 SQLite 写压力。
- 单 uvicorn Python 进程在读侧聚合与写侧 SQLite 锁竞争下会拖慢其它请求;`/healthz` 本身已经是轻量 async handler,但容器 CPU 被拉满时仍会被部署平台判 unhealthy。

## 目标

- 用服务端推送减少浏览器对 `/api/state` 的周期性请求,同时保留可靠 fallback。
- 保证 `/api/state` 快照重算在同一进程内单飞,避免缓存过期时的并发重复计算。
- 将纯心跳 `last_seen` 写入合并为默认 15 秒一批,降低 SQLite 高频写锁。
- 跳过相同 `shim_version` 的无意义写入,只在首次出现或版本变化时更新 sticky 表。
- 保持状态变化、步骤变化、skill 使用、profile 更新、shim 版本变化这些真实语义事件即时落库。
- 不引入外部数据库、缓存、MQ 或独立前端运行服务,继续符合单容器 + SQLite 约束。

## 非目标

- 不改卡片按 `(operator, agent || runtime)` 合并的身份模型。
- 不引入多 uvicorn worker;多 worker 下的 SSE 广播与后台线程协调另起变更讨论。
- 不调整 token / 成本相关能力;本项目仍不追踪 token 或费用。
- 不重做 SKILLS 页面低频接口的图表与信息架构。
- 不用 WebSocket 做双向协议;本期只需要 server → browser 的状态推送,优先 SSE。

## 方案概述

1. 新增 `/api/state/stream` SSE 通道。
   浏览器优先通过 EventSource 接收完整 state payload;连接成功后先收到一份初始快照,后续由服务端在 state dirty 时合并推送。若 SSE 不可用或断开,前端回退到自适应 polling。

2. `/api/state` 与 SSE 共用同一套快照缓存。
   `_state_compute_or_cache` 增加 single-flight / stale-while-revalidate 语义:同一时刻最多一个线程计算新快照;其它请求复用仍可接受的旧快照或等待已在途的结果,不重复运行 `_snapshot`。

3. 前端 state hook 改为 SSE-first。
   `usePollingState` 演进为"实时状态 hook":优先建立 SSE,失败后 fallback polling。fallback 轮询按页面可见性和当前 live 数自适应:可见且有 live agent 时保持约 3 秒;无 live agent 时降到约 15 秒;页面隐藏时暂停或降到约 60 秒;任何时候都避免并发叠加请求。

4. 写侧纯心跳 batch。
   `/v1/events` 对状态/步骤未变化且不携带需要即时落库语义的纯心跳,不再每次更新 SQLite,而是把最新 `last_seen` 放入进程内 pending map。后台 flush 默认每 15 秒用一个事务批量更新。进程崩溃时最多丢最近 15 秒 liveness 刷新,不丢真实状态转变;该取舍已确认可接受。

5. sticky `shim_version` 避免 no-op 写。
   收到非空 `shim_version` 时,仅当该身份当前值缺失或不同才写 `agent_shim_versions`;相同版本的心跳不更新 `updated`,也不触发 SQLite 写。

## 影响

- `server/routes/board.py`:新增 SSE 端点、state dirty/broadcast 机制、single-flight 缓存保护。
- `server/routes/ingest.py`:新增纯心跳 pending map、15 秒 batch flush、相同 shim_version 写跳过,并在真实状态变化时标记 state dirty。
- `server/routes/admin.py`:管理清理 / 恢复完成后标记 state dirty,让 SSE 看板及时反映删除或恢复结果。
- `frontend/src/lib/api.ts` 及调用点:状态读取改为 SSE-first + fallback polling。
- `openspec/specs/board/spec.md`:补充 `/api/state/stream`、single-flight、fallback polling 行为。
- `openspec/specs/ingest/spec.md`:补充纯心跳 batch、`TF_HEARTBEAT_BATCH_SECONDS` 与 `shim_version` no-op 写规则。
- 测试需要覆盖并发快照单飞、SSE 首包与 fallback、纯心跳 batch flush、真实事件即时写、相同 shim_version 不重复写。
