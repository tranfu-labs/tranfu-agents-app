# 设计:admin-data-cleanup

## 1. 鉴权(与 TF_KEY 隔离)
- 新增 `TF_ADMIN_KEY = os.environ.get("TF_ADMIN_KEY","")`;新增 `check_admin(key, request)`:校验请求头 `X-TF-Admin-Key`,**未配置该环境变量时一律 403**(默认关)。从 `request.client.host` 取 IP 拼成 `actor` 供审计。
- Coolify 部署:`compose.yml` 写 `TF_ADMIN_KEY: ${SERVICE_PASSWORD_64_ADMIN}`,Coolify 首次部署自动生成 64 位纯字母数字(可直接进 HTTP 头,无需转义)并持久化;运维去 Environment Variables 复制。本地开发用 `export TF_ADMIN_KEY=$(openssl rand -hex 32)` 生成强随机值,勿用易猜口令。

## 2. 数据模型(两张新表)
```sql
-- 回收站:一次删除=一个批次,只存源头表行原文用于恢复。
CREATE TABLE admin_trash (
  batch_id TEXT PRIMARY KEY,   -- uuid4
  created  TEXT,               -- UTC iso
  actor    TEXT,               -- key 标识 + 来源 IP
  selector TEXT,               -- 删除请求 JSON(targets 原文)
  payload  TEXT,               -- {events:[…], skill_uses:[…], profiles:[…]} 仅源头表
  counts   TEXT,               -- 各表删除行数
  restored INTEGER DEFAULT 0
);
-- 审计:append-only,每个动作一行,永不删。
CREATE TABLE admin_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, actor TEXT, action TEXT,   -- delete | restore | purge_trash | denied
  selector TEXT, counts TEXT, batch_id TEXT
);
```
- 回收站有界:仿 `_maybe_prune` 加 `_maybe_prune_trash`,按 `TF_TRASH_DAYS`(默认 30)真删过期批次;审计行不删。
- **回收站只存源头表 `events / skill_uses / profiles`**;`skills_seen` / `identities` 是派生态,删与恢复都用"重算"得到,从不快照、从不直接恢复(避免漂移)。

## 3. 核心:`_purge()` 全表级联(一处定义,单事务 + `_lock`)
所有删除入口都走它,先快照后删除,要么全成要么全不动:
1. **解析目标集**:把 `targets[]` 里每个选择器解析成受影响主键集合,取并集。目标集按 **`events ∪ skill_uses`** 取(因保留期裁剪只删 events、`skill_uses` 长期留,会产生 events 已无但 skill_uses 还在的孤儿,必须能清)。可选 `cascade_children=true` 时沿 `parent_session_id` 递归把后代会话并入。
2. **收集受影响 skill 名**:`SELECT DISTINCT skill FROM skill_uses WHERE session_id IN S`,留给步骤 5 重算。
3. **快照源头行进回收站 payload**:`events / skill_uses / profiles`。
4. **删主数据**:`DELETE events`;`DELETE skill_uses`(按 session 集);容忍"skill_uses 在、events 不在"。
5. **重算 `skills_seen`**(不是删):对步骤 2 每个 skill 名——剩余 `skill_uses` 还有引用则 `UPDATE first_day=min(剩余 day)`,没有了才 `DELETE` 该行。
6. **重算 `identities`**:某 `norm` 在 events/skill_uses 已无任何引用才删。
7. **身份连带**:删整张身份卡时 `DELETE profiles`(operator+ak+runtime);`operators`(token 绑定)**默认不动**,仅 `revoke=true` 才删。
8. 写 `admin_trash` 批次 + `admin_audit`(action=delete),`commit`,返回各表实删行数。

`skill` 选择器分支:只删 `skill_uses WHERE skill=?`(库里原值**精确匹配**,不做 lower)+ 按步骤 5 重算 `skills_seen`,**events 不动**。

## 4. 预览即承诺(防 TOCTOU)
- `POST /api/admin/preview` 跑步骤 1、2 + COUNT,**不写库**,返回:逐表"将删 N 行" + **人需看见的副作用**(受影响 operator 列表、`skills_seen.first_day` 漂移如 `web-search: 06-01→06-05`、会清掉哪些身份卡)+ 一个 `preview_token`(= 解析出的主键集合的内容 hash)。
- `DELETE /api/admin/data` 必须回带 `preview_token`;服务端重算集合,若与 token 不一致(预览后又进了新数据)返回 **409**,要求重新预览。**删的是"你预览的那一组",不是重跑查询**——避免确认瞬间把新进的真数据一并带走。

