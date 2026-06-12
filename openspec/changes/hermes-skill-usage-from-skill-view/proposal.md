# 变更提案:hermes-skill-usage-from-skill-view(Hermes skill 使用——从 skill_view 工具调用采集)

- 状态:Implemented locally(待真机抓一条 `pre_tool_call` 真实 payload、端到端验证与部署后归档)
- 关联:ADR-0009(钩子 stdin)、ADR-0015(skill 按会话去重)、ADR-0016(Codex 从源文件补采)、track-skill-usage、PROTOCOL.md §5
- 后续:无新 spec delta(服务端契约零变化,见「影响」)

## 背景 / 问题

skill 使用排行目前接通了两条采集链路:

- Claude Code:`PreToolUse` 里 `tool_name == "Skill"`,从 `tool_input` 取 skill 名(track-skill-usage)。
- Codex:它不暴露 skill 工具调用,改在轮末解析 rollout 源文件(ADR-0016)。

**Hermes 一条都没接上**,所以 Hermes 会话用过的 skill 进不了排行。但与 OpenClaw 不同——OpenClaw 把
skill 编译成 XML 块注入 system prompt、全程无工具边界、无法采集——**Hermes 用 skill 是一次明确的工具调用**:

> Hermes 的 skill 走渐进式披露(progressive disclosure):Level 0 `skills_list()` 只返回名字/描述;
> agent **真要用一个 skill 时,调用 `skill_view(name)` 加载正文**(Level 1);`skill_view(name, path)`
> 读 skill 内的引用文件(Level 2)。"full content loads only when needed / until one is actually used."
> —— 官方文档 hermes-agent.nousresearch.com/docs/user-guide/features/skills

而 Hermes 的 `pre_tool_call` 钩子(已经过 `tf-hermes-hook.sh` → `tf_hook.py`)在每次工具执行前触发,
stdin JSON 带 `tool_name` 与 `tool_input`:

```json
{ "hook_event_name": "pre_tool_call", "tool_name": "skill_view",
  "tool_input": {"name": "<skill 名>"}, "session_id": "...", "cwd": "...", "extra": {...} }
```

这与 Claude Code 的 `Skill` 工具调用**结构完全同构**,只是工具名是 `skill_view`、skill 名在
`tool_input.name`。因此 Hermes **不需要 Codex 那种源文件扫描**,在钩子内直接识别即可。

## 目标

- 让 **Hermes 会话用过的 skill** 进入既有的会话×skill 统计,口径与 ADR-0015 完全一致
  (一个会话算一次、永久保留、`TF_REPORT_SKILLS=0` 可关)。
- **零服务端 / 零协议改动 / 零新文件**:复用既有 `skill` 事件字段与 `skill_uses` 落库规则,
  并复用 Claude Code 那条「钩子内识别 skill 工具调用」的路径。
- 只把现有 `_skill_name()` 认的工具名从「只认 `skill`」放宽到「`skill` 或 `skill_view`」。

## 非目标

- 不引入 Codex 式的 rollout / 源文件扫描(Hermes 有现成的工具调用信号,不需要)。
- 不改 Claude Code / Codex 既有链路(一行不动)。
- 不动服务端 ingest 与协议字段表。
- 不覆盖 OpenClaw——其 skill 注入 prompt、无工具边界,现口径下无法采集,另文论证。
- 不计 `skill_manage`(skill 的增删改,是「编写」不是「使用」)与 `skills_list`(只是列目录)。

## 方案概述(详见 design.md)

链路:Hermes 触发 `pre_tool_call` 钩子(已挂 `tf_hook.py`)→ `resolve()` 照常出基础事件 →
`_skill_name()` 见 `tool_name ∈ {skill, skill_view}` 且 `tool_input` 带名字时,把 skill 名挂到
`--skill` 上 → 经**既有事件**上报 → 服务端按 `(session_id, skill)` 幂等落库。

口径上,`skill_view(name)`(Level 1)= agent 真加载了某 skill 正文 = 认定「用过」;
`skill_view(name, path)`(Level 2)读引用文件,名字相同,服务端去重不放大;
`skills_list()`(Level 0)不带 name、不计;`skill_manage`(编写 skill)不在认可工具名内、不计。

## 影响

- `shims/tf_hook.py`:`_skill_name()` 认可的工具名集合 `{skill}` → `{skill, skill_view}`
  (建议抽成常量);`_name_from` 已读 `name` 键,Hermes 的 `tool_input.name` 无需新逻辑即被取到。
  `resolve()`、Codex 的 `scan_codex_skills` 一行不动。
- `tests/test_hook.py`:新增 Hermes 口径用例(见 tasks.md)。
- `PROTOCOL.md` §5:隐私小节注明 Hermes 下 skill 名取自 `skill_view` 工具调用(仍只上报名,不报参数/内容)。
- `QUICKSTART.md` / `USAGE.md` / `SKILL.md`:补 Hermes shell hooks、`skill_view` 统计来源、关闭与卸载说明。
- `UPDATE.md`:补 Hermes 排查口径。
- 新增 ADR-0017:固化「Hermes 在钩子内识别 `skill_view` 工具调用,不走源文件扫描」「只认 `skill_view`,
  排除 `skills_list`/`skill_manage`」。
- `openspec/specs/onboarding/spec.md`:同步当前接入事实(Hermes shell hooks 由 `tf-hermes-hook.sh` + `tf_hook.py` 提供)。
- **install.sh 不变**:`tf_hook.py` 本就在分发列表,无新文件。
- **specs/ingest 不变**:本变更不新增/不修改任何服务端规则,故无 spec delta。

## 待确认(归档 / 部署前)

官方文档指明 skill 加载走 `skill_view(name)` 工具调用,但未贴 Hermes `pre_tool_call` 的**原始 stdin
payload**。归档 / 部署前需在一台装了 Hermes 的机器上真用一次 skill,确认两件事:
(1) `tool_name` 确为 `skill_view`(而非 `skill-view` 等变体);
(2) skill 名确实落在 `tool_input.name`。
若字段名有出入,调整 `SKILL_TOOLS` 或名称提取键并补测试。
