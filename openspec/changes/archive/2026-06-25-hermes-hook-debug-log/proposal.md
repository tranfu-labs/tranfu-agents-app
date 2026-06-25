# 提案:hermes-hook-debug-log(Hermes 钩子链路常态结构化诊断日志)

- 状态:Draft(2026-06-25)
- 关联:[hermes-skill-usage-from-skill-view](../hermes-skill-usage-from-skill-view/proposal.md)(本变更是它端到端验证的下游诊断手段)、
  [harden-codex-skill-hook-payload](../harden-codex-skill-hook-payload/proposal.md)(它在引入 `TF_DEBUG_HOOK=1` raw stdin dump,与本变更**互补不冲突**——见「与 harden-codex 的关系」)、
  ADR-0015(skill 按会话去重)、PROTOCOL.md §5(隐私边界:只报名不报内容)
- 后续:无新 ADR(本变更只动 `onboarding` 域,见 spec-delta;不动 `ingest`,避免与 harden-codex 重叠)

## 背景 / 问题

Hermes 漏采 skill 时本地**几乎无任何痕迹可查**:

- [shims/tf_hook.py](../../../shims/tf_hook.py) 的 `_run_report()`(行 137-141)与 `_spawn_selfupdate()`(行 144-160)对 `subprocess` 全部 `stdout=DEVNULL, stderr=DEVNULL`——hook 跑了没、是否识别出 skill 名、上报到服务端是否成功,**事后毫无线索**。
- [shims/wrapper/tf-hermes-hook.sh](../../../shims/wrapper/tf-hermes-hook.sh) `exec python3`,**无 tee、无 trap**。
- `grep TF_DEBUG / TF_HOOK_DEBUG` 全空——**没有"按需打开调试模式"的口子**。
- `~/.tranfu/spool.ndjson` 只在**上报失败时**写,作为离线重发队列(`tf_report.py:28`);hook 跑了但 `_skill_name()` 返回空(漏采的最常见根因)→ 这里**什么都不会留下**。
- `~/.tranfu/logs/openclaw-skill.log` 是 OpenClaw runtime 专属(`shims/openclaw/logger.mjs:20`),与 Hermes 无关。

这条「静默至上」是设计上为了「telemetry must never break the session」(`tf_hook.py:141` 注释)——合理,但代价是**所有 Hermes 漏采问题都退化为"远端没数据,本地零证据,只能靠看代码猜"**。`hermes-skill-usage-from-skill-view` 部署后,排查口径将完全依赖远端 `tf.db` 反推,排查链路过长且无法本地自证。

## 目标

- 给 **Hermes 钩子链路**加一份**常态可观察**的结构化日志,事后可查"hook 跑了没 → 识别出 skill 名了没 → 上报是否成功"全链路状态。
- **硬性限制磁盘占用**:双文件 rotate、每份 5MB,总上限 10MB。无外部依赖(标准库 `os.rename`)。
- **零服务端 / 零协议 / 零数据库改动**:纯本地诊断日志。
- 与 Claude/Codex 链路**完全解耦**:同一份 `tf_hook.py` 经过 Claude/Codex 事件时**不落盘**(用 `HERMES_EVENTS` 常量守门)。
- 与 [harden-codex-skill-hook-payload](../harden-codex-skill-hook-payload/proposal.md) 互补共存,**不冲突、不重复**。

## 非目标

- 不动 Claude/Codex hook 链路(它们目前 OK,扩大范围会模糊任务边界)。
- 不动 [shims/wrapper/tf-hermes-hook.sh](../../../shims/wrapper/tf-hermes-hook.sh)(所有日志逻辑在 python 一侧,wrapper 保持纯透传)。
- 不动协议字段、`skill_uses` 表结构、服务端 ingest 代码。
- **不重复** harden-codex 的 raw stdin dump 能力(它做"按需开 + 全 runtime 原始 payload",本变更做"常态开 + Hermes-only 结构化摘要",两条路独立)。
- 不日志化 `_spawn_selfupdate()`——它是 detached 长进程,抓 returncode 要等子进程结束 → 会卡 hook 热路径。
- 不引入 fcntl.flock——`O_APPEND` 在 POSIX 下对 < PIPE_BUF 写入已原子,加锁是过度工程。

## 方案概述(详见 design.md)

`tf_hook.py` 入口增加 `_hook_log()`:

