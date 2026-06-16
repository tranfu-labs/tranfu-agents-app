# 任务：scope-operator-delete

## 待实现
- [ ] `_event_ids_for_sessions` 加可选 `operator_norm` 过滤
- [ ] `_skill_keys_for_sessions` 加可选 `operator_norm` 过滤
- [ ] `_expand_child_sessions` 加 operator 过滤(后代会话同 operator 范围内扩展)
- [ ] `_resolve_admin_targets` 改逐 target 带 operator 约束解析:operator / before_day 路径收口,session_ids / skill 路径保持整删
- [ ] 确认预览(`_preview_admin_resolution`)的 `operators` / `first_day_changes` / `identities_cleared` 随收口后删除集自动正确,无需单独改

## 验证
- [ ] 真实库实测:`tf-20260616-104556.db` 跑 `tranfu` 预览 → `events=26 / skill_uses=4 / operators=[tranfu]`(不再是 45 / 9 人)
- [ ] 扩展 `tests/test_admin_cleanup.py`:
  - [ ] 脏数据用例:一个 session 由 A、B 共用 → 删 A 只解析出 A 的行,B 完全不动,预览 `operators` 仅含 A
  - [ ] 哨兵用例:`codex-doctor` 式多人共用 → 删 A 留下其余人
  - [ ] 回归用例:按 `session_ids` 显式删,仍整删该 session 全部行(不被新过滤误伤)
  - [ ] 回归用例:`skill` 选择器行为不变
- [ ] `pytest tests/` 全绿;`python -m py_compile server/app.py`
- [ ] 把本目录 `specs/` delta 合并回 `openspec/specs/admin/spec.md`
