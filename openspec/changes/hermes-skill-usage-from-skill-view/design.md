# 设计:hermes-skill-usage-from-skill-view

## 信源声明

本设计以**官方文档**为准,不以本仓库既有注释为准(本仓库对 OpenClaw「跑 Codex runtime、读 SKILL.md」
的旧注释已被证伪,不可外推到 Hermes)。依据:

- 技能机制:hermes-agent.nousresearch.com/docs/user-guide/features/skills
  ——skill 渐进式披露,Level 1 用 `skill_view(name)` 加载正文。
- 钩子机制:hermes-agent.nousresearch.com/docs/user-guide/features/hooks
  ——`pre_tool_call` 每次工具执行前触发,stdin JSON 带 `tool_name` / `tool_input`。

## 已确认的决策

1. **目标**:补上 Hermes 的 skill 使用漏报,口径与 ADR-0015 一致;仅 Hermes,Claude/Codex 现有链路不动。
2. **机制**:**钩子内识别工具调用**(与 Claude Code 同路),不解析源文件。理由见下节。
3. **口径**:只认 `tool_name ∈ {skill, skill_view}` 且 `tool_input` 带非空 skill 名的 `pre_tool_call`。
   `skills_list()`(Level 0,无 name)不计;`skill_manage`(编写 skill)不计。宁缺毋错。
4. **回填**:不回填,从上线起算(与 ADR-0016 一致,排行是趋势工具)。
5. **隐私**:沿用 `TF_REPORT_SKILLS=0`,不加新开关;PROTOCOL.md 注明 Hermes 下 skill 名取自工具调用参数。

## 为什么是「钩子内识别」,不是 Codex 那种「源文件扫描」

Codex 走源文件扫描,是因为它**根本不把 skill 暴露成工具调用**,钩子里看不到信号,只能回头解析 rollout。
Hermes 不一样:它的 skill 使用本身就是一次 **`skill_view` 工具调用**,`pre_tool_call` 钩子直接就能看见。
所以走与 Claude Code 完全相同的「钩子内识别」最简且最稳:

- 无新文件、无私有格式依赖、无 `MAX_BYTES` 超时护栏、无每轮重扫读盘开销。
- 信号即时、强:`skill_view(name)` = agent 主动加载某 skill 正文,正是「用过」的定义。
- 复用既有 `resolve()` + `_skill_name()` + `tf_report.py --skill` 全链路,改动面最小。

(若未来发现 Hermes 某些 skill 触发**不**经 `skill_view`——例如 slash 命令在框架层直接注入而不过工具边界
——再单独评估是否需要补充信号源,但那是另一个变更。)

## 数据流

```
Hermes agent 调用 skill_view("<skill>")  (Level 1 加载正文 / Level 2 读引用)
→ Hermes 触发 pre_tool_call 钩子 → ~/.tranfu/tf-hermes-hook.sh(加载身份)→ tf_hook.py
→ tf_hook.resolve(d):事件 pre_tool_call → 基础事件 running, step="tool: skill_view"
→ tf_hook._skill_name(d, ev, tool):TF_REPORT_SKILLS≠0 且 ev∈PRE_TOOL 且
    tool ∈ {skill, skill_view} → _name_from(tool_input) 取 tool_input.name
→ tf_report.py --status running --step "tool: skill_view" --session <sid> --skill <名>
→ 既有 ingest:事件带 skill+session_id → INSERT OR IGNORE skill_uses(session_id, skill)
→ (show-skill-usage)读时 GROUP BY 出排行
```

注:Hermes 的 `pre_tool_call` 已在 `tf-hermes-hook.sh` 的注册清单里(`~/.hermes/config.yaml`
`hooks:` 下),信号本就流经 `tf_hook.py`——本变更**不需要改钩子接线**,只需让 `_skill_name()` 多认一个
工具名。

## 改动文件与职责

- `shims/tf_hook.py`——
  - `_skill_name(d, ev, tool)`:把判定 `str(tool).casefold() != "skill"` 改为「不在认可集合内则跳过」,
    集合 = `{"skill", "skill_view"}`(建议抽成模块级常量 `SKILL_TOOLS`,便于将来增减)。其余不变:
    仍只在 `ev ∈ PRE_TOOL`、`TF_REPORT_SKILLS≠0` 时工作,仍用 `_name_from` 从 `tool_input`/`toolInput`/
    `input`/`arguments` 取名(`_name_from` 已认 `skill`/`name`/`skill_name` 键,Hermes 的 `name` 直接命中)。
  - `resolve()`、`scan_codex_skills()`、`MAP`、`PRE_TOOL` 均不动(`PRE_TOOL` 已含 `pre_tool_call`)。
