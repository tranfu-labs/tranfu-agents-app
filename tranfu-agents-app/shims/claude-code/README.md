# Claude Code 接入(状态)

Claude Code 和其它 agent 一样用轻量方式接入,上报「在干哪一步 / 状态」。

## 方式一:钩子(推荐,能看到实时步骤)
把 `hooks.settings.json` 合并进 `~/.claude/settings.json`
(填好里面的 TF_SERVER / TF_KEY / TF_OPERATOR / TF_AGENT),
并确保 `~/.tranfu/tf_client.sh` 已安装(见仓库 `install.sh`)。之后照常 `claude` 即可。

## 方式二:包装器(最省事)
```bash
tf-run --runtime claude-code --agent code --task "重构支付" -- claude -p "重构支付模块"
```
