# 规格:admin(后台数据清理域)

事实来源:`server/routes/admin.py`(`/api/admin/*` 端点与清理算子族 + `DELETE /v1/events` legacy 兼容路径)、共用模块 `server/db.py`(连接 + schema)、`server/security.py`(管理钥匙鉴权 + 限流)、以及 `frontend/` 的 `/admin` 前端。

## 鉴权(MUST)
- 所有 `/api/admin/*` 以及兼容清理路径 `DELETE /v1/events` 须带请求头 `X-TF-Admin-Key` 且等于服务端
  `TF_ADMIN_KEY`。
- `TF_ADMIN_KEY` 为空(未配置)时,管理接口一律 403。
- `TF_ADMIN_KEY` 与采集写侧 `TF_KEY` 相互独立:持有 `TF_KEY` 不得据此访问管理接口。
- 管理钥匙比较须用常量时间比较(`hmac.compare_digest`),不得按字符短路;两侧编码成 bytes 以兼容非
  ASCII 输入,且不得因输入类型抛 500。
- 被拒的管理请求须写一条 `admin_audit`(`action=denied`),审计不得记录明文管理钥匙;失败审计按来源 +
  节流窗口去重(每来源每窗口至多一条汇总,含累计失败数);被 `429` 拦下的请求不再写审计。

## 防爆破速率限制(MUST)
- 管理接口(`/api/admin/*` + `/api/admin/export` + 兼容 `DELETE /v1/events`)须按真实客户端 IP 限流。
- 同一来源在 `TF_ADMIN_RATE_WINDOW`(默认 60s)内验钥失败超过 `TF_ADMIN_RATE_MAX`(默认 5)次后,
  须进入封锁窗口,后续请求返回 `429` 并带 `Retry-After`;封锁时长指数退避,从 `TF_ADMIN_LOCK_BASE`
  (默认 30s)翻倍至 `TF_ADMIN_LOCK_MAX`(默认 3600s)封顶。
- 封锁窗口内的请求须不再校验钥匙、不写审计。
- 验钥成功须清除该来源的失败计数。
- 限流为单进程内存态(`uvicorn.run(app)` 无 `--workers`);若改多 worker,各 worker 计数独立、阈值
  实际放大,届时须换共享存储。

## 真实客户端 IP(MUST)
- 仅当 `TF_TRUST_PROXY=1` 时,客户端 IP 取自 `X-Forwarded-For`(可信反代追加的最右段);否则取连接对端 IP。
- 未声明可信反代时,须不信任请求自带的 `X-Forwarded-For`。
- `admin_audit` 的 actor 须记录上述真实客户端 IP。

## 删除模型(MUST)
- 删除是硬删;不引入软删/隐藏标记。
- 一次删除请求携带 `targets[]`(选择器列表),在单个事务内完成、对应一个回收站批次;失败则整批不生效。
- 选择器恰为以下之一:
  - `session_ids`:精确全 id(不支持前缀)。
  - `operator`(可选 `agent`/`runtime`):operator 比较走 `lower(trim)`。
  - `before_day`(必须带 `operator`):语义 `day < before_day`,UTC 日期;禁止全局无 operator 作用域。
  - `skill`:库内原值精确匹配(不做 lower)。
- 删除集按选择器类型确定作用域,**session 不再是 operator 路径的删除原子单位**:
  - `operator`(含其 `agent`/`runtime`/`before_day` 变体):删除集只含 `lower(trim(operator))` **等于该 operator**
    的 events 与 skill_uses 行;即以「行所属 session ∈ 该 operator 的会话」**且**「行的 operator = 该 operator」为准,
    同一 `session_id` 下属于**其他具名 operator** 的行不得并入。
  - 空 operator(NULL/`''`)行不得被 operator 选择器带走(共用 session 下不可靠归属,留作孤儿;如需清理走 `session_ids`)。
  - `session_ids`:仍整删该 session 的全部行(用户精确点选,保留原子语义),覆盖保留期裁剪后 events 已无、
    skill_uses 残留的孤儿。
  - `skill`:不变,只触 `skill_uses`。
