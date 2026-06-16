# ADR-0020 后台数据清理:硬删 + 回收站 + 审计,不软删;管理鉴权与 TF_KEY 隔离

- 状态:Proposed
- 关联:ADR-0001(单容器/单文件 SQLite)、ADR-0002(写凭证仅 TF_KEY)、ADR-0014(保留期裁剪 / 存储限制)、`openspec/changes/admin-data-cleanup/`、specs/admin
- 后续:ADR-0021 收口本文「删除全表级联」中隐含的「session 单操作员独占」假设(operator 路径删除改为按 operator 收口到本人行)

## 背景 / 问题
生产看板会混入测试数据与同事配置错误上传的数据,污染 Pods 看板、operator 列表与 SKILLS 排行,需要在生产**安全删除**这些数据。现有 `DELETE /v1/events` 只删 events(可选 profiles),删不干净;且复用全队分发的 `TF_KEY`,人人可删;无预览、不可逆、无留痕。需要定下删除的数据模型与鉴权边界。

## 决策
- **硬删,不软删。** 不引入 `deleted_at`/隐藏标记。原因:页面干净要求每条读查询都带过滤(`server/app.py` 约十处聚合,漏一处脏数据就漏回视图,与目标相悖);软删与 `skill_uses(session,skill,mode)` 等自然键幂等 upsert 冲突;行只增不减违背单容器有界存储与 ADR-0014 的 90 天裁剪。
- **可逆靠回收站,不靠软删。** 删除前把**源头表** `events / skill_uses / profiles` 行快照进 `admin_trash`(一次删除=一批次),`POST /api/admin/restore` 整批恢复;按 `TF_TRASH_DAYS`(默认 30)真删过期批次。`skills_seen` / `identities` 是**派生态**,删与恢复均**重算**,从不快照、从不直接恢复(避免漂移)。
- **可审计靠 append-only 审计表。** `admin_audit` 记 `delete / restore / purge_trash / denied`,永不删。保留期裁剪(`_maybe_prune`)不进回收站、不逐行审计,只写一条汇总行——自动裁剪与用户删除是两条独立路径。
- **删除全表级联,一处定义。** 所有删除入口(含改造后的 `DELETE /v1/events`)都走单一 `_purge()`,在单事务内级联 events→skill_uses→重算 skills_seen/identities→身份连带 profiles;`operators`(token 绑定)默认保留,仅 `revoke=true` 才删——删数据 ≠ 注销同事入职令牌(承 ADR-0011)。
- **预览即承诺。** preview 返回解析主键集合的 `preview_token`,delete 必须回带;集合变动则 409。删的是"预览的那一组",不重跑选择器查询,避免确认瞬间把新进真数据一并带走。
- **管理鉴权与写凭证隔离。** 新增 `TF_ADMIN_KEY`(请求头 `X-TF-Admin-Key`),与采集 `TF_KEY` 相互独立;未配置时管理接口一律 403(默认关)。生产由 Coolify Magic 变量 `${SERVICE_PASSWORD_64_ADMIN}` 自动生成、后台复制,不随 `install.sh` 分发给同事。

## 后果
- ✅ 删完页面立即干净(含 SKILLS / operator 列表);误删可从回收站恢复;操作可追溯;破坏性权限不再随写凭证扩散。
- 约束:新增读查询无需关心"已删"过滤(因硬删);但任何新的删除路径**必须走 `_purge`**,不得绕过级联与留底直接 `DELETE`。
- 取向(可推广为团队规范):应强制的是"破坏性删除必须可逆且可审计"(性质),而非"所有表必须软删"(实现);append-only 遥测/事件表用硬删 + 留底。
