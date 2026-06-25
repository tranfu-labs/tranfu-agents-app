# 设计：claude-slash-skill-usage-from-transcript

## 方案

### `scan_claude_skills(d)` 新增 —— 与 `scan_codex_skills` 同构

放在 [shims/tf_hook.py](../../../shims/tf_hook.py)，签名/约束抄 [`scan_codex_skills`](../../../shims/tf_hook.py)：

```python
CLAUDE_SCAN_EVENTS = ("Stop", "SessionEnd")
_CLAUDE_SLASH_RE = re.compile(r"<command-name>/?([\w-]{2,80})</command-name>")


def scan_claude_skills(d):
    """Stop/SessionEnd 时扫 transcript jsonl 抓 <command-name> 标记。
    Codex 是 rollout transcript，Claude 是 ~/.claude/projects/*.jsonl —— 来源不同，
    handling 一致：best-effort，任何失败静默退出，永远不阻塞主线程。"""
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return
    if os.environ.get("TF_RUNTIME") != "claude-code":
        return
    if _event_name(d) not in CLAUDE_SCAN_EVENTS:
        return
    transcript = d.get("transcript_path") if isinstance(d, dict) else None
    if not transcript or not os.path.exists(transcript):
        return
    sid = _session_id(d)
    if not sid:
        return
    names = set()
    try:
        with open(transcript, errors="replace") as f:
            for line in f:
                for m in _CLAUDE_SLASH_RE.finditer(line):
                    nm = m.group(1)
                    if nm.isdigit():
                        continue
                    if nm.startswith(("-", "_")) or nm.endswith(("-", "_")):
                        continue
                    if "--" in nm:
                        continue
                    names.add(nm)
    except Exception:
        return
    for nm in names:
        _run_report(["--status", "done", "--step", f"skill: {nm}",
                     "--session", str(sid), "--skill", nm])
```

### `main()` 末尾追加调用 —— 与 `scan_codex_skills` 并列

```python
try:
    scan_claude_skills(d)
except Exception:
    pass  # telemetry must never break the session
```

### 死代码清理（archive 方向那一坨）

删除：
- `_SLASH_CMD_RE`、`_SLASH_PROMPT_HEAD`、`_skill_from_slash_prompt(prompt)`
- `_skill_name` 里 `if ev == "UserPromptSubmit": return _skill_from_slash_prompt(...)` 这一分支
- `resolve()` 里 `if ev == "UserPromptSubmit": step_idx = args.index("--step")+1; args[step_idx] = f"skill: {skill}"` 这一段

`_skill_name` 简化回到 archive 之前的形态：

```python
def _skill_name(d, ev, tool):
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return ""
    if ev in PRE_TOOL and str(tool).casefold() in SKILL_TOOLS:
        return _skill_from_tool_input(d)
    return ""
```

### 测试

[tests/test_hook.py](../../../tests/test_hook.py)：

- **删**：archive change 加的 6 条 `<command-name>` payload 假定 UserPromptSubmit 用例（前提已被推翻）
- **新增**（围绕 `scan_claude_skills`）：
  1. 命中：fixture jsonl 含 1 行 `<command-name>/openspec-driven-development</command-name>` → `_run_report` 被调一次，argv 含 `--skill openspec-driven-development`、`--status done`、`--step skill: openspec-driven-development`
  2. 多 skill 命中 + 去重：jsonl 含两个不同 `<command-name>` 各 N 次 → `_run_report` 各调一次
  3. `TF_REPORT_SKILLS=0` 时不上报
  4. `TF_RUNTIME != claude-code`（如 codex / 缺省）不触发
  5. `transcript_path` 文件缺失 / 路径为空 / key 不存在 → 不报错、不上报
  6. 异常 skill 名（纯数字 `<command-name>/12345</command-name>`、`--` 连字、首尾 `_-`）被过滤
- **保留并确保不回归**：既有 PreToolUse + Skill 工具用例（这条线还是热的）

