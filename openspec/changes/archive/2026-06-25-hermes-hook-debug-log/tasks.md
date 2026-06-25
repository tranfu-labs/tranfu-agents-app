# 任务:hermes-hook-debug-log

- [ ] 1. [shims/tf_hook.py](../../../shims/tf_hook.py):新增模块级常量 `HERMES_EVENTS`、`LOG_DIR`、`LOG_PATH`、`LOG_BAK`、`LOG_MAX = 5*1024*1024`;
      新增 `_ensure_log_dir()`(`os.makedirs(LOG_DIR, exist_ok=True)`)、
      `_rotate_if_needed()`(`os.stat(LOG_PATH).st_size >= LOG_MAX → os.rename(LOG_PATH, LOG_BAK)`,文件不存在静默跳过)、
      `_utcnow_iso()`(无依赖,`datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`)、
      `_hook_log(ev, tool, sid, skill, argv, rc, err)`(守门 + 落盘 + 全段 try/except);
      `_run_report(argv)` 接入:`stderr=DEVNULL → stderr=subprocess.PIPE`,执行后取 `proc.returncode` 与 `proc.stderr`,超时分支 rc=-1 err="timeout",最后调 `_hook_log()`。
      `resolve()` / `_skill_name()` / `MAP` / `SKILL_TOOLS` / `PRE_TOOL` / `_spawn_selfupdate()` 不动。
- [ ] 2. [tests/test_hook.py](../../../tests/test_hook.py):新增 8 类用例。所有测试用 `tmp_path` monkeypatch `LOG_PATH`、`LOG_BAK`、`LOG_MAX`:
      - **(a) 字段完整**:`pre_tool_call` + `skill_view(name="plan")` payload → 落一行,断言 `ev=="pre_tool_call"` / `tool=="skill_view"` / `skill=="plan"` / `argv_tail` 末尾含 `"--skill plan"` / `rc==0`。
      - **(b) 空 skill 也记**:`pre_tool_call` + `tool_name="terminal"` → 落一行,断言 `skill==""` / `tool=="terminal"` / `argv_tail` 不含 `--skill`(证明"识别失败"在日志里看得见)。
      - **(c) skills_list / skill_manage 也记**:这两个事件 → 落一行 `skill==""`(可区分"hook 跑了 + 被过滤"vs"hook 没跑")。
      - **(d) 隐私守门**:`tool_input={"name":"x","command":"rm -rf /","secret":"k"}` → 落地日志**不含** `"rm -rf /"` 也不含 `"k"`,只含 `skill=="x"`。
      - **(e) 轮转**:monkeypatch `LOG_MAX=200`,连写 5 条 → 断言 `LOG_BAK` 文件存在 + `LOG_PATH` 文件存在 + 当前 `LOG_PATH` 大小 < 200B。
      - **(f) Claude/Codex 守门**:喂 `PreToolUse`(CamelCase) → 断言 `LOG_PATH` 不存在或未追加(`HERMES_EVENTS` 守门)。
      - **(g) TF_HOOK_DEBUG=0 关闭**:`monkeypatch.setenv("TF_HOOK_DEBUG", "0")` → 任何 Hermes 事件都不落盘。
      - **(h) 写失败静默**:`LOG_DIR` 父目录设只读 / monkeypatch `os.makedirs` 抛异常 → `_run_report()` 正常返回,`tf_report.py` 仍被调用。
      - **(i) 回归**:Claude `tool_name=Skill` / Codex `scan_codex_skills` 既有用例不破(直接复用既有断言)。
      - **(j) 并发**:`multiprocessing` 起 4 进程各写 100 条,断言 `LOG_PATH` 总行数恰好 400 且每行 `json.loads` 不抛(`O_APPEND` 原子性回归)。
- [ ] 3. 文档:
      - [PROTOCOL.md](../../../PROTOCOL.md) §5:补一句本地诊断日志路径与隐私边界(只名不内容);
      - [UPDATE.md](../../../UPDATE.md):补"Hermes 漏采时先看 `~/.tranfu/logs/hermes-hook.ndjson`"排查口径 + 字段速查表;
      - [docs/adr/0022-hermes-hook-debug-log.md](../../../docs/adr/0022-hermes-hook-debug-log.md) 成文并登记 [docs/adr/README.md](../../../docs/adr/README.md),固化三条决策(默认开 / 双文件 rotate / 不与 harden-codex 重复造 raw stdin dump);
      - [docs/architecture/module-map.md](../../../docs/architecture/module-map.md) 同步 `tf_hook.py` 多出的诊断职责;
      - [openspec/specs/onboarding/spec.md](../../../openspec/specs/onboarding/spec.md) 同步规则 10(见 spec-delta)。
- [ ] 4. 解析层手验:构造各类 Hermes payload JSON 经 stdin 喂 `tf_hook.py`,断言:
      - `pre_tool_call` + `skill_view` → 出 `skill` 字段;
      - `skills_list` / `skill_manage` → 出空 `skill`、有 `tool`、有 `argv_tail`;
      - `PreToolUse`(Claude)→ 不出现在 `hermes-hook.ndjson`(只能出现在 stdout 上报);
      - `LOG_MAX` 改 200 后连写 → `.1` 文件出现。
- [ ] 5. 端到端手验:真机 Hermes 会话:
      - 触发 `skill_view` → 本地 `hermes-hook.ndjson` 末尾出对应行(`ev=="pre_tool_call"` / `tool=="skill_view"` / `skill=="<名>"` / `rc==0`);
      - 远端 `/api/state` 排行同步出现该 skill;
      - 同会话 `current_step` 形如 `"tool: skill_view"`;
      - 用 `dd` 把日志撑过 5MB → 下一次 hook 触发后 `.1` 文件出现且 current < 5MB;
      - `TF_HOOK_DEBUG=0` env 起 Hermes → 不落盘。
- [ ] 6. 部署:把新版 `tf_hook.py` 发布到服务端 `shims/`,队友重跑 `install.sh` 后其 Hermes 会话开始产生本地诊断日志。
- [ ] 7. 归档前置:与 [harden-codex-skill-hook-payload](../harden-codex-skill-hook-payload/proposal.md) 复核——
      `onboarding` 与 `ingest` 两份 spec-delta 路径互不踩;两份 ADR(0017 / 0022)互相引用;
      代码层面 `_hook_log_payload_dump`(他)与 `_hook_log`(本)函数名、文件路径、守门条件互不冲突。
