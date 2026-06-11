# 变更提案:manage-agent-hooks(本地 agent hooks 生命周期管理)

- 状态:Implemented(已实现;tasks 13/13 完成,spec delta 已合入 specs/onboarding 规则 5/6)
- 关联:specs/onboarding、ADR-0009、install.sh、shims/tf_hook.py、QUICKSTART.md

## 背景 / 问题
Claude Code 自动上报依赖 `~/.claude/settings.json` 中的 hooks 配置;Codex 自动上报依赖
`~/.codex/hooks.json` 中的 hooks 配置。当前仓库已有 `tf_hook.py` 与 Claude hooks 模板,
但安装流程不会自动合并配置;用户需要手动复制 QUICKSTART 中的脚本,Codex 也只能靠 `tf-run`。

手动脚本还能工作,但缺少三个产品化能力:
- 幂等:重复安装不应重复追加 TRANFU hook。
- 保留用户配置:不能覆盖用户已有的其它 Claude Code / Codex hooks。
- 可回退 / 可卸载:安装前应备份,并提供移除 TRANFU hooks 与恢复备份的入口。

## 目标
- `install.sh` 在 `--runtime claude-code` 或 `--runtime codex` 时自动安装或修复 TRANFU hooks。
- hooks 合并必须幂等,保留非 TRANFU hooks。
- 提供本地管理入口,支持 `status / install / uninstall / restore`。
- 安装、卸载、恢复前做备份,便于回退。

## 非目标
- 不改变 TATP 事件协议。
- 不上传 prompt、代码、输出或记忆。
- 不依赖宿主环境变量获取 hook 上下文;仍遵守 ADR-0009,从 stdin JSON 读取 hook 上下文。

## 影响
- onboarding 规格新增本地 agent hooks 生命周期规则。
- `install.sh` 下载新的 hook 管理脚本,并在 Claude Code / Codex runtime 下自动接线。
- QUICKSTART / README / SKILL 同步安装、卸载、恢复说明。
