# 任务:manage-agent-hooks

- [x] 新增 `shims/tf_hooks.py`,支持 Claude Code / Codex 的 status/install/uninstall/restore。
- [x] 保留 `shims/tf_claude_hooks.py` 兼容入口。
- [x] `install.sh` 下载该脚本,并在 `--runtime claude-code` / `--runtime codex` 时自动幂等安装 hooks。
- [x] 增加卸载与恢复说明,同步 QUICKSTART / README / SKILL / onboarding spec。
- [x] 校验:
  - [x] Claude 已安装 hooks 时重复 install 不改文件。
  - [x] Codex 已安装 hooks 时重复 install 不改文件。
  - [x] 缺单个事件时 install 只补缺项。
  - [x] 有重复 TRANFU hook 时 install 去重。
  - [x] uninstall 保留非 TRANFU hooks。
  - [x] restore 能恢复安装前文件或删除安装创建的文件。
  - [x] `python -m py_compile shims/tf_hooks.py shims/tf_claude_hooks.py shims/tf_hook.py shims/tf_report.py`。
  - [x] `bash -n install.sh`。
