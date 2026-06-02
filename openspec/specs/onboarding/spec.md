# 规格:onboarding(安装与接入域)

事实来源:`install.sh`、`server/app.py`(`/install.sh`、`/shims/{path}`)、`shims/*`、`QUICKSTART.md`/`USAGE.md`。

## 规则(MUST)
1. 安装一律从**看板域名**:`curl -fsSL $SERVER/install.sh | bash -s -- --server $SERVER --key K --operator OP --runtime RT [--agent A --role R --about .. --tips ..]`。
   不依赖代码库是否公开(见 ADR-0007)。
2. `install.sh`:把 shim 拉到 `~/.tranfu`(下载源 `${SERVER%/}/shims`);将 `TF_SERVER/TF_KEY/TF_OPERATOR` 及提供的
   `TF_RUNTIME/TF_AGENT/TF_ROLE/TF_ABOUT/TF_TIPS` 写入 shell rc;并把 `~/.tranfu` 加入 PATH。
3. **装完即注册**:安装末尾发送一条 `started --profile` 事件,使看板立刻出现卡且详情有内容。
4. 服务端 `/shims/{path}` 仅提供 `shims/` 目录内文件,且拒绝目录穿越;`/install.sh` 提供仓库 `install.sh`。
5. 三条接入路径并存:`tf-run`(任意 CLI)、Claude Code / Codex 钩子(`tf_hook.py` + `tf_hooks.py`,见 ADR-0009/0010)、MCP reporter(桌面/黑盒)。
6. **hooks 安装必须幂等且可回退**:`--runtime claude-code` 默认维护 `~/.claude/settings.json`;
   `--runtime codex` 默认维护 `~/.codex/hooks.json`;重复安装不重复追加,卸载只移除 TRANFU hook,写入前生成
   `*.tranfu.bak.*` 备份,且不得把 `TF_KEY` 写进 hooks JSON。
7. **同一 agent 始终用同一套 `operator/runtime/agent`**;漏掉 `--agent` 会退化为按 runtime 显示(产生独立卡)。

## 可验证行为
- `curl $SERVER/install.sh` 出脚本;`curl $SERVER/shims/tf_hook.py` / `curl $SERVER/shims/tf_hooks.py` 出文件;
  `curl $SERVER/shims/../server/app.py` 返回 404。
- 跑完安装命令后,`/api/state` 出现该身份卡片且含 profile(role/IM 等)。
