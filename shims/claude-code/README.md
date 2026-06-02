# Claude Code 接入(自动上报)

让 Claude Code 在 会话开始 / 提交提示 / 每次工具调用 / 会话结束 时自动上报到看板,
不再依赖人工发事件。所有事件共用一个分发器 `~/.tranfu/tf_hook.py`。

## 前提
已用 `install.sh` 装好 shim(`~/.tranfu/` 下有 tf_report.py / tf_profile.py / tf_hook.py / tf_hooks.py),
且 shell rc 里已 `export TF_SERVER/TF_KEY/TF_OPERATOR/TF_RUNTIME=claude-code/TF_AGENT=...`。

## 安装钩子(用户级,对所有项目生效)
如果安装时传了 `--runtime claude-code`,安装器会自动幂等合并 hooks 到 `~/.claude/settings.json`。
手动维护时用:

```bash
python3 ~/.tranfu/tf_hooks.py --target claude status
python3 ~/.tranfu/tf_hooks.py --target claude install
python3 ~/.tranfu/tf_hooks.py --target claude uninstall
python3 ~/.tranfu/tf_hooks.py --target claude restore
```

写入前会生成 `~/.claude/settings.json.tranfu.bak.*` 备份。然后重启 Claude Code。

事件 → 上报状态:
- `SessionStart` → started(并附带自动探测的 profile,注册这个 agent)
- `UserPromptSubmit` → running(step=prompt)
- `PreToolUse` → running(step=tool: <工具名>,看板上能看到当前在调哪个工具)
- `Stop` → done(本轮结束)
- `SessionEnd` → done(会话结束)

`session_id` 取自每次事件的 stdin JSON,因此同一会话所有事件归到同一张卡。

## 验证
随便在某个项目里让 Claude Code 跑一步,然后刷新看板,应看到你这个 Pod 下对应 agent
从 started → running(tool: …) → done 的变化与活跃时长。

## 取环境变量失败时
钩子命令以 Claude Code 进程的环境运行。若你从终端 `claude` 启动(rc 已 source),
TF_* 会被继承,正常工作。若从 GUI/非终端启动导致取不到,可在 `~/.claude/settings.json`
顶层加 `"env": { "TF_SERVER": "...", "TF_KEY": "...", "TF_OPERATOR": "...", "TF_RUNTIME": "claude-code", "TF_AGENT": "..." }`,
或把钩子命令改成先 source 一个只含这些导出的环境文件。
