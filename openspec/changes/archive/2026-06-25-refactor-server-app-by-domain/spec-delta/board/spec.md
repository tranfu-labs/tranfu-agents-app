# Delta:board(看板与计算域)— refactor-server-app-by-domain

## 修改:事实来源

### 原(spec.md 第 3 行)
```
事实来源:`server/app.py`(`/api/state`、`metrics`、`leverage`、`reuse_map`、`_snapshot`)与 `frontend/` React 看板。
```

### 改为
```
事实来源:`server/routes/board.py`(`/api/state` / `/api/skills` / `/api/skill` / `/api/operator` /
        `/api/agent` 端点 + `_snapshot` / `metrics` / `leverage` / `skill_usage` / `skills_overview` /
        `*_payload` / `_state_compute_or_cache`)、`server/profile.py`(`load_profiles` /
        `load_shim_versions` / `reuse_map`)、共用模块 `server/db.py`、`server/catalog.py`
        (skill 来源标记)、以及 `frontend/` React 看板。
        缓存状态 `_state_cache` / `_state_cache_lock` 仍由 `server/app.py` 持有(全局可变)。
```

## 理由
`server/app.py` 已按 spec 域拆分(本变更)。事实来源指向新的物理位置。

行为零变更:`/api/state` TTL 缓存语义、卡片身份合并规则、掉线判定、`STALE_SECONDS`、
`WINDOW_DAYS`、`totals.live` 口径、`feed` 倒序、`leverage` 定义、`skills` 排行口径、
`shim.version` 三态比较 等所有 MUST 规则与原 spec 完全一致,只是实现位置从单文件搬到了对应模块。
