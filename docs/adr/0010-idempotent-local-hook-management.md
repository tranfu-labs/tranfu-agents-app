# ADR-0010 本地 hooks 配置必须幂等且可回退

- 状态:Accepted

## 背景
Claude Code 与 Codex 都能通过用户级 hooks 配置触发命令式上报:
- Claude Code:`~/.claude/settings.json`
- Codex:`~/.codex/hooks.json`

早期只提供模板或文档脚本,用户需要手动合并 JSON。这样容易覆盖已有 hooks、重复追加 TRANFU hook,
也缺少卸载和恢复路径。

## 决策
提供 `shims/tf_hooks.py` 管理本地 agent hooks:
- `--target claude` 维护 `~/.claude/settings.json`
- `--target codex` 维护 `~/.codex/hooks.json`
- 支持 `status / install / uninstall / restore`
- 写入前生成 `*.tranfu.bak.*` 备份
- 安装时保留所有非 TRANFU hooks,重复运行不重复追加
- 卸载时只移除 command 指向 `~/.tranfu/tf_hook.py` 的 TRANFU hooks

`install.sh` 在 `--runtime claude-code` 或 `--runtime codex` 时默认执行对应目标的 `install`。

## 后果
- ✅ Claude Code / Codex 都能装完自动接线。
- ✅ 重复安装、修复缺项、卸载、恢复都有明确入口。
- ✅ 不把 `TF_KEY` 写入 hooks JSON;身份和密钥仍从 shell rc 环境继承。
- ⚠️ Codex 新增 hook 后可能要求用户首次信任该 hook,安装器只提示,不绕过信任机制。
