# 规格:onboarding(安装与接入域)

事实来源:`install.sh`、`server/routes/onboarding.py`(`/install.sh` / `/shims/{path}` / `/shims/manifest` / `/llms.txt` / `/robots.txt` / `/healthz` / SPA 路由)、`server/shim.py`(`_build_shim_manifest` / `_SHIM_MANIFEST` — 内容版本与文件清单)、`shims/*`、`QUICKSTART.md` / `USAGE.md`。

## 规则(MUST)
1. 安装一律从**看板域名**:`curl -fsSL $SERVER/install.sh | bash -s -- --server $SERVER --key K --operator OP --runtime RT [--agent A --role R --about .. --tips ..]`。
   不依赖代码库是否公开(见 ADR-0007)。
2. `install.sh`:优先按 `${SERVER%/}/shims/manifest` 全量下载 shim 目标文件,校验 sha256 后写入
   `~/.tranfu/manifest.json`;将 `TF_SERVER/TF_KEY/TF_OPERATOR` 及提供的
   `TF_RUNTIME/TF_AGENT/TF_ROLE/TF_ABOUT/TF_TIPS/TF_AUTO_UPDATE` 写入 shell rc;并把 `~/.tranfu` 加入 PATH。
   若全量安装失败,不得写入假的本地 manifest 版本基线。
3. **装完即注册**:安装末尾发送一条 `started --profile` 事件,使看板立刻出现卡且详情有内容。
4. 服务端 `/shims/{path}` 仅提供 `shims/` 目录内文件,且拒绝目录穿越;`/install.sh` 提供仓库 `install.sh`;
   `/shims/manifest` 提供当前 shim 文件清单、安装目标、sha256 与内容版本。
5. 接入路径并存:`tf-run`(任意 CLI)、Claude Code / Codex 钩子(`tf_hook.py` + `tf_hooks.py`,见 ADR-0009/0010)、
   Hermes shell hooks(`tf-hermes-hook.sh` + `tf_hook.py`)、MCP reporter(桌面/黑盒)。
6. **hooks 安装必须幂等且可回退**:`--runtime claude-code` 默认维护 `~/.claude/settings.json`;
   `--runtime codex` 默认维护 `~/.codex/hooks.json`;重复安装不重复追加,卸载只移除 TRANFU hook,写入前生成
   `*.tranfu.bak.*` 备份,且不得把 `TF_KEY` 写进 hooks JSON。Hermes 使用 `~/.hermes/config.yaml` 的 shell hooks,
   安装器提供配置片段,hook wrapper 从 `~/.tranfu/tf_env.hermes.sh` 读取身份与密钥。
7. **同一 agent 始终用同一套 `operator/runtime/agent`**;漏掉 `--agent` 会退化为按 runtime 显示(产生独立卡)。
8. **自更新安全边界**:`tf_selfupdate.py` 在 hook 事件
   `SessionStart` / `on_session_start` / `UserPromptSubmit` / `Stop` / `SessionEnd`
   触发后台静默更新(实际拉取频率受 `~/.tranfu/.selfupdate.json` 的 1 小时节流约束,所有触发点共享一个窗口);
   `PreToolUse` 不触发(频率过高,无收益)。
   必须先下载到 staging,校验 sha256,`.py` 通过 `py_compile`,全部通过后才替换正式文件;失败静默且保留旧文件。
   本地 manifest 与服务端版本一致但目标文件缺失或哈希不符时,必须补齐该文件。`TF_AUTO_UPDATE=0` 完全关闭。
9. Claude Code / Codex / Hermes 的新 shim 在下一次 hook 触发时生效。
   **OpenClaw 在 `session_start` 中 fire-and-forget spawn `python3 ~/.tranfu/tf_selfupdate.py`,
   shim 文件被刷新**;JS 常驻代码本身的生效仍需重启 OpenClaw(`SIGUSR1` 只重读 manifest 的版本号显示)。
10. **Hermes 钩子链路落盘常态结构化诊断日志**。`shims/tf_hook.py` 在 `_run_report()` 内部、
    `subprocess.run` 结束后必须为每条 **Hermes 事件**(`hook_event_name ∈ {on_session_start,
    pre_llm_call, pre_tool_call, post_tool_call, post_llm_call, on_session_end}`)追加一行 NDJSON 到
    `~/.tranfu/logs/hermes-hook.ndjson`,字段固定为 `{ts, ev, tool, sid, skill, argv_tail, rc, err}`
    (类型 / 上限见 ADR-0022),并满足:
    - **守门**:事件不在上述集合内时不写入(Claude/Codex 同一份 hook 经过时不落盘);
      `TF_HOOK_DEBUG=0` 时不写入(逃逸口)。
    - **隐私**:禁写 `tool_input` 非 `name` 字段、stdin 全文、shell 命令文本;`sid` 取前 8 字符脱敏。
      隐私边界与 PROTOCOL.md §5"只名不内容"原则一致(本地一档同样严格)。
    - **轮转**:写入前若 `~/.tranfu/logs/hermes-hook.ndjson` 大小 ≥ `5 * 1024 * 1024`(5MB),
      必须 `os.rename` 为 `~/.tranfu/logs/hermes-hook.ndjson.1`(覆盖既有备份),然后新建 current。
      **总磁盘占用上限 10MB**。
    - **不阻塞主线**:任何 IO / 文件系统失败必须静默(`try/except Exception: pass`),
      不得影响 `tf_report.py` 的调用与上报。
    - **并发安全**:`O_APPEND` 模式 append、`os.rename` 作为原子 rotate,不引入 fcntl 锁。
      每行硬控 < 400B,远低于 `PIPE_BUF` 4096B 原子阈。
    - **不日志化自更新子进程**:`_spawn_selfupdate()` 是 detached 长进程,不接入本日志
      (避免抓 returncode 阻塞 hook 热路径)。
    - 与 `~/.tranfu/logs/hook-payload.jsonl`(`TF_DEBUG_HOOK=1` 按需 raw stdin dump,
      由 ingest 域 spec 规定)互补共存:两者写入点独立、文件路径不同、守门条件不同,
      各自失败不影响对方与上报主线。
