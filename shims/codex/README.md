# Codex 接入(自动上报)

让 Codex 在 会话开始 / 提交提示 / 每次工具调用前 / 结束 时自动上报到看板,
不再依赖人工发事件。所有事件共用一个分发器 `~/.tranfu/tf_hook.py`。

## 前提
已用 `install.sh` 装好 shim(`~/.tranfu/` 下有 tf_report.py / tf_profile.py / tf_hook.py / tf_hooks.py),
且 shell rc 里已 `export TF_SERVER/TF_KEY/TF_OPERATOR/TF_RUNTIME=codex/TF_AGENT=...`。

## 安装钩子(用户级,对所有项目生效)
如果安装时传了 `--runtime codex`,安装器会自动幂等合并 hooks 到 `~/.codex/hooks.json`。
手动维护时用:

```bash
python3 ~/.tranfu/tf_hooks.py --target codex status
python3 ~/.tranfu/tf_hooks.py --target codex install
python3 ~/.tranfu/tf_hooks.py --target codex uninstall
python3 ~/.tranfu/tf_hooks.py --target codex restore
```

事件 → 上报状态:
- `SessionStart` → started(并附带自动探测的 profile,注册这个 agent)
- `UserPromptSubmit` → running(step=prompt)
- `PreToolUse` → running(step=tool: <工具名>,看板上能看到当前在调哪个工具)
- `Stop` → done(本轮结束)
- `SessionEnd` → done(会话结束)

`session_id` 优先取自事件 stdin JSON,因此同一会话所有事件归到同一张卡。

## 验证
重启 Codex,随便跑一步,然后刷新看板。首次运行新增 hook 时,Codex 可能要求信任该 hook;确认一次即可。

## 取环境变量失败时
钩子命令以 Codex 进程的环境运行。若你从终端 `codex` 启动(rc 已 source),
TF_* 会被继承,正常工作。若从 GUI/非终端启动导致取不到,可继续用 `tf-run` 包装启动,
或让启动环境显式带上 `TF_SERVER/TF_KEY/TF_OPERATOR/TF_RUNTIME=codex/TF_AGENT`。
