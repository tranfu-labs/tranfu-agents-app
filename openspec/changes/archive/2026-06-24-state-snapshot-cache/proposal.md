# 变更提案:state-snapshot-cache(看板读路径止血)

- 状态:Proposed
- 关联:specs/board(GET /api/state 行为与轮询)、`server/app.py` 的 `_snapshot`/`/healthz`/`/v1/events`
- 触发事件:2026-06-23 生产 Coolify 容器 `tranfu-agents-app:local` CPU 长期 130%~270%、
  healthcheck 连续 FailingStreak=9 进入 unhealthy(诊断报告见 `/private/tmp/tranfu-agents-cpu-*`)。

## 背景 / 问题
看板读路径在生产被打爆,根因不是单点故障而是一条链:

1. **`GET /api/state` 是无缓存的重聚合**:每次进 `_snapshot(conn)` 串行做 7 件 O(N) 活——
   200 行 events 的 JOIN+GROUP BY、`metrics()` 扫整段 90 天窗口 events 再 Python 端按秒分桶、
   `load_profiles()` 全表 + 逐行 `json.loads`、`load_shim_versions()` 全表、`leverage()` 双 COUNT、
   `skill_usage()` 在 `skill_uses` 上 GROUP BY skill,mode(day 无独立索引)。
2. **前端 spec 是 ~3s 轮询,实际 60-75 req/min**:多浏览器 tab/多客户端同时打,
   服务端没有缓存复用,每次都重算同一份快照。
3. **`/api/state` 是 sync def**:FastAPI 把它推到 anyio threadpool;并发请求各占一个 worker
   同时跑同一份聚合,GIL 直接顶到 245%~272% CPU。
4. **`/v1/events` 路径上有全局 `_lock` 串行 + 路径内同步 `_maybe_prune`**:WAL 本就保证 writer 串行,
   应用层再加 Python 锁等于把 dedup-UPDATE 这类快路径也排队;每 200 次 insert 同事务跑一次 DELETE。
5. **`/healthz` 也是 sync def**:handler 本体 25ms,但 threadpool 被根因 1 全占 → 排队 2s 超时 →
   Docker 标 unhealthy。
6. **uvicorn 单 worker**:启动命令无 `--workers`,单进程 GIL + 40 anyio threadpool worker,
   实例还有 3 核没用。

## 目标
让生产容器 CPU 在不重写架构的前提下立刻降一个数量级,healthcheck 永远绿。本变更只做**止血层**(下称阶段 1),
保留下一轮根治(阶段 2:`metrics` 物化、写路径减压)所需的接口和数据契约空间。

- CPU 从 ~270% 降到 ≤60%(单 worker,稳定流量)。
- `/healthz` 在 100 并发 `/api/state` 期间仍 < 50ms,Docker healthcheck 连绿。
- `/api/state` 的 P95 < 200ms;聚合 SQL 的实际执行次数降到 ≤40 次/分钟,与前端 tab 数解耦。

## 非目标
- 不动 `_snapshot` 内部聚合算法(不做 metrics 物化、不动 daily_active 表)——留给阶段 2。
- 不改 `/v1/events` 写路径(去 `_lock`、_maybe_prune 后台化)——留给阶段 2 独立 change。
- 不引入 SSE/WebSocket。
- 不动前端轮询节奏(仍按现有 spec ~3s);本变更只在服务端做缓存,前端无感知。

## 方案概述(详见 design.md)
四件事(命名沿用诊断时的 S1-*),按风险/收益从大到小排:

- **S1-1**:`/api/state` 进程内 TTL 缓存 1.5s(默认值,可经环境变量覆盖),命中即返回旧 JSON。
- **S1-2**:`/healthz`、`/api/state` 改 `async def`;`/healthz` 完全不依赖 DB、不进 threadpool;
  `/api/state` 的聚合显式 `await run_in_threadpool(...)`。
- **S1-3**:Dockerfile / compose 的 healthcheck `Timeout` 5s→10s、`Retries` 3→5(配置层余量)。
- **S1-4**:uvicorn 启动 `--workers 2`(条件项,**先观察 S1-1+S1-2 落地后的数据再决定是否启用**)。

## 影响
- specs/board:`GET /api/state` 与 `GET /healthz` 行为补充(缓存语义 + healthz 解耦)、新增缓存可配置项。
- `server/app.py`:`state()`/`healthz()` 签名改 async、新增 `_state_cache` 模块状态、聚合包一层 threadpool 调用。
- Dockerfile / compose(待确认入口,见 design.md 待决项 2):healthcheck Timeout/Retries 配置。
- 不影响 `/v1/events` 写路径、不影响 `/api/skills*`、`/api/operator/*`、`/api/agent/*` 等。
- 协议层无破坏性变更:响应 JSON 形状不变,客户端无需配合升级。
