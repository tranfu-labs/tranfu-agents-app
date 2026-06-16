# 规格:admin(后台数据清理域)

事实来源:`server/app.py` 的 `/api/admin/*`、`/admin` 前端与改造后的 `DELETE /v1/events`。

## 鉴权(MUST)
- 所有 `/api/admin/*` 以及兼容清理路径 `DELETE /v1/events` 须带请求头 `X-TF-Admin-Key` 且等于服务端
  `TF_ADMIN_KEY`。
- `TF_ADMIN_KEY` 为空(未配置)时,管理接口一律 403。
- `TF_ADMIN_KEY` 与采集写侧 `TF_KEY` 相互独立:持有 `TF_KEY` 不得据此访问管理接口。
- 被拒的管理请求须写一条 `admin_audit`(`action=denied`),审计不得记录明文管理钥匙。

## 删除模型(MUST)
- 删除是硬删;不引入软删/隐藏标记。
- 一次删除请求携带 `targets[]`(选择器列表),在单个事务内完成、对应一个回收站批次;失败则整批不生效。
- 选择器恰为以下之一:
  - `session_ids`:精确全 id(不支持前缀)。
  - `operator`(可选 `agent`/`runtime`):operator 比较走 `lower(trim)`。
  - `before_day`(必须带 `operator`):语义 `day < before_day`,UTC 日期;禁止全局无 operator 作用域。
  - `skill`:库内原值精确匹配(不做 lower)。
- 目标集按 `events ∪ skill_uses` 取并集,覆盖保留期裁剪后 events 已无、skill_uses 残留的孤儿。
- `cascade_children=true` 时沿 `parent_session_id` 递归将后代会话并入目标集。

## 级联与派生态(MUST)
- 删除 session 集时,`events` 与对应 `skill_uses` 必须一并删除,并容忍"skill_uses 在、events 不在"。
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
- `DELETE /api/admin/data` 必须回带 `preview_token`;服务端重算集合,与 token 不一致则返回 409。

## 导出(MUST)
- `GET /api/admin/export` 下载整库一致快照(只读,不改主数据)。
- 鉴权同其它 `/api/admin/*`(`X-TF-Admin-Key`);未配置 `TF_ADMIN_KEY` 时 403。
- 因 SQLite 跑 WAL,不得直接拷 `$TF_DB` 文件(可能撕裂或漏掉未 checkpoint 的页);须在写锁内用
  `VACUUM INTO` 生成自包含快照,流式返回后删临时文件。
- 响应带 `Content-Disposition: attachment`,文件名 `tf-YYYYMMDD-HHMMSS.db`(UTC 时间戳)。
- 每次导出写一条 `admin_audit`(`action=export`);审计不得记录明文管理钥匙。

## 护栏(MUST)
- 单次影响 > `TF_ADMIN_MAX_ROWS`(默认 200)行或跨 > 1 个 operator 时,请求须带与实际行数一致的
  `confirm_count`,否则拒绝。
- 对心跳窗(`STALE_SECONDS`)内仍在上报的活跃会话,默认拒删;须带 `force=true` 才删。

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
- 顶栏提供「导出 DB」按钮:因 `<a download>` 带不了请求头,走 fetch(带 `X-TF-Admin-Key`)→ blob → 触发下载;
  文件名取响应 `Content-Disposition`。

## 可验证行为
- 未配置 `TF_ADMIN_KEY` → 任意 `/api/admin/*` 返回 403。
- 按 session 删后:`/api/skills`、`/api/state`、`/api/operator/{name}` 中该对象消失;回收站 +1 批次。
- 删某 skill 的首次出现会话后:该 skill 若仍有其它会话引用,`skills_seen.first_day` 取剩余最早日。
- preview 后数据未变 → DELETE 200;preview 后集合变化 → DELETE 409。
- 删后 restore → 源头表行恢复;审计含 delete 与 restore。
- `GET /api/admin/export`:错误钥匙 → 403;正确钥匙 → 200 且返回可被 sqlite 打开、含当前数据(含仅在 WAL 中的写入)的 `.db`;审计 +1 条 `export`;临时快照文件不残留。