- `tests/test_hook.py`——新增 Hermes 口径用例(见下「口径细节」与 tasks.md)。
- `PROTOCOL.md` §5 / `UPDATE.md` / `docs/adr/0017-*`——见 proposal「影响」。
- `install.sh`、`server/`、`openspec/specs/`——**不动**。

## 口径细节:什么算「Hermes 用过一个 skill」

| `pre_tool_call` 记录 | 是否计入 | 原因 |
|---|---|---|
| `tool_name=skill_view`, `tool_input={name:"plan"}` | ✅ | Level 1 加载 skill 正文,强信号:真用了 |
| `tool_name=skill_view`, `tool_input={name:"plan", path:"ref.md"}` | ✅ | Level 2 读引用,名字同上,服务端去重不放大 |
| `tool_name=skills_list`, `tool_input={}` | ❌ | Level 0 只列目录,无 name → 自然被过滤 |
| `tool_name=skill_manage`, `tool_input={action:"create", name:"x"}` | ❌ | 编写 skill,不是使用;不在认可工具名集合内 |
| `tool_name=terminal`, `tool_input={command:"cat ~/.hermes/skills/x/SKILL.md"}` | ❌ | 普通 shell,非 `skill_view` 工具;不计(与 Codex 口径相反,因 Hermes 有专门工具,不靠 shell 推断) |
| `post_tool_call`(任何 skill_view) | ❌ | 只在 `PreToolUse`/`pre_tool_call` 取,避免一次调用计两遍 |

## 已知边界(默认决策,可推翻)

- **agent 出于好奇/检查 `skill_view` 了某 skill 却没真正按它执行**——会被计入。接受:与 ADR-0016 的
  「调试读 SKILL.md」同性质,罕见,且内容确实进了上下文。
- **slash 命令(如 `/plan`)**:官方称「每个 skill 自动暴露为 slash 命令」。需真机确认它最终是否落成一次
  `skill_view` 工具调用。若是→自动被本方案覆盖;若框架层直接注入不过工具边界→该来源漏采,作为已知边界,
  另议是否补。
- **Hermes 工具名变体**:归档 / 部署前需真机确认是 `skill_view`(下划线)。若官方某版本用连字符等变体,只需在
  `SKILL_TOOLS` 常量里加一项。
- **子代理独立 session_id**:Hermes 有 `subagent_stop` 钩子,子代理的 skill 在其自身会话内单独计数;
  与 ADR-0015 一致,未来读侧按 parent 归并。
- **依赖钩子接线已装**:仅当用户 `~/.hermes/config.yaml` 已注册 `pre_tool_call → tf-hermes-hook.sh`
  时数据才产生。未注册 = 该 runtime 无数据,不报错。

## 分发线:上线后数据何时开始产生

与 track-skill-usage / ADR-0016 同一条线:`install.sh` 从 `$SERVER/shims` 拉文件。需先把新版
`tf_hook.py` 部署到**服务端** `shims/`,队友重跑 `install.sh` 后其 Hermes 会话才开始产生数据。
兼容性:旧 hook(只认 `skill`)+ 新服务端 = 与现状一致(Hermes 仍漏采,不报错);新 hook + 旧服务端 =
多发带 `skill` 字段的普通事件,旧服务端按既有规则处理(有表则落库)。

## 验证计划(实现后据此填结果)

1. **单元层**(`tests/test_hook.py`):`skill_view(name)` → 出名;`skill_view(name,path)` → 出名;
   `skills_list()` → 空;`skill_manage(...)` → 空;`post_tool_call` 的 skill_view → 空;
   `TF_REPORT_SKILLS=0` → 空;并回归 Claude `Skill` / Codex 既有用例不破。
2. **解析手验**:构造一条 Hermes `pre_tool_call` JSON 喂给 `tf_hook.py`(stdin),
   断言其调起的 `tf_report.py` argv 含 `--skill <名>`。
3. **端到端手验**:真机 Hermes 会话执行某 skill → 远端 `/api/state` 排行出现该 skill、
   该会话 `current_step` 形如 `tool: skill_view`、同会话同 skill 只一行。
