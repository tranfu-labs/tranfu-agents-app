# 提案：scope-operator-delete（按 operator 删除收口到本人行）

## 背景
后台「按 operator 清理」存在越界删除风险:在管理页只勾选一个 operator(如 `tranfu`)预览删除影响时,删除集会把**与该 operator 共用同一 `session_id` 的其他具名 operator 的行**也并进来。一份真实导出库(`tf-20260616-104556.db`)上复现:删 `tranfu`(自身 26 events / 4 skill_uses)预览出 **45 events、牵连 9 个 operator**。

根因是删除解析的两段式:`_resolve_admin_targets` 先按 operator 查出 session 集,再按 `session_id IN (...)` **不带 operator 条件**反查全部 events/skill_uses(`_event_ids_for_sessions` / `_skill_keys_for_sessions` / `_expand_child_sessions`)。现有「删除模型」规格隐含假设 **session 单操作员独占**,但真实数据并不满足:

- **哨兵 session**:`codex-doctor` / `claude-code-doctor` / `openclaw-doctor` 等诊断命令在客户端硬编码了固定 `session_id`,全员上报灌进同一个 id(`codex-doctor` 单个被 9 人共用)。
- **operator 改名**:同一真实会话里 operator 中途由旧名切到新名(库中 `tranfu` 实为某人改名 `Ocean` 前的占位名),致使一个 UUID session 挂两个 operator。

规格不应假设数据干净;删除语义必须在「共用 session」下仍可预测、不误伤他人。

## 提案
把「按 operator 删除」的删除集从**整 session 无差别**收口为**按 operator 精确匹配**:删某 operator 时,只删 `lower(trim(operator))` 等于该 operator 的 events 与 skill_uses 行;同一 session 内属于**其他具名 operator** 的行一律不并入。显式 `session_ids` 选择器仍整删该 session 全部行(用户精确点选,保留原子语义);`skill` 选择器不变;`cascade_children` 沿后代递归时同样按 operator 收口。

## 影响
- 业务域:**admin**(删除模型 / 级联与派生态 / 预览即承诺)。
- 对外行为:按 operator(及其 `before_day` / `cascade_children` 变体)删除时,预览与实删的 events/skill_uses 计数、`operators` 列表、`skills_seen.first_day` 漂移、`identities` 清理判定均只反映该 operator 自身;不再连带删除共用 session 中他人行。显式按 `session_ids` / `skill` 的删除行为不变。
- 数据:本次**不做数据清洗**(哨兵 session 与改名遗留的脏数据保持原样);仅修删除解析逻辑使其在脏数据下也安全。哨兵 session 的产生源(客户端固定 id)与 operator 改名/合并能力另案处理。
