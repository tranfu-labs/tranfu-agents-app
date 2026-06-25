# ADR-0022:Hermes 钩子链路常态结构化诊断日志

- 状态:Proposed
- 关联:[ADR-0009](0009-claude-code-hooks-stdin.md)(钩子 stdin 契约)、[ADR-0017](0017-hermes-skill-usage-from-skill-view.md)(Hermes skill 采集)、ADR-0015(skill 按会话去重)、`openspec/changes/hermes-hook-debug-log/`、`openspec/changes/harden-codex-skill-hook-payload/`(互补 raw stdin dump)

## 背景

`shims/tf_hook.py` 既有实现下,`_run_report()` 与 `_spawn_selfupdate()` 对 subprocess 全部
`stdout/stderr=DEVNULL`,`tf-hermes-hook.sh` 也无 tee / trap,且**没有任何 `TF_DEBUG`-类按需打开开关**。

这条「静默至上」是为了贯彻 ADR-0009 的"hook 永远不阻塞宿主 agent"原则——合理。但代价是
**所有 Hermes 漏采都退化为"远端没数据,本地零证据"**:`~/.tranfu/spool.ndjson` 只在上报失败时
写;`_skill_name()` 返回空(漏采最常见根因)时本地什么都不会留下;`~/.tranfu/logs/openclaw-skill.log`
是 OpenClaw 专属。结果是 Hermes 链路出问题只能"看代码猜",排查链路过长。

并行的 `harden-codex-skill-hook-payload` change 引入了 `TF_DEBUG_HOOK=1` raw stdin dump 到
`~/.tranfu/logs/hook-payload.jsonl`——但**按需开 + 无 rotate**,解决不了"下次又漏诊断时队友机器
没开"的根本问题。

## 决策

`shims/tf_hook.py` 在 `_run_report()` 内部新增一份**常态结构化**诊断日志,固化三条:

1. **默认开,`TF_HOOK_DEBUG=0` 关**(逃逸口)。理由:诉求是常态可观察,按需开方案解决不了"事后排查"。
2. **双文件 rotate,每份 5MB,总上限 10MB**。`os.rename` 原子;无外部依赖;实现 ~10 行。
3. **不与 `harden-codex` 的 raw stdin dump 重叠**:本日志走 `~/.tranfu/logs/hermes-hook.ndjson`、
   写**结构化摘要**(8 字段)、仅 `HERMES_EVENTS` 守门;那条走 `~/.tranfu/logs/hook-payload.jsonl`、
   写**原始 stdin 全文**、`TF_DEBUG_HOOK=1` 按需开。两者代码与文件路径完全独立、互补共存。

字段固定 `{ts, ev, tool, sid, skill, argv_tail, rc, err}`(类型 / 上限见 `openspec/changes/
hermes-hook-debug-log/design.md` 字段表)。**隐私边界与 PROTOCOL.md §5 一致**:
禁写 `tool_input` 非 `name` 字段、stdin 全文、shell 命令文本;`sid` 取前 8 字符脱敏。

并发安全靠 POSIX `O_APPEND` 对 < `PIPE_BUF`(4096B)的 append 已原子,每行硬控 < 400B;
`os.rename` 在同 fs 下原子;不引入 fcntl 锁。任何 IO 失败必须静默,不影响 `tf_report.py` 调用与上报。

## 范围

- **仅 Hermes 链路**:`HERMES_EVENTS` 守门,Claude/Codex 经过 `tf_hook.py` 不落本日志。
- **仅 `_run_report()`**:`_spawn_selfupdate()` 是 detached 长进程,抓 returncode 会卡 hook 热路径,**不接入**。

## 后果

正面:

- Hermes 漏采 skill 时本地首次有可观察证据,排查链路从"远端反推"缩到"`tail ~/.tranfu/logs/hermes-hook.ndjson`"。
- `UPDATE.md` §8 给出字段-断点对照表,排查口径稳定。
- 与 `harden-codex` 的 raw dump 形成"结构化常态 + 原始按需"互补诊断栈。

负面:

- Hermes 长会话每天写几十 KB(每事件 < 200B × 数百事件),默认开;接受(远低于 5MB rotate 阈)。
- 对 `subprocess.run` 的 stderr 从 DEVNULL 改 PIPE——`tf_report.py` 现状 stderr 几乎不输出;
  即便输出也被 hook 进程吸入内存,不回流 Hermes。无实际副作用。
- Claude/Codex 漏采时本日志仍无痕迹——按 YAGNI 不预留扩展点,未来真有需要再扩 `HERMES_EVENTS` 集合。

## 替代方案与放弃理由

- **复用 `harden-codex` 的 `TF_DEBUG_HOOK=1`**:它默认关 + 无 rotate,解决不了"下次又漏诊断时
  队友没开"的根本问题;且字段是 raw stdin,不是事后排查友好的结构化摘要。
- **按日期切片 + 保留 N 天**:实现复杂度多一档(扫目录清旧文件),磁盘占用上限不如双文件 rotate 直观。
- **单文件 + 自截断**:中间段会丢,事后无法回看上一周期的事件。
- **fcntl.flock**:POSIX `O_APPEND` < PIPE_BUF 已原子,加锁是过度工程。

## 验证

- 单测覆盖 9 类:字段完整 / 空 skill 也记 / `skills_list`/`skill_manage` 也记 / 隐私守门 / 轮转 /
  Claude/Codex 守门 / `TF_HOOK_DEBUG=0` / 写失败静默 / 并发 4 进程 × 100 条原子性。
- 端到端真机手验:Hermes 触发 `skill_view` → 本地 ndjson 出对应行 ↔ 远端 `tf.db.skill_uses` 出对应行。
