# tasks:hermes-skill-usage-from-skill-view

- [ ] 0. 归档 / 部署前置:在装了 Hermes 的机器上真用一次 skill,抓一条 `pre_tool_call` 原始 stdin payload,
      确认 `tool_name == "skill_view"` 且 skill 名在 `tool_input.name`。有出入则相应调整识别键。
- [x] 1. `shims/tf_hook.py`:`_skill_name()` 认可的工具名从 `{"skill"}` 放宽到 `{"skill", "skill_view"}`
      (建议抽模块级常量 `SKILL_TOOLS`)。`_name_from`/`resolve`/`scan_codex_skills`/`PRE_TOOL` 不动。
      约定不变:`ev∈PRE_TOOL` 且 `TF_REPORT_SKILLS≠0` 才工作;只取 `PreToolUse`/`pre_tool_call`,不取 post。
- [x] 2. 单测 `tests/test_hook.py`:
      正例(`skill_view(name)`、`skill_view(name,path)` → 出名);
      负例(`skills_list()` 无 name、`skill_manage(...)` 工具名不在集合、`post_tool_call` 的 skill_view);
      开关(`TF_REPORT_SKILLS=0` → 空);
      回归(Claude `tool_name=Skill` 仍出名、Codex `scan_codex_skills` 未受影响)。
- [x] 3. 文档:`PROTOCOL.md` §5 注明 Hermes 下 skill 名取自 `skill_view` 工具调用参数(只报名不报内容);
      `UPDATE.md` 补 Hermes 排查口径;`QUICKSTART.md` / `USAGE.md` / `SKILL.md` 补 Hermes shell hooks
      与 Skill 统计来源;`docs/adr/0017-hermes-skill-usage-from-skill-view.md` 成文并登记
      `docs/adr/README.md`;`docs/architecture/module-map.md` 与 `openspec/specs/onboarding/spec.md` 同步。
- [x] 4. 解析层手验:构造 Hermes `pre_tool_call` JSON 经 stdin 喂 `tf_hook.py`,断言调起的
      `tf_report.py` argv 含 `--skill <名>`;`skills_list`/`skill_manage` 不含。
- [ ] 5. 端到端手验:真机 Hermes 会话执行某 skill → 远端排行出现该 skill、
      `current_step` 形如 `tool: skill_view`、同会话只一行。
- [ ] 6. 部署:把新版 `tf_hook.py` 发布到服务端 `shims/`,队友重跑 `install.sh` 后其 Hermes 会话开始产生数据。
