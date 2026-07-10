# 任务：fix-codex-rollout-skill-scan

- [x] 1. 在 `shims/tf_rollout_scan.py` 增加统一命令区域提取：旧格式只取
      `function_call + exec_command` 的 `arguments.cmd`；新格式只取
      `custom_tool_call + exec` 中代码态、边界完整的 `tools.exec_command(...)` 调用内静态字符串 `cmd` 字段，
      忽略字符串/注释中的伪调用、非命令字段和动态变量。
- [x] 2. 保持现有 `SKILL_RE`、名称截断、文件/session 去重、`MAX_BYTES`、失败静默、
      `TF_REPORT_SKILLS=0` 和 `tf_report.py --skill` 上报链路不变；不新增回填入口或持久化游标。
- [x] 3. 扩展 `tests/test_rollout_scan.py`：保留旧真实 fixture，加入脱敏的 Codex Desktop `0.144`
      fixture，并覆盖双格式共存、多个 exec、嵌套 apply_patch 排除、非 shell function_call 排除、
      字符串/注释伪调用、非 `cmd` 字段、引号/括号/畸形输入和既有 hook 契约。
- [x] 4. 更新 `docs/adr/0016-codex-skill-usage-from-rollout.md`，同步按需修改
      `docs/architecture/module-map.md`、根 `AGENTS.md` 与相关运维说明，明确双格式守门和无批量回填边界。
- [x] 5. 运行解析层验证：旧 `codex_exec 0.135` rollout 的 `--print` 结果不变，Codex Desktop
      `0.144` rollout 能识别 `openspec-driven-development`，且验证过程不发送历史事件。
- [x] 6. 运行 `pytest tests/test_rollout_scan.py`、Python 编译检查、全量 `pytest tests/` 与覆盖率门槛；
      记录通过结果和任何已知残余风险。
