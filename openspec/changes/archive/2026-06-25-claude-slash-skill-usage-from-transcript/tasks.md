# 任务：claude-slash-skill-usage-from-transcript

## 实现

- [ ] `shims/tf_hook.py`：删 `_SLASH_CMD_RE`、`_SLASH_PROMPT_HEAD`、`_skill_from_slash_prompt`
- [ ] `shims/tf_hook.py`：改 `_skill_name` 回到 archive 之前形态（只剩 `TF_REPORT_SKILLS` 短路 + `PreToolUse + Skill 工具` 单分支）
- [ ] `shims/tf_hook.py`：改 `resolve()`，删 `if ev == "UserPromptSubmit": step_idx = args.index("--step")+1 ...` 特例
- [ ] `shims/tf_hook.py`：加 `CLAUDE_SCAN_EVENTS`、`_CLAUDE_SLASH_RE`、`scan_claude_skills(d)`
- [ ] `shims/tf_hook.py`：`main()` 尾部追加 `try: scan_claude_skills(d) except: pass`（与 `scan_codex_skills` 并列）

## 测试

- [ ] `tests/test_hook.py`：删 archive change 加的 6 条 `<command-name>` payload 假定 UserPromptSubmit 用例
- [ ] `tests/test_hook.py`：新增 6 条 `scan_claude_skills` 用例（命中、多 skill 去重、`TF_REPORT_SKILLS=0`、错 runtime、文件缺失、异常名过滤）
- [ ] `tests/test_hook.py`：保留并保证既有 PreToolUse + Skill 工具用例不回归
- [ ] `pytest tests/test_hook.py -q` 全绿

## 文档

- [ ] `openspec/specs/ingest/spec.md` 规则 12：按 `spec-delta/ingest.md` 替换
- [ ] 可选：新开 `docs/adr/0018-claude-transcript-schema-dependency.md` 记录"Claude jsonl `<command-name>` schema 被我们当事实依赖"，方便未来 Claude Desktop 改格式时第一时间定位

## 端到端验证

- [ ] 用 `~/.tranfu` 本地装好新 `tf_hook.py`
- [ ] 手敲 `/openspec-driven-development xxx` 在新 Claude Desktop 会话里
- [ ] 等回合结束（触发 Stop），看 `https://tranfu-agents-app.tranfu.com/operator/Wing?view=operator` 多一条对应记录
- [ ] 同时跑一次模型 invoke Skill 工具的会话（如 `/cooper` 或自然语言唤起），确认两条路径都上报且服务端去重正确

## 归档

- [ ] 把 `spec-delta/ingest.md` 内容合并回 `openspec/specs/ingest/spec.md` 规则 12
- [ ] `mv openspec/changes/claude-slash-skill-usage-from-transcript openspec/changes/archive/2026-06-24-claude-slash-skill-usage-from-transcript`
- [ ] git commit 关联本提案
