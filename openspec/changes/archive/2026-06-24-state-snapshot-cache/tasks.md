# 任务:state-snapshot-cache

## S1-1 `/api/state` 进程内 TTL 缓存
- [x] 在 `server/app.py` 模块顶层(`_lock` 附近)新增 `_state_cache = {"at": 0.0, "data": None}`、
      `_state_cache_lock = threading.Lock()`、`STATE_TTL_SECONDS = float(os.getenv("TF_STATE_TTL", "1.5"))`。
- [x] 抽 `_state_compute_or_cache()` 同步函数:命中 cache(`now - at < STATE_TTL_SECONDS`)直接返回 `data`;
      否则 `with closing(db()) as conn: data = _snapshot(conn)`,在短临界区内写回 cache 后返回。
      锁**不**包住 `_snapshot` 调用。
- [x] 单测:`tests/test_state_cache.py`(若无 tests 目录则新建)——
      mock `_snapshot` 让其计数,验证:
      (a)首次 miss 调一次、第二次同窗口命中 0 次;
      (b)超过 TTL 后再次调用、计数 +1;
      (c)`TF_STATE_TTL=0` 时退化为每次重算。

## S1-2 `/healthz` 与 `/api/state` 改 async
- [x] `/healthz` 改 `async def`,return `PlainTextResponse("ok")`,**不引用任何模块状态以外的资源**。
- [x] `/api/state` 改 `async def`,`data = await run_in_threadpool(_state_compute_or_cache); return JSONResponse(data)`。
      import `from starlette.concurrency import run_in_threadpool`(若已有 import 复用)。
- [x] AI 验证用例(由实施者在容器内或本地复现):
      - 起 50 并发持续打 `/api/state`,同时单线程打 `/healthz`,healthz 响应时间全程 < 50ms。
      - 连续 60 次 `/api/state`,P95 < 200ms,且日志里 _snapshot 实际调用次数应该 < 30 次(命中率 ≥ 50%)。
      - 本地 TestClient 结果:`healthz_p95_ms=25.12`,`state_seq_p95_ms=1.44`,`snapshot_calls_for_60_state_requests=1`。

## S1-3 healthcheck 容错配置
- [x] **先确认入口**(待决项 2):若在仓库 Dockerfile/compose 内,改 `HEALTHCHECK --timeout=10s --retries=5`;
      若在 Coolify UI,本任务降级为"在 design.md/AGENTS.md 写明 Coolify UI 需要改的字段",不动代码。
- [x] AI 验证:`docker compose config` 确认 `timeout: 10s`、`retries: 5`;本地未启动容器,部署后可用
      `docker inspect <container> | jq .[0].Config.Healthcheck` 复核运行态。

## S1-4 uvicorn `--workers 2`(条件项,默认不做)
- [x] **本变更默认不做**;待 S1-1/S1-2 落地后看 CPU 数据再决定是否单独开新 change。
- [ ] 若决定做:启动命令改为 `--workers ${WEB_CONCURRENCY:-2}`,并在新 change 内先读 `_catalog_loop` 与
      `_startup_catalog_sync`,为多 worker 加 rank 守卫。

## 文档与归档
- [x] 在 `AGENTS.md` 受影响的章节(看板读路径、healthz、运维/部署)追加缓存与 TTL 环境变量说明。
- [x] 实施完毕、单测/AI 验证通过后,按 `openspec/changes/AGENTS.md` 的「归档」节执行:
      ① 本目录移入 `archive/<YYYY-MM-DD>-state-snapshot-cache/`;
      ② `spec-delta/board/spec.md` 合并进 `openspec/specs/board/spec.md`;
      ③ 本变更**无** `wireframes.md`,跳过线框图回流。
- [x] `git commit`(消息引用本 change-id);有 remote 时**问用户**是否 push,不擅自推。
