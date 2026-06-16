# 规格（delta）：admin —— 认证加固与防爆破

事实来源：`server/app.py` 的 `check_admin` / `_client_host` / `/api/admin/*` / `/api/admin/export` / `DELETE /v1/events` / 响应中间件。本 delta 在现有 `openspec/specs/admin/spec.md` 基础上新增/修改下列条款，实现完成后合并回主规格。

## 鉴权比较（MUST）
- 管理钥匙比较 MUST 用常量时间比较（`hmac.compare_digest`），不得短路；输入按 bytes 处理以兼容非 ASCII，且不得因输入类型抛 500。

## 防爆破速率限制（MUST）
- 管理接口（含 `/api/admin/*`、`/api/admin/export`、兼容 `DELETE /v1/events`）MUST 按真实客户端 IP 限流。
- 同一来源在 `TF_ADMIN_RATE_WINDOW`（默认 60s）内验钥失败超过 `TF_ADMIN_RATE_MAX`（默认 5）次后 MUST 进入封锁窗口，后续请求返回 `429` 并带 `Retry-After`；封锁时长指数退避，从 `TF_ADMIN_LOCK_BASE`（默认 30s）翻倍至 `TF_ADMIN_LOCK_MAX`（默认 3600s）封顶。
- 封锁窗口内的请求 MUST 不再校验钥匙、不写审计。
- 验钥成功 MUST 清除该来源的失败计数。

## 真实客户端 IP（MUST）
- 仅当 `TF_TRUST_PROXY=1` 时，客户端 IP 取自 `X-Forwarded-For`（可信反代追加的最右段）；否则取连接对端 IP。
- 未声明可信反代时 MUST NOT 信任请求自带的 `X-Forwarded-For`。

## 失败审计降噪（MUST）
- 被拒管理请求的 `admin_audit`（`action=denied`）MUST 按来源 + 窗口去重：每个来源每个节流窗口最多一条汇总（含累计失败数）；被 `429` 拦下的请求 MUST NOT 再写审计。

## 高危导出加固（MUST）
- `/api/admin/export` 导出整库快照（含敏感字段 instructions/memory/input/output），MUST 需要二次确认方可执行，MUST 纳入上述速率限制，审计 `action=export` MUST 标记为高危。
- 带副作用的导出 SHOULD 以 `POST` 暴露，不应为可被预取/缓存的 `GET`。

## 遗留端点护栏对齐（MUST）
- 兼容 `DELETE /v1/events` 的删除 MUST 受与 `/api/admin/data` 同等护栏约束（`preview_token`、`confirm_count`、活跃会话 `force`、`TF_ADMIN_MAX_ROWS`）；若保留为简化旁路，则 MUST 默认关闭并在文档标注废弃。

## 安全响应头（MUST）
- 所有响应 MUST 带 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`（或等效 CSP `frame-ancestors 'none'`）、`Referrer-Policy: no-referrer`；`/admin` 页 MUST 带锁定本源的 `Content-Security-Policy`；启用 HTTPS 的生产部署 MUST 带 `Strict-Transport-Security`。

## 可验证行为
- 连续错钥达阈值 → `429` + `Retry-After`；封锁期带正确钥匙仍 `429`；到期可恢复。
- 爆破 N 次后 `admin_audit` 的 `denied` 行数 ≤ 经历的窗口数。
- `TF_TRUST_PROXY=0` 时伪造 `X-Forwarded-For` 不改变限流分桶。
- 导出缺二次确认 → 拒绝；遗留 `DELETE /v1/events` 超 `MAX_ROWS` 无 `confirm_count` → 拒绝。
- 响应含上述安全头。
