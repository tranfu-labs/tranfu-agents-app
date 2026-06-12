# tasks:codex-skill-usage-from-rollout

- [x] 1. `shims/tf_rollout_scan.py`:`find_rollouts` / `skills_in_file` / `scan_session` / `report_skills` / `main`。
      口径=只认 `function_call` 行读取 `.codex|.claude/skills/<名>/SKILL.md`;名称截断;`MAX_BYTES` 超时护栏;
      `--print` 供手动验证。约定:任何异常→空结果,绝不抛错。
- [x] 2. `shims/tf_hook.py`:抽 `_event_name`/`_session_id`/`_run_report`;新增 `scan_codex_skills`
      (runtime=codex 且事件∈{Stop,SessionEnd},受 `TF_REPORT_SKILLS=0` 短路)。`resolve()` 的 Claude `Skill` 逻辑保留。
- [x] 3. 单测 `tests/test_rollout_scan.py`(夹具取自真实 thread 019eb6e9 脱敏):
      正例(`.codex`/`.claude` 读取);负例(developer 技能目录 / 提示词点名 / 输出回显 / apply_patch / 非点目录);
      文件内去重;名称截断;`scan_session` 按 id 命中且忽略别的会话;`report_skills` 每名一次事件;
      hook 入口:codex Stop 触发、非 codex 不触发、开关=0 不触发、非结束事件不触发。
- [x] 4. `install.sh` 分发列表加入 `tf_rollout_scan.py`。
- [x] 5. 文档:`PROTOCOL.md` §5 隐私小节注明 Codex 本地读会话文件;`UPDATE.md` §6 补 Codex 排查口径;
      `docs/adr/0016-codex-skill-usage-from-rollout.md` 成文并登记 `docs/adr/README.md`。
- [x] 6. 解析层手验:`tf_rollout_scan.py --session <旧 thread> --print` 提取出预期 skill 名,且 developer 目录不污染。
- [x] 7. 端到端手验:新 Codex 会话真执行某 skill → 远端排行出现、`current_step=="skill: <名>"`、同会话只一行。
- [ ] 8. 部署:把 `shims/`(含新模块)发布到服务端,队友重跑 `install.sh` 后逐人开始产生数据。