## 5. 选择器与护栏
- 选择器四类,`targets[]` 列表里每个是其一:
  - `{"session_ids":[…]}`(精确全 id,不支持前缀)
  - `{"operator":…, "agent"?, "runtime"?}`(operator 走 `lower(trim)`)
  - `{"before_day":"YYYY-MM-DD", "operator":…}`:语义 `events.day < before_day`,**UTC、左闭**;**必须带 operator 作用域**,禁止全局一刀切。
  - `{"skill":…}`:精确匹配,只清 `skill_uses`/`skills_seen`。
- **一次用户动作 = 一个 `targets[]` 批次 = 一个事务 = 一个回收站批次**;恢复整批回滚,不出现"恢复一半"。
- **爆炸半径护栏**:单次影响 > `TF_ADMIN_MAX_ROWS`(默认 200)行或跨 > 1 个 operator 时,二次确认必须**手输实际行数**才放行(非输 `DELETE`)。
- **活跃会话**:对心跳窗(`STALE_SECONDS`)内仍在上报的会话,预览标红、**默认拒删**,要删须带 `force=true`,并提示"删了下个心跳会重现,治本要让对方停上报"。

## 6. 恢复
- `POST /api/admin/restore {batch_id}`:把 payload 的 `events/skill_uses/profiles` 行 `INSERT OR IGNORE` 回去,再对受影响 skill/operator **重算** `skills_seen`/`identities`(与删除共用同一重算函数)。
- `events` 恢复**不复用旧自增 id**(去掉 id 列重插;父子关系靠 `session_id` 不靠行 id,不受影响)。
- 恢复**逐表回报"成功 N / 因键冲突跳过 M"**,不静默吞掉(键已被新数据占用时让人看见)。置 `restored=1`,补 `admin_audit`(action=restore)。

## 7. 审计范围
- 记 `delete` / `restore` / `purge_trash`,**也记被拒的删除尝试**(403,action=denied,安全信号)。preview 不记(噪声)。
- **保留期裁剪不走回收站、不逐行审计**:`_maybe_prune` 是自动滚动硬删,只写**一条汇总审计行**(裁了 N 行、cutoff=X);与用户删除两条路径在代码与文档里显式分开。

## 8. 端点一览(均过 `check_admin`)
| 方法 + 路径 | 用途 |
|---|---|
| `GET /api/admin/inventory` | 列可清理对象(operator/identity/session/skill),各带行数、最近活跃、是否活跃中;取数 `events ∪ skill_uses` |
| `POST /api/admin/preview` | 干删:逐表 COUNT + 副作用 + `preview_token`,不写库 |
| `DELETE /api/admin/data` | 真删:回带 `preview_token`,走 `_purge`,以实删数回显 |
| `GET /api/admin/trash` | 回收站批次列表 |
| `POST /api/admin/restore` | 恢复批次 |

`DELETE /v1/events`(现有)改造为内部调 `_purge`,对外行为兼容,顺带补上它今天漏清的级联。

## 9. 前端
- 受保护路由 `/admin`(`views/Admin.tsx`),**不进顶栏导航**,直链进入;进页弹钥匙框,存 `sessionStorage`,后续请求带 `X-TF-Admin-Key`。
- 三块 + 回收站:清单(四 tab,勾选)→ 预览(逐表 + 副作用)→ 二次确认(护栏:输行数/输 `DELETE`)→ 回收站(列批次、恢复)。线框见 `docs/wireframes/pages/admin.md`。

## 权衡
- **为何不用软删**:页面干净要求每条读查询都带 `deleted_at IS NULL`(`server/app.py` 有约十处聚合:`_iter_sessions`/`metrics`/`leverage`/`skills_overview`/`operator_detail_payload`/`skill_detail_payload`/`_snapshot`…),漏一处脏数据就漏回来,与目标相悖;软删还与 `skill_uses`(session,skill,mode)等自然键幂等 upsert 冲突,且行只增不减违背有界存储与保留期裁剪。硬删 + 回收站以低一个量级的成本拿到等价的"可逆 + 留痕"。
- **公司级规范取向**:应强制的是"破坏性删除必须可逆且可审计"(性质),而非"所有表必须软删"(实现);append-only 遥测/事件表用硬删 + 留底。

## 风险
- 最大风险:**误删真实数据**。缓解:预览即承诺(`preview_token` + 409)、爆炸半径手输行数、回收站可恢复、审计可追溯。
- 次风险:**漏级联导致页面没删干净**。缓解:全部走单一 `_purge`,测试显式断言删后 `/api/skills`、`/api/state`、`/api/operator/{name}` 里对象消失。
- 回滚思路:管理端点是新增、`DELETE /v1/events` 改造保持兼容;最坏情况下移除 `/api/admin/*` 与 `Admin.tsx`、回退 `DELETE /v1/events` 即可,不影响采集与看板。
