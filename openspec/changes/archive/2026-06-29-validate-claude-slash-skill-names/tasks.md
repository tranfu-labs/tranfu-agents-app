# 任务：validate-claude-slash-skill-names

## 实现（`shims/tf_hook.py`）

- [x] 1. 加常量 `_CLAUDE_BUILTIN_SLASH`（frozenset，含 `design.md` §4 列出的 ~35 个内置命令名）
- [x] 2. 加辅助 `_extract_user_command_name(line: str) -> str | None`：行级 `json.loads` → `type=="user"` → 取 `message.content`（string 或 list-of-blocks 首个 text 块）→ `lstrip()` 后必须以 `<command-name>` 起头,或以 `<command-message>` 起头且紧跟 `<command-name>` → 匹配首个 `<command-name>/?([\w:-]{1,80})</command-name>` → 返回原始名（含可能的前导 `/` 与 `:subcmd`）；任何一步不满足返回 None
- [x] 3. 加辅助 `_normalize_skill_name(raw: str) -> str | None`：`lstrip("/")` → 按 `:` 切首段 → 复用现有「数字 / 首尾 `-_` / `--` / 空」过滤；过滤通过返回归一名，否则 None
- [x] 4. `scan_claude_skills` 主流程改写：按行调 `_extract_user_command_name` → 调 `_normalize_skill_name` → `name in _CLAUDE_BUILTIN_SLASH` 则 continue → 否则 `names.add(name)`；上报逻辑保持原状
- [x] 5. 删原 `_CLAUDE_SLASH_RE` 常量（被新辅助函数内联取代）

## 单元测试（`tests/test_hook.py`）

- [x] 6. **改**：原 `test_scan_claude_skills_multi_skills_deduped` 中的「`<command-name>verify</command-name>` 无前导 / 也算」断言 → 调整为「无 `type=user` 包裹的 fixture 文本不上报」
- [x] 7. **加**：`test_scan_claude_skills_only_user_message_at_start` —— `type=user` + content `lstrip()` 起头斜杠命令三件套含 `<command-name>/openspec-driven-development</command-name>` → 上报；同一名出现在 `type=assistant` 或 `tool_result` content 中 → 不上报
- [x] 8. **加**：`test_scan_claude_skills_builtin_blacklist` —— 参数化 `/clear, /compact, /context, /login, /model, /memory, /usage, /help, /agents, /doctor, /hooks, /permissions, /status, /cost, /config, /exit, /quit, /vim, /mcp, /output-style, /add-dir, /resume, /ide, /bashes, /fast` 等 → 全部不上报
- [x] 9. **加**：`test_scan_claude_skills_subcommand_normalized_to_builtin` —— `<command-name>/output-style:new</command-name>` 起头 → 不上报（归一化到 `output-style` 命中黑名单）
- [x] 10. **加**：`test_scan_claude_skills_fixture_in_middle_not_collected` —— content 起头是普通文本、中间出现 `<command-name>verify</command-name>` → 不上报
- [x] 11. **加**：`test_scan_claude_skills_list_of_blocks_content` —— `message.content` 是 `[{"type":"text","text":"<command-name>/foo-bar</command-name>..."}]` 形态 → 上报 `foo-bar`
- [x] 12. **加**：`test_scan_claude_skills_malformed_json_line_skipped` —— jsonl 含一行损坏 + 一行合法斜杠命令 → 合法那行仍上报
- [x] 13. 保留：`hit_single` / `transcript_missing_silent` / `wrong_runtime_noop` / `disabled_by_env` / `only_on_stop_and_session_end` / `main_invokes_scan_claude_skills_on_stop` / `malformed_names_filtered` 既有用例（部分 fixture 字符串需补 `type=user` 包裹）

## Spec 同步（`openspec/specs/ingest/spec.md` 经由 `spec-delta/ingest.md`）

- [x] 14. 规则 12 文本里加两个否定条件（位置守门 + 内置命令黑名单）
- [x] 15. 「可验证行为」追加：
  - 「`Stop` + transcript 内 `type=user` content 起头 `<command-name>/clear</command-name>` → 不附加 skill 字段、不上报」
  - 「`Stop` + transcript 内某 `tool_result` content 含 `<command-name>verify</command-name>` 子串、但无 `type=user` 起头记录 → 不附加 skill 字段、不上报」

## 端到端验证（AI 跑一遍）

- [x] 16. 写完单测后 `pytest tests/test_hook.py -v` 全绿
- [x] 17. 拿本机真实 transcript `~/.claude/projects/-Users-wing-Develop-tranfu-agents-app--claude-worktrees-magical-hoover-ed9dce/5451939b-*.jsonl`（自带 hook 测试 fixture + 真实 `/openspec-driven-development` 三件套）喂 `scan_claude_skills`（mock `_run_report` 收集 argv）→ 断言上报集合**含** `openspec-driven-development`，且**不含** `verify`、不含任何内置命令
- [x] 18. 再拿一份只含普通 prompt 引用、没有真实斜杠命令三件套的 transcript（如 `e379c872-*.jsonl`）跑 → 断言上报集合为空，避免把调查文本里的 `<command-name>` 引用当 skill
