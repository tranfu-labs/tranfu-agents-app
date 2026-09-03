# 任务：fix-scheduled-tfs-node-path

- [x] 为 `_exec()` 增加可选环境并新增 `_tfs_env()` / `_tfs_exec()`。
- [x] 将 version、inventory、update 三类调用统一切换到 `_tfs_exec()`。
- [x] 增加真实 env-node shebang + 极简 PATH 回归测试。
- [x] 同步 onboarding spec、UPDATE 与 change 状态。
- [x] 运行定向测试、完整 pytest/覆盖率、前端单测/构建和静态检查。
