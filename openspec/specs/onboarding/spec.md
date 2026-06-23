# 规格:onboarding(安装与接入域)

事实来源:`install.sh`、`server/app.py`(`/install.sh`、`/shims/{path}`、`/shims/manifest`)、`shims/*`、`QUICKSTART.md`/`USAGE.md`。

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

## 可验证行为
- `curl $SERVER/install.sh` 出脚本;`curl $SERVER/shims/manifest` 出当前版本清单;`curl $SERVER/shims/tf_hook.py` / `curl $SERVER/shims/tf_hooks.py` 出文件;
  `curl $SERVER/shims/../server/app.py` 返回 404。
- 跑完安装命令后,`/api/state` 出现该身份卡片且含 profile(role/IM 等)。
- `TF_AUTO_UPDATE=0` 时,`SessionStart` / `UserPromptSubmit` / `Stop` / `SessionEnd` 任一事件都不启动更新;
  服务端不可达或坏包时旧 shim 保留。
- 一小时内多次触发自更新,只有第一次会真正请求 `/shims/manifest`,其余被 `.selfupdate.json` 节流跳过。
- OpenClaw `session_start` 后,若 `~/.tranfu/manifest.json` 与服务端不一致,会在 ≤ 1h 内被刷新。
- `install.sh` 全量 manifest 安装成功后,manifest 中所有 target 都存在于 `~/.tranfu/`;安装失败时不写入 `manifest.json`。
- 本地 manifest 版本与服务端一致但某 target 缺失 → 自更新器下载并补齐该 target。
