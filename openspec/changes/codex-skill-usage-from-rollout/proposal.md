# 变更提案:codex-skill-usage-from-rollout(Codex skill 使用——从会话文件补采)

- 状态:Accepted(已实现并端到端验证,2026-06-12)
- 关联:ADR-0009(钩子 stdin)、ADR-0015(skill 按会话去重)、track-skill-usage、show-skill-usage、PROTOCOL.md §5
- 后续:无新 spec delta(服务端契约零变化,见"影响")

## 背景 / 问题

track-skill-usage 打通的采集链路只在一种情况上报:`PreToolUse` 事件里 `tool_name == "Skill"`
且 `tool_input` 带 skill 名。这是 Claude Code 的形态。**Codex 不把 skill 触发暴露成 `Skill`
工具调用**(其公开 hooks 仅明确支持 Bash / apply_patch / MCP 工具),所以 Codex 会话用过的 skill
永远进不了「Skill 使用排行」。

实证:thread `019eb6e9-…` 用了 `web-product-craft`,远端 `/api/state` 能看到这台 Codex 装了它,
但 `skill_uses` 里没有该会话×skill,网页排行不显示。design.md 当时已把 Codex skill 统计标为
"尽力而为、不算本期已接通"。本变更把它接通。

## 目标

- 让 **Codex 会话用过的 skill** 进入既有的会话×skill 统计,口径与 ADR-0015 完全一致
  (一个会话算一次、永久保留、`TF_REPORT_SKILLS=0` 可关)。
- **零服务端 / 零协议改动**:复用既有 `skill` 事件字段与 `skill_uses` 落库规则。
- 只新增**一条采集链路**:Codex 在轮次 / 会话结束时,解析自己写的会话文件(rollout)。

## 非目标

- 不回填历史会话(从上线起算,需求方确认;排行本就是趋势工具)。
- 不改 Claude Code 既有链路(`PreToolUse` + `Skill` 工具调用,一行不动)。
- 不动服务端 ingest 与协议字段表。
- 不覆盖 Hermes / OpenClaw(协议字段通用,各自的源文件解析另议)。

## 方案概述(详见 design.md)

Codex 把每个会话的完整对话写成磁盘上的 rollout(`$CODEX_HOME/sessions/…/rollout-*-<sid>.jsonl`)。
agent **真用** 一个 skill 时,会用 shell `function_call` 读已装的 `.codex/skills/<名>/SKILL.md`
(或 `.claude/…`)。这条读取就是我们认的**强信号**。

链路:Codex 的 `Stop` / `SessionEnd` 钩子(已挂在 `tf_hook.py`)触发 → 用 `session_id` 定位 rollout
文件 → 只看 `payload.type == "function_call"` 的行,正则提取已装 SKILL.md 路径里的 skill 名 → 去重后
每个名字经 `tf_report.py --skill` 走**既有事件**上报 → 服务端按 `(session_id, skill)` 幂等落库。
**每轮重扫整个增长中的文件也不会重复计数**(服务端唯一键去重)。

## 影响

- `shims/tf_rollout_scan.py`(新):定位 / 解析 / 提取 / 上报。
- `shims/tf_hook.py`:Codex 且事件为 `Stop`/`SessionEnd` 时拉起扫描(受 `TF_REPORT_SKILLS=0` 短路)。
- `install.sh`:分发列表 +1(`tf_rollout_scan.py`)。
- `PROTOCOL.md` §5:隐私小节注明 Codex 下会本地读取会话文件以提取 skill 名(仍只上报名,不报内容)。
- `UPDATE.md` §6:补 Codex 排查口径。
- 新增 ADR-0016:固化"解析源文件而非 hook 内识别""只认读 SKILL.md 的强信号""不回填"。
- **specs/ingest 不变**:本变更不新增/不修改任何服务端规则,故无 spec delta。
