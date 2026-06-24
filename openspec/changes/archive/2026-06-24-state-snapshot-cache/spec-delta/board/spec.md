# spec-delta:board(state-snapshot-cache)

针对 `openspec/specs/board/spec.md` 的增量。归档时按下面的"操作"合并进基线。

## 接口章节

### 修改 `GET /api/state`
原条目保留 schema(响应 JSON 形状不变)。**新增**行为补充:

> 服务端对响应做进程内 TTL 缓存,默认 `STATE_TTL_SECONDS=1.5`,可由 `TF_STATE_TTL` 环境变量覆盖。
> 同一 TTL 窗口内的多次请求复用上一次的快照——所以响应字段 `now` 的语义是"上次服务端计算时间",
> 而非"本次请求的服务端时间",最大可能滞后 = `STATE_TTL_SECONDS`。

### 修改 `GET /healthz`
原条目 `→ ok` 保留。**新增**行为补充:

> handler 必须是 async,且**不得**打开 DB 连接、不得引用任何会触发 IO 的模块状态;
> 必须在事件循环直接返回,**不能**进 anyio threadpool 队列。
> 目的:确保 `/api/state` 的聚合压力(threadpool 占用)永远不会影响健康检查响应时间。

## 规则(MUST)章节

**新增**规则(编号紧接现有最高编号):

> N. `/api/state` 必须在服务端做 TTL 缓存复用,缓存 TTL 由 `TF_STATE_TTL`(秒,float)配置,
>    默认 1.5;前端可见的所有字段(包括 `now`/`sessions`/`feed`/`leverage`/`skills`/`shim`/`totals`)
>    可以在一个 TTL 窗口内相同;不允许任何路径(包括 `/api/skills`、`/api/skill/{name}` 等)
>    依赖"`/api/state.now` 必须是请求当下时间"的假设。

> N+1. `/healthz` 必须是 async handler,响应体固定 `ok`,不依赖 DB 或重模块状态;
>    其响应时间不得受 `/api/state` 聚合压力影响——在 100 并发 `/api/state` 期间,
>    `/healthz` 单请求响应时间应 < 50ms。

## 前端规则章节
**无修改**——前端轮询节奏(~3s)、所有视图字段消费方式不变;服务端缓存对前端透明。

## 部署/运维章节(若 specs 内已有,合并;无则在 specs 末尾追加)

> - `TF_STATE_TTL`:`/api/state` 缓存 TTL(秒,float),默认 `1.5`。区间建议 `0.5~3.0`。
> - Docker healthcheck 配置:`Timeout=10s`、`Retries=5`、`Interval=30s`、`StartPeriod=10s`。
>   配置入口取决于本仓库是否托管 Dockerfile/compose;若由 Coolify UI 管理,
>   则该字段以 Coolify 配置为准,本 spec 仅记录目标值。
> - uvicorn `--workers` 默认 1;启用多 worker 前必须先解决 `_catalog_loop`(`server/app.py:658`)
>   多进程并发拉取 + 写 `catalog_cache` 表的潜在竞争,详见独立 change。
