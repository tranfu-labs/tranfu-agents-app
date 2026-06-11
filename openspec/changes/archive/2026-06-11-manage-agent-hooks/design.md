# 设计:manage-agent-hooks

## 管理入口
新增 `shims/tf_hooks.py`,仅使用 Python 标准库,用于维护本地 agent 用户级 hooks 配置:

```bash
python3 ~/.tranfu/tf_hooks.py --target claude status
python3 ~/.tranfu/tf_hooks.py --target codex install
python3 ~/.tranfu/tf_hooks.py --target codex uninstall
python3 ~/.tranfu/tf_hooks.py --target claude restore
```

目标:
- Claude Code:`~/.claude/settings.json`
- Codex:`~/.codex/hooks.json`

可用 `--settings PATH` 覆盖,便于测试与故障处理。`tf_claude_hooks.py` 保留为 Claude 兼容入口。

## 合并规则
- 目标 hooks 事件:`SessionStart / UserPromptSubmit / PreToolUse / Stop / SessionEnd`。
- TRANFU hook 判定:command 同时包含 `.tranfu` 与 `tf_hook.py`。
- `install`:
  - 文件不存在则创建 `{}`。
  - 每个目标事件已有 TRANFU hook 时不重复添加。
  - 某事件缺失时只补该事件。
  - 同一事件出现多个 TRANFU hook 时保留第一个,移除重复项。
  - 保留所有非 TRANFU hooks 与其它顶层配置。
- `uninstall`:
  - 从所有 hooks 事件中移除 TRANFU hook。
  - 删除因此变空的 matcher 组与事件项。
- `restore`:
  - 默认恢复最近一次 `settings.json.tranfu.bak.*` 备份。
  - 如果安装前配置不存在,恢复时删除安装创建的 settings 文件。

## 备份
所有会写文件的操作在写入前创建备份:
- 已有配置:`settings.json.tranfu.bak.<timestamp>`。
- 原配置不存在:`settings.json.tranfu.bak.<timestamp>.missing` 标记。

## install.sh 集成
- 安装 shim 时额外下载 `tf_hooks.py` 与兼容入口 `tf_claude_hooks.py`。
- 当 `--runtime claude-code` 且未传 `--no-claude-hooks` 时,自动执行 `--target claude install`。
- 当 `--runtime codex` 且未传 `--no-codex-hooks` 时,自动执行 `--target codex install`。
- 额外支持显式参数:
  - `--install-claude-hooks`
  - `--no-claude-hooks`
  - `--claude-hooks status|install|uninstall|restore`
  - `--install-codex-hooks`
  - `--no-codex-hooks`
  - `--codex-hooks status|install|uninstall|restore`

## 风险与约束
- 若 `settings.json` 不是合法 JSON,管理脚本不得覆盖它,只提示错误。
- 若 `hooks.json` 不是合法 JSON,管理脚本不得覆盖它,只提示错误。
- 不能把 `TF_KEY` 写进 hooks JSON;身份与密钥仍从 shell rc 环境继承。
- hooks 命令继续调用 `python3 "$HOME/.tranfu/tf_hook.py"`。
- Codex 新增 hook 后可能要求用户首次信任该 hook;安装器只提示,不绕过信任。
