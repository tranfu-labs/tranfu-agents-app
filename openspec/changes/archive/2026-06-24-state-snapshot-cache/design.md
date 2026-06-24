# 设计:state-snapshot-cache

## 方案

### S1-1 `/api/state` 进程内 TTL 缓存

模块级单 entry 缓存(只有一个 cache key,无需 LRU):

- 新增 `_state_cache = {"at": 0.0, "data": None}` 在 `server/app.py` 模块顶层(靠近 `_lock`、`_prune_state` 那一段)。
- 新增 TTL 常量 `STATE_TTL_SECONDS = float(os.getenv("TF_STATE_TTL", "1.5"))`。
- `state()` 命中且 `now - at < STATE_TTL_SECONDS` → 直接返回上次的 `JSONResponse` body。
- 命中失败 → 进 threadpool 执行 `_snapshot(conn)`、更新缓存。
- 并发保护:用一个 `_state_cache_lock = threading.Lock()` 短临界区——只保护"读 `(at, data)` 决定走哪条"和"写新值",
  **不要把 `_snapshot` 包进锁**(否则锁内仍会串行)。允许偶发的"miss 时多线程同时算"——TTL 1.5s 内最多算 N 次,不致命;
  更复杂的"single-flight"(只让一个线程算、其他等结果)放到后续如果发现真有压力再加。
- 缓存的是已序列化的 `dict`(_snapshot 的返回值),`JSONResponse(cached)` 让 starlette 重新 dump——
  避免缓存 `Response` 对象时引入字节级污染。

### S1-2 `/healthz`、`/api/state` 改 async

- `/healthz` 改成 `async def healthz(): return PlainTextResponse("ok")`。**绝对不能引用 `db()` / 模块状态以外的东西**——
  让它能在事件循环直接返回,不进 threadpool 队列,不被 R1 阻塞。
- `/api/state` 改成 `async def state()`,内部 `data = await run_in_threadpool(_state_compute_or_cache)` 并 `return JSONResponse(data)`。
- 抽一个 `_state_compute_or_cache()` 同步函数封装 S1-1 的缓存逻辑 + `with closing(db()) as conn: return _snapshot(conn)`,
  方便 run_in_threadpool 调用,**也方便阶段 2 替换为别的实现**。

### S1-3 healthcheck 容错

- Dockerfile 内 `HEALTHCHECK` 指令(或 compose 内 `healthcheck:` 节,**入口待确认见待决项 2**)调整:
  - `--timeout=10s`(原 5s)
  - `--retries=5`(原 3)
  - `--interval=30s` 不变、`--start-period=10s` 不变
- S1-1+S1-2 落地后理论上不需要这条余量,留作冷启动/首个高峰兜底。

### S1-4 uvicorn `--workers 2`(条件项)

- 启动命令改为 `exec python -m uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8788} --workers ${WEB_CONCURRENCY:-2}`。
- 默认 2 worker;按 `WEB_CONCURRENCY` 环境变量覆盖。
- 风险:
  - **`_catalog_loop`(`app.py:658`)是 startup hook 起的后台 daemon thread**,多 worker 会各起一份,
    pull 远端 catalog 频率 ×worker 数;`catalog_cache` 表 sqlite 写入会被复 worker 同时尝试 →
    上线前必须读完 `_catalog_loop` 与 `_startup_catalog_sync` 的实现,确认是否需要加 `if WORKER_RANK == 0` 这类守卫。
  - 进程内缓存(S1-1)按 worker 各算各的 → cache hit 率折半但总聚合次数仍按 worker 平摊。
- **决策默认**:**先不启用**——只上 S1-1+S1-2+S1-3,落地后看 CPU 数据再决定是否补 S1-4(单独 PR/单独 change 即可)。

## 权衡

### 为什么是 TTL 缓存而不是 SSE / WebSocket
SSE/WebSocket 需要前后端同时改、要处理重连/扇出、要解决"增量 patch 与全量快照如何对齐"——工作量是缓存的 10 倍,
而且阶段 2 的 `metrics` 物化才是单次成本下降的真正杠杆;**先用 1.5s 缓存把"重复计算"压到 60% 以下,撑住运行,
再去优化"单次计算成本"**,顺序不能反。

