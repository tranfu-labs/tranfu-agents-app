# 规格（delta）：admin —— 按 operator 删除收口到本人行

事实来源：`server/app.py` 的 `_resolve_admin_targets` / `_event_ids_for_sessions` / `_skill_keys_for_sessions` / `_expand_child_sessions` / `_preview_admin_resolution`。本 delta 在现有 `openspec/specs/admin/spec.md` 的「删除模型」「级联与派生态」「可验证行为」基础上**修改/补充**下列条款，实现完成后合并回主规格。

## 删除模型（MUST）—— 修改
- 删除集 MUST 按选择器类型确定作用域，**session 不再是 operator 路径的删除原子单位**：
  - `operator`（含其 `agent` / `runtime` / `before_day` 变体）：删除集 MUST 只含 `lower(trim(operator))` **等于该 operator** 的 events 与 skill_uses 行。即以「行所属 session ∈ 该 operator 的会话」**且**「行的 operator = 该 operator」为准；同一 `session_id` 下属于**其他具名 operator** 的行 MUST NOT 并入。
  - 空 operator（NULL/`''`）行 MUST NOT 被 operator 选择器带走（共用 session 下不可靠归属，留作孤儿；如需清理走 `session_ids`）。
  - `session_ids`：仍 MUST 整删该 session 的全部行（用户精确点选，保留原子语义）。
  - `skill`：不变，只触 `skill_uses`。
- `cascade_children=true` 沿 `parent_session_id` 递归并入后代会话时，MUST 同样按当前 operator 收口（仅并入该 operator 名下的后代行），不得借后代会话把他人行卷入。

> 现实依据：真实数据中同一 `session_id` 可挂多个 operator —— 哨兵 session（`*-doctor` 等客户端固定 id 被全员共用）与 operator 改名遗留（旧名/新名同处一会话）。规格不假设 session 单操作员独占；删除在共用 session 下仍 MUST 不误伤他人。

## 级联与派生态（MUST）—— 修改
- 派生态重算口径不变（`skills_seen.first_day` 取剩余 `skill_uses` 的 `min(day)`、无引用才删行；`identities` 在 `events ∪ skill_uses` 无任何引用才删归一行）。但其输入集 MUST 是**收口后的删除集**：按 operator 删除时，`skills_seen` 漂移与 `identities` 清理只应由该 operator 自身被删的行触发，不受共用 session 中他人行影响。

## 预览即承诺（MUST）—— 补充
- `POST /api/admin/preview` 返回的逐表行数、`operators` 列表、`skills_seen.first_day` 漂移、将清掉的身份卡，MUST 与上述收口后的删除集一致：按单一 operator 删除时 `operators` 只含该 operator，计数等于其自身行数。

## 可验证行为 —— 新增
- 一个 session 由 operator A、B 共用：按 A 删除 → 删除集只含 A 的 events/skill_uses；B 的行与预览 `operators` 均不含；A 在该 session 的删除完成后 B 仍可在 `/api/state`、`/api/operator/B` 正常出现。
- 哨兵 session（如 `codex-doctor`，多 operator 共用同一 `session_id`）：按其中一人删除 → 仅删该人行，其余人行保留。
- 按 `session_ids` 显式删除共用 session → 仍整删该 session 全部行（不被 operator 过滤削弱）。
- 真实样本：导出库中 `tranfu`（自身 26 events / 4 skill_uses，与 `Ocean` 等共用多个 session）预览删除 → `events=26`、`skill_uses=4`、`operators=[tranfu]`（而非旧行为的 45 行 / 9 个 operator）。
