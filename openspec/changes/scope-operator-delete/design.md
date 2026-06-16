# 设计：scope-operator-delete

## 方案
改 `server/app.py` 一个文件,把 operator 约束贯穿到「按 session 反查」那一层:

1. **反查函数加 operator 过滤**(三处,均加可选 `operator_norm` 参数,有值时追加 `AND lower(trim(COALESCE(operator,'')))=?`):
   - `_event_ids_for_sessions`
   - `_skill_keys_for_sessions`
   - `_expand_child_sessions`(后代会话只在同 operator 范围内扩展)
2. **`_resolve_admin_targets` 主干改造**:不再把所有 operator 的 session 倒进一个公共池子做无差别反查,而是**逐 target 带各自 operator 约束**解析后再取并集:
   - `operator`(含 `agent`/`runtime`)target → 反查时传该 operator 的 `_norm_op`,收口。
   - `before_day`(必带 operator)target → 同样按该 operator 收口。
   - 裸 `session_ids` target → 不加过滤,整删该 session(用户精确点选)。
   - `skill` target → 不变(本就按 skill_uses)。
3. 预览侧 `_preview_admin_resolution` 无需改:`operators` 列表、`first_day_changes`、`identities_cleared` 都是从收口后的删除集反推的,自动正确。

## 权衡
- **session 不再是删除原子单位(按 operator 路径)**:历史实现把 session 当原子单位,是为了顺带清掉「同 session 内无 operator 标记」的附属行。收口后这类空 operator 行不再被 operator 选择器带走。
- **空 operator(NULL/'')行的归属**:本方案**严格按具名匹配**,空 operator 行不并入 operator 删除集。理由:在共用 session(哨兵)场景下,空行无法可靠归属某人,宁可留作孤儿也不误删他人侧。确有需要清理的空行,走 `session_ids` 显式选择器。
- 未选「合并/改名」路线:本次只保证删除不越界;operator 改名遗留(如 `tranfu`→`Ocean`)按用户决定**照删不并**,不引入身份合并能力。

## 风险
- **回归**:`session_ids` / `skill` 显式删除路径必须保持整删,不被新过滤误伤——用单测钉死。
- **skill_uses 主键不含 operator**(`(session_id, skill, mode)`):共用 session 同一 skill 只有一行,其 operator 为写入时的值;按 operator 过滤 skill_uses 时,该行只在 operator 命中时才删,属保守行为(不会误删他人),可接受。
- 回滚:改动集中在解析函数,回退该 commit 即恢复旧行为;不涉及数据迁移。
