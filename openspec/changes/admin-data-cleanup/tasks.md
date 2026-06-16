# 任务:admin-data-cleanup

## 鉴权与配置
- [x] `server/app.py`:加 `TF_ADMIN_KEY` 读取 + `check_admin(key, request)`(未配置 → 403,取来源 IP 拼 actor)。
- [x] `compose.yml`:server.environment 加 `TF_ADMIN_KEY: ${SERVICE_PASSWORD_64_ADMIN}`。
- [x] `.env.example`:加「后台清理台」段(说明 Coolify 自动生成 + 本地 export + 未设置默认 403)。

## 数据模型
- [x] `init_db()`:建 `admin_trash`、`admin_audit` 两张表。
- [x] 加 `_maybe_prune_trash`,按 `TF_TRASH_DAYS`(默认 30)真删过期批次;审计行保留。

## 核心删除/恢复
- [x] `_resolve(targets)`:把 `targets[]` 各选择器解析成主键集合(并集,取数 `events ∪ skill_uses`),支持 `cascade_children`;产出 `preview_token`(集合内容 hash)。
- [x] `_recompute_derived(skills, operators)`:删/恢复共用,重算 `skills_seen.first_day` 与 `identities`。
- [x] `_purge(targets, ...)`:单事务 + `_lock`,先快照源头行→删 events/skill_uses→调重算→身份连带(profiles;operators 仅 revoke=true)→写 trash + audit。
- [x] `skill` 选择器分支:精确匹配只删 skill_uses + 重算 skills_seen,events 不动。
- [x] `restore(batch_id)`:INSERT OR IGNORE 回源头表→重算派生→逐表回报"成功/键冲突跳过"→events 不复用旧 id→置 restored=1 + audit。
- [x] 护栏:活跃会话默认拒删(force 才删);影响 > `TF_ADMIN_MAX_ROWS`(默认 200)或跨 > 1 operator 时要求手输行数(后端校验 `confirm_count`)。
- [x] `before_day` 选择器:校验必须带 operator;语义 `day < before_day`,UTC 左闭。

## 端点
- [x] `GET /api/admin/inventory`(operator/identity/session/skill 四视角,标活跃中;取数 `events∪skill_uses`;支持 `q` 搜索 + `limit`/分页;空/null operator 单列一桶可清)。
- [x] `POST /api/admin/preview`(逐表 COUNT + 副作用:受影响 operator、first_day 漂移、清掉的身份卡 + `preview_token`,不写库)。
- [x] `DELETE /api/admin/data`(回带 `preview_token`,不一致 → 409;走 `_purge`,实删数回显)。
- [x] `GET /api/admin/trash`、`POST /api/admin/restore`。
- [x] 改造现有 `DELETE /v1/events` 内部走 `_purge`(对外兼容,补齐级联)。
- [x] `_maybe_prune` 改为:裁剪只写一条汇总审计行,不进回收站。
- [x] 被拒删除(403)写 `admin_audit`(action=denied)。

## 前端
- [x] `frontend/src/views/Admin.tsx` + `App.tsx` 加 `/admin` 路由(不进 TopBar 导航)。
- [x] 进页钥匙浮层 → `sessionStorage` → 后续请求带 `X-TF-Admin-Key`(`lib/api.ts` 加 admin 调用)。
- [x] 三块 + 回收站:清单(四 tab 勾选)/ 预览(逐表 + 副作用)/ 二次确认(护栏)/ 回收站(列批次 + 恢复)。
- [x] 页面文案走 `lib/i18n.ts`(zh/en),不硬编码。
- [x] 清单支持服务端搜索/分页或上限(会话量大时不拉爆),与 `inventory` 的 query 参数对齐。
- [x] 暗/亮主题 + ≤600px 窄屏各看一眼;实现照 `docs/wireframes/pages/admin.md`。

## 文档
- [x] `PROTOCOL.md`:补 admin 接口段(鉴权、选择器、preview_token、回收站语义)。
- [x] `DEPLOY.md`:加 `TF_ADMIN_KEY`(Coolify Magic 变量)/ `TF_TRASH_DAYS` / `TF_ADMIN_MAX_ROWS` 说明 + `VACUUM` 一句脚注。
- [x] `docs/wireframes/pages/admin.md`(桌面/平板/手机三断点 + 注释表)、`flow.md` 加 `/admin` 进入流程边。
- [x] 合并 spec-delta 回 `openspec/specs/admin/spec.md`(实现完成后)。

## 验收(`tests/`,TestClient,CI 自动跑)
- [x] 无 key / 错 key / `TF_ADMIN_KEY` 未配置 → 403;denied 写审计。
- [x] preview 不改库(删前后 count 相等),返回 `preview_token` 与副作用。
- [x] `preview_token` 失配 → DELETE 返回 409。
- [x] 按 session 删:events + skill_uses 归零,`/api/skills` 该会话消失;回收站多一批次。
- [x] 按 skill 删:skill_uses/skills_seen 清掉,events 不变。
- [x] `skills_seen.first_day` 重算:删掉"首次出现"会话后,该 skill 仍有引用时 first_day 取剩余最早值、不消失。
- [x] 按 operator 删:profiles/identities 连带清,operators(token)默认保留;`revoke=true` 才清。
- [x] `events ∪ skill_uses` 取数:events 已被裁、仅 skill_uses 残留的孤儿也能在清单出现并被清。
- [x] `cascade_children`:父会话连子树一起删,无孤儿;`before_day` 缺 operator → 400。
- [x] 活跃会话默认拒删,`force=true` 才删;影响 > 200 行缺 `confirm_count` → 拒绝。
- [x] restore:删后恢复各表复原,键冲突有回报;审计有 delete + restore 两条。
- [x] 回收站超 `TF_TRASH_DAYS` 被裁,审计行保留;保留期裁剪只写一条汇总审计行、不进回收站。