1. **守门**:仅当 `ev ∈ HERMES_EVENTS`(snake_case 那批,与 `MAP` 里 Hermes 分组对齐)时落盘。Claude/Codex 事件不落。
2. **触发模式**:**默认开**;`TF_HOOK_DEBUG=0` 可关闭(逃逸口)。
3. **字段**:一条 NDJSON,`{ts, ev, tool, sid, skill, argv_tail, rc, err}`。**不写** `tool_input` 完整体、stdin 全文、shell 命令文本——与 PROTOCOL.md §5 一致(本地一档同样严格)。
4. **轮转**:写之前看 `LOG_PATH` 大小;超 5MB → `os.rename(LOG_PATH, LOG_PATH + ".1")`(原子,覆盖旧 `.1`),再新建 current。**总上限 10MB**。
5. **接入点**:`_run_report()` 改 `subprocess.run` 的 `stderr=DEVNULL → stderr=PIPE`,执行完拿到 rc + stderr,塞给 `_hook_log()`;`stdout` 仍 DEVNULL;`timeout=8` 不变。

## 与 harden-codex-skill-hook-payload 的关系

两条 change 都为「hook 诊断」做事,但**形态完全不同**,代码与 spec-delta 都不冲突:

| 维度 | 本变更(hermes-hook-debug-log) | harden-codex 的诊断部分 |
|---|---|---|
| 范围 | Hermes-only(`HERMES_EVENTS` 守门) | All-runtime(`tf_hook.py.main()` 入口) |
| 触发 | 默认开,`TF_HOOK_DEBUG=0` 关 | 默认关,`TF_DEBUG_HOOK=1` 开 |
| 字段 | 结构化摘要(8 字段) | Raw stdin 全文 + Codex 6 早退点 |
| 路径 | `~/.tranfu/logs/hermes-hook.ndjson`(+`.1`) | `~/.tranfu/logs/hook-payload.jsonl` + `codex-skill.log` |
| Rotate | 双文件 5MB,总 10MB | 无 |
| 服务目标 | 事后排查("下次又漏诊断") | 快速抓证据("30 秒拿到 payload 形态") |
| spec-delta 域 | `onboarding`(规则 10) | `ingest`(规则 13 + 诊断 SHOULD) |

**spec-delta 协调**:两份 spec-delta 操作不同业务域,文件路径与字段都不冲突。归档先后任意,后归档者按 openspec/changes/AGENTS.md 的合并约定接住基线即可。代码层面两个 `_*_log` 函数并存于同一份 `tf_hook.py`,各自守门、各自落盘、不互相干扰。

## 影响

- [shims/tf_hook.py](../../../shims/tf_hook.py)——
  - 新增模块级常量 `HERMES_EVENTS`、`LOG_PATH`、`LOG_MAX = 5*1024*1024`、`LOG_KEEP = 1`。
  - 新增 `_hook_log(ev, tool, sid, skill, argv, rc, err)`:落盘 + rotate。
  - `_run_report()` 改 `stderr=PIPE`,执行后调 `_hook_log()`。
  - `resolve()` / `_skill_name()` / `MAP` / `SKILL_TOOLS` / `PRE_TOOL` / `_spawn_selfupdate()` **不动**。
- [shims/wrapper/tf-hermes-hook.sh](../../../shims/wrapper/tf-hermes-hook.sh)——**不动**。
- [tests/test_hook.py](../../../tests/test_hook.py)——新增本变更测试用例(见 tasks.md)。
- [PROTOCOL.md](../../../PROTOCOL.md) §5——补一句:本地诊断日志写在 `~/.tranfu/logs/hermes-hook.ndjson`,只记字段名 / 工具名 / skill 名,不记参数内容。
- [UPDATE.md](../../../UPDATE.md)——补一条排查口径:Hermes 漏采时先看这个文件;字段口径速查表。
- 新增 [docs/adr/0022-hermes-hook-debug-log.md](../../../docs/adr/0022-hermes-hook-debug-log.md)——固化三条决策:默认开、双文件 rotate、不与 harden-codex 重复造 raw stdin dump。
- [openspec/specs/onboarding/spec.md](../../../openspec/specs/onboarding/spec.md)——新增规则 10(见 spec-delta)。
- [install.sh](../../../install.sh)——**不动**(`tf_hook.py` 本就在 manifest)。
- [server/](../../../server/) / [openspec/specs/ingest/spec.md](../../../openspec/specs/ingest/spec.md)——**不动**。

## 待确认(归档前)

- 与 [harden-codex-skill-hook-payload](../harden-codex-skill-hook-payload/proposal.md) 的归档先后无要求,但归档时复核 `onboarding` 与 `ingest` 两份 spec-delta 互不踩。
- 真机端到端手验通过(Hermes 触发 skill_view → 本地 ndjson 出对应行 → 远端 `skill_uses` 表出对应行)。
