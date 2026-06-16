# 任务：harden-admin-auth

## 已完成（本轮零成本加固）
- [x] `check_admin` 改 `hmac.compare_digest`（常量时间，bytes 编码兼容非 ASCII）
- [x] 移除前端 `?key=` URL 入口（旧链接只清地址栏、不再采用）
- [x] 启动时弱 `TF_ADMIN_KEY` 告警（过短或命中常见示例值）
- [x] 清理 `devadmin` 弱示例（`.env.example`、`admin-data-cleanup/design.md`）

## 已实现
- [x] `check_auth`（`INGEST_KEY`）同步 `compare_digest`（抽出 `_key_eq`，admin/ingest 共用）
- [x] 真实客户端 IP 提取 + `TF_TRUST_PROXY` 开关（`_client_host` 取 XFF 最右段；审计 actor 用真实 IP）
- [x] admin 端点速率限制 + 指数退避（`TF_ADMIN_RATE_*`/`TF_ADMIN_LOCK_*`），统一接入 `check_admin`
- [x] 失败审计降噪（每来源每窗口一条汇总；429 不验钥、不写库）
- [x] **`/api/admin/export` 加固：改 `POST` + `confirm=EXPORT` 二次确认 + 纳入限流 + 审计高危标记**
- [x] 遗留 `DELETE /v1/events` 护栏对齐（force/confirm_count/MAX_ROWS；标废弃，不强制 preview_token）
- [x] 统一安全响应头中间件（CSP / X-Frame-Options / nosniff / Referrer-Policy / HSTS）
- [x] `/v1/enroll` 纳入限流（独立计数桶）；`/v1/events` 高频上报豁免
- [x] `.env.example` / `DEPLOY.md` 补 `TF_TRUST_PROXY`、`TF_ADMIN_RATE_*`、`TF_HSTS` 说明（重点提示反代场景）
- [x] 前端 `exportAdminDb` 改 POST + confirm，「导出 DB」按钮加二次确认弹窗

## 验证
- [x] 扩展 `tests/test_admin_cleanup.py`（TestClient）：
  - 错钥到阈值 → `429` + `Retry-After`（`test_rate_limit_locks_after_threshold`）
  - 封锁期带正确钥匙仍 `429`；到期恢复（`test_lockout_recovers_after_expiry`）
  - 多轮触发 → 退避指数增长且封顶（`test_lockout_backoff_grows_and_caps`）
  - 爆破 N 次后 `denied` 行数 ≤ 窗口数（`test_denied_audit_deduped_per_window`）
  - `TF_TRUST_PROXY` 开/关的分桶（`test_xff_*_trust_proxy`）
  - export POST + 缺 confirm → 拒绝（`test_export_requires_post_and_confirm`）；
    遗留 `DELETE /v1/events` 超 `MAX_ROWS` 无 `confirm_count` → 拒绝（`test_legacy_delete_enforces_max_rows_confirm`）
  - 安全头存在 + 非 HTTPS 不发 HSTS（`test_security_headers_present`）；enroll 限流（`test_enroll_is_rate_limited`）
  - conftest 每测试清空进程内限流状态,避免跨测试污染
- [x] `pytest tests/` 全绿（123 passed）；`python -m py_compile server/app.py`；前端 `npm run build` 通过
- [x] 把本目录 `specs/` delta 合并回 `openspec/specs/`（admin / ingest）
