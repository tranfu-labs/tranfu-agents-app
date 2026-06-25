# Delta:admin(后台数据清理域)— refactor-server-app-by-domain

## 修改:事实来源

### 原(spec.md 第 3 行)
```
事实来源:`server/app.py` 的 `/api/admin/*`、`/admin` 前端与改造后的 `DELETE /v1/events`。
```

### 改为
```
事实来源:`server/routes/admin.py`(`/api/admin/*` 端点与清理算子族)、
        `server/routes/ingest.py` 的 `DELETE /v1/events`(legacy 兼容路径)、
        共用模块 `server/db.py`(连接 + schema)、`server/security.py`(管理钥匙鉴权 + 限流)、
        以及 `frontend/` 的 `/admin` 前端。
```

## 理由
`server/app.py` 已按 spec 域拆分为 `server/<base>.py` + `server/routes/<domain>.py`(本变更)。
事实来源需要指向新的物理位置,使 spec 与代码的对应关系可机械追踪。

行为零变更:鉴权 / 限流 / 删除模型 / 审计 / 软删除 / 导出确认 / IP 取值 等所有 MUST 规则
与原 spec 完全一致,只是实现位置从单文件搬到了对应模块。