- `cascade_children=true` 时沿 `parent_session_id` 递归将后代会话并入目标集;operator 路径下后代同样按当前 operator
  收口(仅并入该 operator 名下的后代行),不得借后代会话把他人行卷入。
- 现实依据:真实数据中同一 `session_id` 可挂多个 operator —— 哨兵 session(`*-doctor` 等客户端固定 id 被全员共用)
  与 operator 改名遗留(旧名/新名同处一会话)。规格不假设 session 单操作员独占;删除在共用 session 下仍不得误伤他人。

## 级联与派生态(MUST)
- 删除 session 集时,`events` 与对应 `skill_uses` 必须一并删除,并容忍"skill_uses 在、events 不在"。
- 派生态重算的输入集必须是**收口后的删除集**:按 operator 删除时,`skills_seen` 漂移与 `identities` 清理只应由
  该 operator 自身被删的行触发,不受共用 session 中他人行影响。
- `skills_seen` 按重算处理:对受影响 skill 名,剩余 `skill_uses` 仍有引用则
  `first_day = min(剩余 day)`,无引用才删行。
- `identities`:某 `norm` 在 `events ∪ skill_uses` 已无任何引用,才删该归一行。
- 删整张身份卡(operator+agent+runtime)时连带删 `profiles`;`operators` token 绑定默认保留,仅 `revoke=true` 时删。
- `skill` 选择器只触 `skill_uses` + 重算 `skills_seen`,不动 `events`。
- 回收站 payload 存源头表 `events / skill_uses / profiles`;`revoke=true` 时还存被删的 `operators`
  绑定。`skills_seen / identities` 为派生态,删与恢复均重算。

## 预览即承诺(MUST)
- `POST /api/admin/preview` dry-run:返回逐表将删行数、副作用(受影响 operator、`skills_seen.first_day` 漂移、
  将清掉的身份卡)与 `preview_token`;不写主数据。
- 预览的逐表行数、`operators` 列表、`first_day` 漂移、将清身份卡必须与收口后的删除集一致:按单一 operator 删除时
  `operators` 只含该 operator,计数等于其自身行数。
- `DELETE /api/admin/data` 必须回带 `preview_token`;服务端重算集合,与 token 不一致则返回 409。

## 导出(MUST)
- 整库导出走 `POST /api/admin/export`(带副作用的高危操作,不暴露为可被预取/缓存的 `GET`)。
- 导出整库一致快照(含敏感字段 instructions/memory/input/output,只读不改主数据),不可逆,因此须二次确认:
  请求体须带 `{"confirm":"EXPORT"}`,缺失则拒绝(400)。
- 须纳入上述速率限制(经 `check_admin` 统一覆盖)。
- 鉴权同其它 `/api/admin/*`(`X-TF-Admin-Key`);未配置 `TF_ADMIN_KEY` 时 403。
- 因 SQLite 跑 WAL,不得直接拷 `$TF_DB` 文件(可能撕裂或漏掉未 checkpoint 的页);须在写锁内用
  `VACUUM INTO` 生成自包含快照,流式返回后删临时文件。
- 响应带 `Content-Disposition: attachment`,文件名 `tf-YYYYMMDD-HHMMSS.db`(UTC 时间戳)。
- 每次导出写一条 `admin_audit`(`action=export`)并标记为高危;审计不得记录明文管理钥匙。

## 护栏(MUST)
- 单次影响 > `TF_ADMIN_MAX_ROWS`(默认 200)行或跨 > 1 个 operator 时,请求须带与实际行数一致的
  `confirm_count`,否则拒绝。
- 对心跳窗(`STALE_SECONDS`)内仍在上报的活跃会话,默认拒删;须带 `force=true` 才删。
- 兼容 `DELETE /v1/events` 须受与 `/api/admin/data` 同等的可即时判定护栏:活跃会话需 `force=true`,
  超 `TF_ADMIN_MAX_ROWS` / 跨多 operator 需 `confirm_count` 匹配 `total_rows`(不要求 `preview_token`,
  以保留一次性 curl:删一次读回 `total_rows` 再带 `confirm_count`)。该端点标废弃,推荐改用 `/api/admin/data`。

