# spec-delta · onboarding(安装与接入域)

针对 [openspec/specs/onboarding/spec.md](../../../../specs/onboarding/spec.md) 的增量约束。归档时合并。

## 规则(MUST)—— 新增第 10 条

10. **Hermes 钩子链路落盘常态结构化诊断日志**。`shims/tf_hook.py` 在 `_run_report()` 内部、`subprocess.run` 结束后必须为每条 **Hermes 事件**(`hook_event_name ∈ {on_session_start, pre_llm_call, pre_tool_call, post_tool_call, post_llm_call, on_session_end}`)追加一行 NDJSON 到 `~/.tranfu/logs/hermes-hook.ndjson`,字段固定为 `{ts, ev, tool, sid, skill, argv_tail, rc, err}`(类型 / 上限见 design.md「日志记录字段表」),并满足:

    - **守门**:事件不在上述集合内时不写入(Claude/Codex 同一份 hook 经过时**不落盘**);`TF_HOOK_DEBUG=0` 时不写入(逃逸口)。
    - **隐私**:禁写 `tool_input` 非 `name` 字段、stdin 全文、shell 命令文本;`sid` 取前 8 字符脱敏。隐私边界与 [PROTOCOL.md](../../../../../PROTOCOL.md) §5 一致(本地一档同样严格)。
    - **轮转**:写入前若 `~/.tranfu/logs/hermes-hook.ndjson` 大小 ≥ `5 * 1024 * 1024`(5MB),必须 `os.rename` 为 `~/.tranfu/logs/hermes-hook.ndjson.1`(覆盖既有备份),然后新建 current。**总磁盘占用上限 10MB**。
    - **不阻塞主线**:任何 IO / 文件系统失败必须静默(`try/except Exception: pass`),不得影响 `tf_report.py` 的调用与上报。
    - **并发安全**:`O_APPEND` 模式 append、`os.rename` 作为原子 rotate,不引入 fcntl 锁。每行硬控 < 400B 远低于 `PIPE_BUF` 4096B 原子阈。
    - **不日志化自更新子进程**:`_spawn_selfupdate()` 是 detached 长进程,不接入本日志(避免抓 returncode 阻塞 hook 热路径)。
    - **与 `~/.tranfu/logs/hook-payload.jsonl`(harden-codex 引入,raw stdin dump,`TF_DEBUG_HOOK=1` 按需开)互补共存**:两者写入点独立、文件路径不同、守门条件不同,各自失败不影响对方与上报主线。

## 可验证行为 —— 追加

- Hermes `pre_tool_call` + `tool_name=skill_view` + `tool_input.name="plan"` payload 经 stdin 喂 `tf_hook.py` → `~/.tranfu/logs/hermes-hook.ndjson` 末尾追加一行,`json.loads` 后 `ev=="pre_tool_call"` 且 `tool=="skill_view"` 且 `skill=="plan"` 且 `argv_tail` 末尾含 `"--skill plan"` 且 `rc==0`。
- Hermes `pre_tool_call` + `tool_name=terminal` payload → 日志追加一行 `skill==""`、`tool=="terminal"`、`argv_tail` 不含 `--skill`(证明"识别失败"在日志里看得见)。
- Hermes `pre_tool_call` + `tool_input={"name":"x","command":"rm -rf /","secret":"k"}` → 日志一行 `skill=="x"`,**不含** `"rm -rf /"` 也不含 `"k"`。
- Hermes 任意事件 + 环境 `TF_HOOK_DEBUG=0` → 日志不追加。
- Claude `PreToolUse` / Codex 任意 CamelCase 事件 → `hermes-hook.ndjson` 不追加(`HERMES_EVENTS` 守门)。
- `LOG_MAX` 缩到 200B + 连写 5 条 → `hermes-hook.ndjson.1` 文件存在 + `hermes-hook.ndjson` 大小 < 200B。
- `~/.tranfu/logs/` 父目录设为只读 → `_run_report()` 仍正常调起 `tf_report.py`,无异常向 stderr 泄漏。
- `multiprocessing` 起 4 进程各写 100 条 → 文件总行数恰好 400 且每行可独立 `json.loads`(`O_APPEND` 原子性回归)。
- 真机 Hermes 会话执行某 skill → 日志末尾出对应 `tool=="skill_view"` 行 ↔ 远端 `tf.db.skill_uses` 出对应 `(session_id, skill)` 行,**形成端到端诊断闭环**。
