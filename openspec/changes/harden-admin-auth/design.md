# 设计：harden-admin-auth

## 方案

### 1. 常量时间比较（全覆盖）
`check_admin` 已改用 `hmac.compare_digest`（两边编码成 bytes，兼容非 ASCII 输入、不抛 500）。`check_auth`（`INGEST_KEY`）同步改造，统一比较方式，避免只修一半。

### 2. 真实客户端 IP（限流前置，关键依赖）
现 `_client_host` 取 `request.client.host`；部署在 Traefik/Coolify 反代后面时，所有外部请求 IP 都变成反代 IP，直接限流会「一人触发、全员被封」。新增真实 IP 提取：`TF_TRUST_PROXY=1` 时取 `X-Forwarded-For` 中可信反代追加的最右段，否则用连接对端 IP。XFF 可伪造，故默认关、仅在确认前置有可信反代时开。顺带修正现有审计日志的 IP 失真。

### 3. 速率限制 + 指数退避（核心）
服务是单进程单 worker（`uvicorn.run(app)`，无 `--workers`）→ 用进程内限流器（dict + 独立轻锁，只做内存读写、不碰全局 DB 锁、不引入 Redis，契合「无外部服务」）。统一接在 `check_admin` 开头（6 个 admin 端点 + 遗留 DELETE 都经过它，单点覆盖）：

- 命中封锁窗口 → 直接 `429` + `Retry-After`，**不验钥、不写审计**。
- 验钥失败 → 滑窗计数 +1；超阈值则 `blocked_until = now + 指数退避`（base→翻倍→封顶）。
- 验钥成功 → 清除该来源失败记录。

参数（沿用 `_env_int` 风格）：`TF_ADMIN_RATE_MAX`(5)、`TF_ADMIN_RATE_WINDOW`(60s)、`TF_ADMIN_LOCK_BASE`(30s)、`TF_ADMIN_LOCK_MAX`(3600s)。内存惰性清理过期条目 + 硬上限（如 1 万 IP），防海量来源撑爆内存。

### 4. 失败审计降噪
每个来源每个节流窗口最多写一条 `denied` 汇总（含累计失败数、是否封锁）；已被 429 拦下的请求不写库。消除写放大与对全局写锁的抢占。

### 5. 导出端点加固（最高优先）
`GET /api/admin/export` 一次请求 `VACUUM INTO` 导出整库、不可逆。加：二次确认（显式 `confirm=EXPORT` 或回带 inventory 指纹）、纳入速率限制、审计 `export` 行标记高危（后续可接告警）。评估改为 `POST` —— 带副作用的操作不应是可被预取/缓存的 `GET`。

### 6. 遗留 DELETE /v1/events 护栏对齐
现状走了 `check_admin` + 回收站 + 审计，但**不要求 preview_token、不要求 confirm_count、不检查活跃会话、不受 MAX_ROWS 限制**，是绕过护栏的旁路。要么补齐与 `/api/admin/data` 一致的护栏，要么默认关闭并标注废弃。倾向「对齐护栏」以保 curl 兼容。

### 7. 安全响应头
统一中间件注入：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`、锁定本源的 `Content-Security-Policy`（`/admin` 页禁内联与第三方脚本，作为 XSS 纵深防御）、HTTPS 生产部署加 `Strict-Transport-Security`。

## 权衡
- **限流放进程内存**：最简、契合「无外部服务」；代价是将来若加 `--workers N`，各 worker 计数独立、阈值实际放大 N 倍，届时需换共享存储（SQLite 表 / Redis）。文档须注明此前提。
- **封锁期一律拒绝（含正确钥匙）**：防爆破彻底；代价是运维误触后要等，但封锁起步仅 30s，可接受。
- **遗留端点选「对齐护栏」而非删除**：保兼容，代价是多一处维护。
- **导出加二次确认 vs 维持便利**：导出是不可逆数据泄露面，确认成本值得。

## 风险
- **XFF 信任错配**：开了 `TF_TRUST_PROXY` 但前面没有可信反代 → 攻击者自带 `X-Forwarded-For` 即可伪造 IP 绕过限流。文档须写死「仅在确认前置可信反代时开」；回滚 = 关开关回到连接 IP。
- **限流误伤**：阈值过低影响正常运维；默认值偏宽松（5 次/分钟），可调。
- **CSP 过严打断前端**：先以 `Content-Security-Policy-Report-Only` 灰度，再切强制。
- **改 export 为 POST 破坏现有 curl 脚本**：在本 change 内同步更新文档与前端调用。

## 回滚
各项相互独立，均由环境变量或可单独还原的代码块控制；限流器、响应头中间件、导出确认都能单独关闭回退。