实现机制：fixture 通过 `tmp_path` 写一个 jsonl，构造 hook payload `{"hook_event_name": "Stop", "transcript_path": str(tmp), "session_id": "..."}`，用 `monkeypatch` 把 `_run_report` 换成捕获器，断言 argv 列表。

## 权衡

### 为什么不走 "改 UserPromptSubmit regex 抓裸 `/<name>`"

- **误识高**：用户聊天里以 `/api/foo`、`/etc/passwd`、`/根目录` 起头不少见
- **跨 runtime 不一致**：Codex 走 transcript scan，Claude 走 prompt regex，维护成本翻倍
- **失去扩展空间**：未来真要分 `used` / `equipped` 或拿 args，transcript 路径在 jsonl 里直接拿就行；regex 路径只有裸字符串

### 为什么不从 UserPromptSubmit hook 里读 `transcript_path`

时序竞态。debug 捕获时 jsonl 比 hook 早 151ms，但 Claude Desktop 没承诺这个顺序；不同 entrypoint（CLI vs Desktop vs IDE）的展开顺序可能不同。`Stop` / `SessionEnd` 触发时落盘已经稳了。

### 每 turn 重扫开销

单次 Stop 扫整份 jsonl：1-10MB 量级、几 ms ~ 几十 ms；`tf_report.py` 是子进程不阻塞主线程；`subprocess.run(timeout=8)` 兜底。先不做增量；如果实测看板上 Stop 延迟超 100ms 再加 `last_seen_offset` 状态文件。

### 为什么不顺手扫 jsonl 里的 Skill 工具调用

也能做（jsonl assistant message 的 `tool_use` 有 `Skill` name + input.name）。但现有 PreToolUse + Skill 路径已经实时上报，Stop 时再扫一遍是多余工作，且实时延迟更小。除非未来发现 PreToolUse 漏触发，再加。

### 重扫产生的重复上报

每个 Stop 都会重扫整份 jsonl（无 last-seen-offset），同一个 skill 在长会话里会被多次报。**这是预期行为**，依赖服务端 ADR-0015 的 `(session_id, skill, mode)` 唯一约束兜底，第 2 次起就是无害的 INSERT-OR-IGNORE。客户端不加状态文件，能省一个出错面。

## 风险

| 风险 | 缓解 |
|---|---|
| Claude Desktop 未来改 jsonl 格式，去掉 `<command-name>` markup | 这次改完写 [ADR-0017](../../../docs/adr/) 兄弟 ADR 记录 "Claude transcript schema 依赖"；若 Claude 升版后看板斜杠数突然清零，第一时间查这个 |
| 大 jsonl 扫描慢 | 每 Stop 几十 ms 量级；`subprocess.run(timeout=8)` 保底；超慢退到只在 SessionEnd 扫 |
| Stop hook 在 Claude Desktop 上不保证每 turn 都触发（用户中途强关）| `SessionEnd` 兜底；最坏漏一次末尾 turn，但前面 turn 的 Stop 已经把对应 skill 抓到了 |
| `transcript_path` 是 CLI / Desktop 共有字段假设可能错 | 默认拿不到就静默退出（已有 `if not transcript: return`）；不阻塞主线程；测试 case 5 覆盖 |
| 用户在 prompt 正文里"复述" `<command-name>` 字面量被误识别 | 真实场景极低；保留与 archive 时同样的名字校验（非数字、首尾非 `-_`、无 `--`）；如有误识可加白名单 |

## 回滚

代码变更局限于：
- [shims/tf_hook.py](../../../shims/tf_hook.py)
- [tests/test_hook.py](../../../tests/test_hook.py)
- [openspec/specs/ingest/spec.md](../../../openspec/specs/ingest/spec.md) 规则 12

回滚 = `git revert <merge>` + 触发一次 selfupdate 覆盖本地 `~/.tranfu/tf_hook.py`。无数据迁移、无服务端动作、无 `skill_uses` 表脏数据（INSERT 走原有去重路径）。
