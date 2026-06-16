# ADR-0021 按 operator 删除收口到本人行:session 不再是 operator 路径的删除原子单位

- 状态:Proposed
- 关联:ADR-0020(后台清理:硬删+回收站+审计)、ADR-0011(per-operator 令牌身份)、`openspec/changes/scope-operator-delete/`、specs/admin
- 修订:收口 ADR-0020「删除全表级联」中**隐含的「session 单操作员独占」假设**(operator 路径)

## 背景 / 问题
ADR-0020 把删除定义为「全表级联,一处定义」,在 `_purge()` 单事务内级联 events→skill_uses→重算派生态,并以 session 为操作单位。其隐含前提是**一个 `session_id` 只属于一个 operator**——按 operator 解析删除集时,先按 operator 查出会话集,再按 `session_id IN (...)` **不带 operator 条件**反查全部行。

真实数据并不满足该前提,一个 `session_id` 会挂多个 operator:
- **哨兵 session**:`codex-doctor` / `claude-code-doctor` / `openclaw-doctor` 等诊断命令在客户端硬编码固定 `session_id`,全员上报灌进同一 id(`codex-doctor` 单个被 9 人共用)。
- **operator 改名遗留**:同一真实会话里 operator 中途由旧名切到新名,一个 UUID session 挂两个 operator。

后果是越界删除:导出库 `tf-20260616-104556.db` 上删 `tranfu`(自身 26 events / 4 skill_uses)预览出 **45 events、牵连 9 个 operator**。

## 决策
- **operator 路径的删除集收口到本人行。** 删某 operator(含其 `agent`/`runtime`/`before_day` 变体)时,删除集只含 `lower(trim(operator))` **等于该 operator** 的 events 与 skill_uses 行;同一 `session_id` 下属于**其他具名 operator** 的行不并入。实现:`_event_ids_for_sessions` / `_skill_keys_for_sessions` / `_expand_child_sessions` 加可选 `operator_norm` 过滤,`_resolve_admin_targets` 改为**逐 target 带各自 operator 约束**解析后取并集。
- **空 operator(NULL/`''`)行不被 operator 选择器带走。** 共用 session 下空行无法可靠归属,宁可留作孤儿也不误删他人侧;确需清理走 `session_ids`。
- **显式选择器语义不变。** 裸 `session_ids` 仍整删该 session 全部行(用户精确点选,保留原子语义);`skill` 仍只触 `skill_uses`。`cascade_children` 沿后代递归时,operator 路径下同样按 operator 收口。
- **不做数据清洗、不引入身份合并。** 哨兵 session 的产生源(客户端固定 id)与 operator 改名/合并能力另案处理;本次只保证删除不越界,改名遗留按用户决定照删不并。

## 后果
- ✅ 共用 session 下删除可预测、不误伤他人:删一人留其余人;预览的逐表计数、`operators` 列表、`skills_seen.first_day` 漂移、`identities` 清理均只反映该 operator 自身。导出库 `tranfu` 预览回到 `events=26 / skill_uses=4 / operators=[tranfu]`。
- 约束修订:**session 不再是 operator 路径的删除原子单位**(ADR-0020 仍成立,`_purge` 的级联/回收站/审计不变;改的只是 `_resolve_admin_targets` 的解析作用域)。历史实现把 session 当原子单位顺带清掉「同 session 内无 operator 标记」的附属行,收口后这类空 operator 行不再被 operator 选择器带走——按 `session_ids` 显式删。
- `skill_uses` 主键 `(session_id, skill, mode)` 不含 operator:共用 session 同一 skill 只有一行,按 operator 过滤时仅在 operator 命中才删,属保守行为(不误删他人),可接受。
- 回退:改动集中在解析函数,回退该 commit 即恢复旧行为,不涉及数据迁移。
