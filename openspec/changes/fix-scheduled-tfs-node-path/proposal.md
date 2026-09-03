# 提案：fix-scheduled-tfs-node-path

- 状态：Implemented
- 关联：`specs/onboarding`、`daily-auto-update-managed-skills`

## 背景

macOS LaunchAgent 不加载用户交互 shell 配置。NVM 安装的 tfs 使用 `#!/usr/bin/env node`,即使 runner
找到 tfs 的绝对路径,其极简 PATH 仍找不到同目录的 node。本机已复现:极简 PATH 下 `tfs --version`
失败,把 tfs 所在目录前置到子进程 PATH 后成功。

## 提案

- runner 为所有 tfs 子进程构造专用环境,仅把 `Path(tfs_bin).parent` 前置到 PATH。
- version、inventory、update 三类 tfs 调用统一经过同一入口。
- 不加载 `.zshrc` / `.bashrc`,不修改 LaunchAgent 的全局环境,不影响其它子进程。
- 增加真实 `#!/usr/bin/env node`、极简 PATH 的回归测试。

## 影响

- M3 `tf_skill_update.py`:tfs 子进程环境构造。
- onboarding 规格与 UPDATE 排障文档:固化非交互 PATH 规则。
- 不改变调度、备份、scope/hash 分层、回滚或对外命令。