## 回收站与审计(MUST)
- `admin_trash` 一批次一行,存源头行原文、selector、actor、counts;`POST /api/admin/restore` 整批恢复。
- 恢复:源头行 `INSERT OR IGNORE` 回库,`events` 不复用旧自增 id;之后重算派生态;
  逐表回报 `inserted / skipped`。
- `admin_trash` 按 `TF_TRASH_DAYS`(默认 30)真删过期批次;`admin_audit` 为 append-only。
- `admin_audit` 记 `delete / restore / purge_trash / denied / retention_prune / export`。
- 保留期裁剪(`_maybe_prune`)不进回收站、不逐行审计,只写一条汇总审计行;与用户删除是两条独立路径。

## 前端规则(MUST)
- `/admin` 为直链后台,不进顶栏导航。
- 进页输入 `X-TF-Admin-Key`,本会话用 `sessionStorage` 暂存;后续请求带同名请求头。
- 页面包含清单(operators/identities/sessions/skills 四视角)、按 operator+before_day 的日期清理入口、预览、
  活跃会话明细、确认删除、回收站恢复。
- 警示条右端提供「导出 DB」按钮:点击先弹二次确认;因 `<a download>` 带不了请求头,走 `POST`(带
  `X-TF-Admin-Key` 与 `{"confirm":"EXPORT"}`)→ blob → 触发下载;文件名取响应 `Content-Disposition`。

## 安全响应头(MUST)
- 所有响应须带 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`(并以 CSP `frame-ancestors 'none'`
  等效加固)、`Referrer-Policy: no-referrer`。
- 须带锁定本源的 `Content-Security-Policy`:`script-src 'self'`、`connect-src 'self'`(作为 XSS 盗取
  `sessionStorage` 管理钥匙的纵深防御),放行前端实际依赖的样式/字体/图床来源。
- 经识别为 HTTPS(`TF_HSTS=1`,或可信反代 `X-Forwarded-Proto=https`,或连接本身 https)的部署须带
  `Strict-Transport-Security`。

## 可验证行为
- 未配置 `TF_ADMIN_KEY` → 任意 `/api/admin/*` 返回 403。
- 按 session 删后:`/api/skills`、`/api/state`、`/api/operator/{name}` 中该对象消失;回收站 +1 批次。
- 删某 skill 的首次出现会话后:该 skill 若仍有其它会话引用,`skills_seen.first_day` 取剩余最早日。
- 共用 session(operator A、B 同 `session_id`):按 A 删 → 删除集只含 A 的 events/skill_uses,B 的行与预览
  `operators` 均不含;删完后 B 仍可在 `/api/state`、`/api/operator/B` 正常出现。
- 哨兵 session(如 `codex-doctor`,多 operator 共用同一 `session_id`):按其中一人删 → 仅删该人行,其余人行保留。
- 按 `session_ids` 显式删除共用 session → 仍整删该 session 全部行(不被 operator 过滤削弱)。
- preview 后数据未变 → DELETE 200;preview 后集合变化 → DELETE 409。
- 删后 restore → 源头表行恢复;审计含 delete 与 restore。
- `POST /api/admin/export`:错误钥匙 → 403;缺 `confirm=EXPORT` → 400;正确钥匙 + confirm → 200 且返回
  可被 sqlite 打开、含当前数据(含仅在 WAL 中的写入)的 `.db`;审计 +1 条高危 `export`;临时快照文件不残留。
- 连续错钥达阈值 → `429` + `Retry-After`;封锁期带正确钥匙仍 `429`;到期可恢复;多轮触发退避指数增长且封顶。
- 爆破 N 次后 `admin_audit` 的 `denied` 行数 ≤ 经历的窗口数。
- `TF_TRUST_PROXY=0` 时伪造 `X-Forwarded-For` 不改变限流分桶;`=1` 时不同真实 IP 各自独立计数。
- 兼容 `DELETE /v1/events` 超 `MAX_ROWS` 无 `confirm_count` → 拒绝;删活跃会话无 `force` → 拒绝。
- 响应含上述安全头;非 HTTPS 不发 HSTS。
