# Delta:ingest(事件采集域)— refactor-server-app-by-domain

## 修改:事实来源

### 原(spec.md 第 3 行)
```
事实来源:`server/app.py` 的 `POST /v1/events` 与 `PROTOCOL.md`(TATP v0.1)。
```

### 改为
```
事实来源:`server/routes/ingest.py`(`POST /v1/events` 与 `POST /v1/enroll`)、
        `server/identity.py`(`canon_operator` / `verify_operator` — 身份归一化与 token 校验)、
        共用模块 `server/db.py`(写路径 + 全局 `_lock`)、`server/security.py`(写侧鉴权)、
        以及 `PROTOCOL.md`(TATP v0.1)。
```

## 理由
`server/app.py` 已按 spec 域拆分(本变更)。事实来源指向新的物理位置。

行为零变更:身份字段定义、必填校验、status 枚举、profile 字段集合、`shim_version` 顶层字段、
心跳去重规则、profile 全量替换语义、skill 幂等记录、`skill_mode` 缺省 used、心跳命中仍处理 skill、
缺 session_id 时忽略 skill、`TF_REPORT_SKILLS=0` 不附加、OpenClaw equipped 边界 等所有 MUST 规则
与原 spec 完全一致,只是实现位置从单文件搬到了对应模块。