### 为什么 TTL = 1.5s
- 前端 spec 是 ~3s 轮询,理论上 cache TTL >= 3s 命中率最高,但**前端实际可能多 tab 并发**(诊断现场就是这样),
  N tab 在不同相位打,1.5s 能保证"半个轮询周期内复用 1 次"。
- TTL 太短(<1s)缓存形同虚设;TTL 太长(>3s)前端会感知到"数据不新鲜"(running→done 切换看不到)。
- 1.5s 是经验默认,允许 `TF_STATE_TTL` 环境变量覆盖,生产可调。

### 为什么不引入 single-flight
- 实现复杂(threading.Event + 等待队列),收益边际:TTL 1.5s 内即使 5 个线程同时 miss、各算一次,
  CPU 也只多 5×单次成本,比缓存命中差,但远好于现状的 60 次/分钟。
- 阶段 2 把 `_snapshot` 本身降到 ~50ms 后,single-flight 完全没必要。

### 为什么 `/api/state` 改 async 而不是直接给 sync 加缓存
- 即使有 cache,miss 时仍会进 threadpool;多 miss 同时发生 → threadpool 仍会被 _snapshot 占满 → healthz 排队。
- 改 async 后,健康检查这条路径**永远绕过 threadpool**,与 _snapshot 的负载彻底解耦;这是"健康永远绿"的保证。

### 为什么不顺手去掉 `_lock`、把 `_maybe_prune` 后台化
- 那是写路径,与本变更目标(读路径 + healthz)分属两个改动面。
- 阶段 2 单独开 change,便于回滚与测试隔离。

## 风险

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| 多 tab 看到的 `now` 字段会有 ≤1.5s 滞后 | 任何 tab,正常 | 文档化:`/api/state.now` 语义是"上次服务端计算时间",非"请求时间"。前端原本就按 3s 节奏渲染,人眼不可感知。 |
| 缓存里的 `sessions` 状态与同时写入的 `/v1/events` 有 ≤1.5s 不一致 | 心跳上来后立即查 | 与现状一致——现状下 _snapshot 也只反映"开始算的瞬间",`/v1/events` 不是同步影响 cache。可接受。 |
| `_catalog_loop` 多 worker 起多份引发 catalog_cache 写竞争 | 启用 S1-4 才发生 | 默认不启用 S1-4;真要启用前先读 catalog_loop 实现,加 worker rank 守卫。 |
| healthcheck Timeout 提到 10s 会延迟 unhealthy 判定 | 真出现长时间阻塞时 | 真阻塞场景 S1-1/S1-2 已堵住,这条主要是冷启动余量。`Retries=5 × Interval=30s` 最长 2.5 分钟才标 unhealthy——在我们这个流量下可接受。 |
| `_state_cache` 内的 dict 被 mutate | 不太可能(`_snapshot` 返回新 dict),但 JSONResponse 不修改入参 | dict 全 readonly 使用;若担心可在缓存写入时 `copy.deepcopy`(默认不做)。 |

## 待决项(请在 review 此 design 时回答;每项已给建议默认)

1. **阶段 1 范围**:S1-1+S1-2+S1-3 一起落,S1-4 暂不?**建议默认**:是(S1-4 单独评估)。
2. **healthcheck 配置入口在哪**:Dockerfile 内 `HEALTHCHECK` / compose `healthcheck:` / Coolify UI?
   报告里的 healthcheck 内容只见于 `docker inspect`,本仓库根目录没明显 Dockerfile/compose——**需要确认**,
   决定 S1-3 改哪个文件,或者改 Coolify UI(那 S1-3 就不在本仓库 PR 里)。
3. **多 worker 时 `_catalog_loop` 是否安全**:S1-4 默认关,问题留待启用时回答;但作为 design 备忘需要在 tasks 里
   列一项"启用 S1-4 前阅读 catalog_loop 并加 worker 守卫"。**建议默认**:阶段 1 不启用,问题留到独立 change。
4. **阶段 2 是否本次一起落 spec**:**建议默认**:不一起。阶段 2(`metrics` 物化、写路径减压)的取舍要等
   阶段 1 落地后看数据再设计,现在落 spec 会写出"不成熟的契约"。
5. **`STATE_TTL_SECONDS` 默认值**:**建议默认**:1.5s。允许 `TF_STATE_TTL` 环境变量覆盖,
   生产可在 0.5~3.0 区间调,不需要重新发版。
