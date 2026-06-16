# spec delta:admin(后台数据清理域 · 本变更新增)

> 这是一个**新增 spec 域**。合入后落到 `openspec/specs/admin/spec.md`。
> 事实来源:`server/app.py` 的 `/api/admin/*` 与改造后的 `DELETE /v1/events`。

## 鉴权(MUST)
- 所有 `/api/admin/*` 须带请求头 `X-TF-Admin-Key` 且等于服务端 `TF_ADMIN_KEY`。
- `TF_ADMIN_KEY` 为空(未配置)时,管理接口**一律 403**(生产安全默认关)。
- `TF_ADMIN_KEY` 与采集写侧 `TF_KEY` **相互独立**:持有 `TF_KEY` 不得据此访问管理接口。
- 被拒的删除尝试(403)须写一条 `admin_audit`(action=denied)。

## 删除模型(MUST)
- 删除是**硬删**;不引入软删/隐藏标记。
- 一次删除请求携带 `targets[]`(选择器列表),在**单个事务**内完成、对应**一个回收站批次**;失败则整批不生效。
- 选择器恰为以下之一:
  - `session_ids`:精确全 id(不支持前缀)。
  - `operator`(可选 `agent`/`runtime`):operator 比较走 `lower(trim)`。
  - `before_day`(**必须**带 `operator`):语义 `events.day < before_day`,UTC 左闭;禁止全局无 operator 作用域。
  - `skill`:库内原值精确匹配(不做 lower)。
- 目标集按 **`events ∪ skill_uses`** 取并集(覆盖保留期裁剪后 events 已无、skill_uses 残留的孤儿)。
- `cascade_children=true` 时沿 `parent_session_id` 递归将后代会话并入目标集。

## 级联与派生态(MUST)
- 删除 session 集时,`events` 与对应 `skill_uses` 必须一并删除(后者按 `session_id IN 集`),并容忍"skill_uses 在、events 不在"。
- `skills_seen` **不直接删,按重算处理**:对受影响 skill 名,剩余 `skill_uses` 仍有引用则 `first_day = min(剩余首见日)`,无引用才删行。
- `identities`:某 `norm` 在 `events ∪ skill_uses` 已无任何引用,才删该归一行。
- 删整张身份卡(operator+agent+runtime)时连带删 `profiles`;`operators`(token 绑定)**默认保留**,仅 `revoke=true` 时删。
- `skill` 选择器只触 `skill_uses` + 重算 `skills_seen`,**不动 `events`**。
- 回收站 payload **只存源头表** `events / skill_uses / profiles`;`skills_seen` / `identities` 为派生态,删与恢复均重算,不快照、不直接恢复。

## 预览即承诺(MUST)
- `POST /api/admin/preview` 干删:返回逐表"将删 N 行"、副作用(受影响 operator 列表、`skills_seen.first_day` 漂移、将清掉的身份卡)与 `preview_token`(解析主键集合的内容 hash);**不写库**。
- `DELETE /api/admin/data` 必须回带 `preview_token`;服务端重算集合,与 token 不一致(预览后数据变动)则返回 **409**。删除作用于"预览时解析出的集合",不重跑选择器查询。

## 护栏(MUST)
- 单次影响 > `TF_ADMIN_MAX_ROWS`(默认 200)行或跨 > 1 个 operator 时,请求须带与实际行数一致的 `confirm_count`,否则拒绝。
- 对心跳窗(`STALE_SECONDS`)内仍在上报的活跃会话,默认**拒删**;须带 `force=true` 才删。

## 回收站与审计(MUST)
- `admin_trash` 一批次一行,存源头行原文、selector、actor、counts;`POST /api/admin/restore` 整批恢复。
- 恢复:源头行 `INSERT OR IGNORE` 回库,`events` **不复用旧自增 id**;之后重算派生态;逐表回报"成功/键冲突跳过",不静默。
- `admin_trash` 按 `TF_TRASH_DAYS`(默认 30)真删过期批次;`admin_audit` 为 append-only、永不删。
- `admin_audit` 记 `delete / restore / purge_trash / denied`。
- **保留期裁剪(`_maybe_prune`)不进回收站、不逐行审计**,只写一条汇总审计行(行数 + cutoff);与用户删除是两条独立路径。

## 不变量
- 不引入软删、外部数据库、账号体系/RBAC、token/成本字段(承 ADR-0001/0002)。
- 管理接口不影响采集写入与安装分发:`POST /v1/events`、`/install.sh`、`/shims/*`、`/healthz` 行为不变。

## 可验证行为(示例)
- 未配置 `TF_ADMIN_KEY` → 任意 `/api/admin/*` 返回 403。
- 按 session 删后:`/api/skills`、`/api/state`、`/api/operator/{name}` 中该对象消失;回收站 +1 批次。
- 删"某 skill 首次出现"的会话后:该 skill 若仍有其它会话引用,`skills_seen.first_day` 取剩余最早日、不消失。
- preview 后数据未变 → DELETE 200;preview 后又进新事件使集合变化 → DELETE 返回 409。
- 删后 restore → 各表行数复原;审计含 delete 与 restore 两条。
- `before_day` 不带 operator → 400;影响 > 200 行不带 `confirm_count` → 拒绝。