11. 服务端根静态 icon 文件与看板 head 引用的同源主题初始化脚本 `/theme-init.js` 必须从构建后的
    `frontend/dist` 根目录提供,并走白名单与路径穿越保护。
    TRANFU//AGENTS head/manifest 引用到的浏览器与 PWA icon 文件包括未版本化兼容文件与版本化实体文件;
    带点静态路径不得落入 SPA fallback。

## 可验证行为
- `curl $SERVER/install.sh` 出脚本;`curl $SERVER/shims/manifest` 出当前版本清单;`curl $SERVER/shims/tf_hook.py` / `curl $SERVER/shims/tf_hooks.py` 出文件;
  `curl $SERVER/shims/../server/app.py` 返回 404。
- `curl -I $SERVER/favicon-20260626.ico` 返回 200 且为 `image/x-icon`;
  `curl -I $SERVER/favicon-32x32-20260530.png`、`/favicon-16x16-20260530.png`、
  `/apple-touch-icon-20260530.png`、`/android-chrome-192x192-20260530.png`、
  `/android-chrome-512x512-20260530.png` 返回 200 且为 `image/png`;
  未被白名单允许的带点根路径返回 404,不落入 SPA 深链 fallback。
- `GET` / `HEAD` `/theme-init.js` 返回 200,content-type 为 JavaScript。
- 跑完安装命令后,`/api/state` 出现该身份卡片且含 profile(role/IM 等)。
- `TF_AUTO_UPDATE=0` 时,`SessionStart` / `UserPromptSubmit` / `Stop` / `SessionEnd` 任一事件都不启动更新;
  服务端不可达或坏包时旧 shim 保留。
- 一小时内多次触发自更新,只有第一次会真正请求 `/shims/manifest`,其余被 `.selfupdate.json` 节流跳过。
- OpenClaw `session_start` 后,若 `~/.tranfu/manifest.json` 与服务端不一致,会在 ≤ 1h 内被刷新。
- `install.sh` 全量 manifest 安装成功后,manifest 中所有 target 都存在于 `~/.tranfu/`;安装失败时不写入 `manifest.json`。
- 本地 manifest 版本与服务端一致但某 target 缺失 → 自更新器下载并补齐该 target。
- Hermes `pre_tool_call` + `tool_name=skill_view` + `tool_input.name="plan"` payload 经 stdin 喂 `tf_hook.py`
  → `~/.tranfu/logs/hermes-hook.ndjson` 末尾追加一行,`json.loads` 后 `ev=="pre_tool_call"` 且
  `tool=="skill_view"` 且 `skill=="plan"` 且 `argv_tail` 末尾含 `"--skill plan"` 且 `rc==0`。
- Hermes `pre_tool_call` + `tool_name=terminal` payload → 日志一行 `skill==""`、`tool=="terminal"`、
  `argv_tail` 不含 `--skill`(证明"识别失败"在日志里看得见)。
- Hermes `pre_tool_call` + `tool_input={"name":"x","command":"rm -rf /","secret":"k"}`
  → 日志一行 `skill=="x"`,**不含** `"rm -rf /"` 也不含 `"k"`。
- Hermes 任意事件 + 环境 `TF_HOOK_DEBUG=0` → 日志不追加。
- Claude `PreToolUse` / Codex 任意 CamelCase 事件 → `hermes-hook.ndjson` 不追加(`HERMES_EVENTS` 守门)。
- `LOG_MAX` 缩到测试值 + 连写若干条 → `hermes-hook.ndjson.1` 文件存在 + 文件大小 ≥ 阈值 + current 文件大小 < 阈值。
- `~/.tranfu/logs/` 父目录设为只读 → `_run_report()` 仍正常调起 `tf_report.py`,无异常向 stderr 泄漏。
- 4 进程并发各写 100 条 → 文件总行数恰好 400 且每行可独立 `json.loads`(`O_APPEND` 原子性回归)。
- 真机 Hermes 会话执行某 skill → 日志末尾出对应 `tool=="skill_view"` 行 ↔ 远端 `tf.db.skill_uses` 出对应
  `(session_id, skill)` 行,**形成端到端诊断闭环**。
