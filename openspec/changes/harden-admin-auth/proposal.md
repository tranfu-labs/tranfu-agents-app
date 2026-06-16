# 提案：harden-admin-auth（管理接口认证加固与防爆破）

## 背景
对 admin key 机制做了一次安全评估（对照 OWASP API Security Top 10 / REST Security Cheat Sheet）。管理接口仅靠单一静态、永不轮换的 `TF_ADMIN_KEY` 保护，缺少防爆破与若干加固层。已确认的问题：

- 前端 `?key=` 入口会把钥匙带进反代/CDN 访问日志（`replaceState` 只清地址栏，清不掉已发生的那次请求记录）。**已修**。
- `check_admin` 用非常量时间比较；`.env.example` 摆着 `devadmin` 弱示例易被照抄。**已修**。
- `check_auth`（写侧 `TF_KEY`）仍是非常量时间比较 —— 与已修的 `check_admin` 不一致，timing-safe 只做了一半。
- `/api/admin/*` 无任何速率限制；且每次验钥失败都抢全局写锁写一条 `denied` 审计 —— 既可在线爆破（尤其配弱钥），又是写放大型 DoS 点。
- `GET /api/admin/export` 一次请求即 `VACUUM INTO` 导出整库（含 PROTOCOL §5 重点保护的 instructions/memory/input/output），无二次确认。**这是钥匙泄露后不可逆的最高危后果，却保护最薄**：删除尚能从回收站恢复，导出泄露无法挽回。
- 兼容用的 `DELETE /v1/events` 绕过 `/api/admin/data` 的 preview/confirm/force/MAX_ROWS 全部护栏，与本域「护栏 MUST」条款冲突。
- 无任何安全响应头（CSP / X-Frame-Options / Referrer-Policy / nosniff / HSTS）。

## 提案
以「**防止钥匙泄露 → 泄露后仍有第二道拦截 → 高危操作加额外确认**」为目标，对管理接口做一组加固：常量时间比较全覆盖、真实客户端 IP 提取、按 IP 速率限制 + 指数退避、失败审计降噪、导出端点二次确认、遗留删除端点护栏对齐、统一安全响应头。

## 影响
- 业务域：**admin**（主要）、**ingest**（`check_auth` / `enroll` 的比较与限流）。
- 对外行为：连续失败的管理请求被 `429` 限流；导出整库需二次确认；遗留 `DELETE /v1/events` 行为向 `/api/admin/data` 看齐；所有响应新增安全头。
- 部署：新增环境变量 `TF_TRUST_PROXY`、`TF_ADMIN_RATE_*`；**反代场景须开 `TF_TRUST_PROXY`，限流才按真实 IP 生效**，否则会「一人触发、全员被封」。
