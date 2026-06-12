# spec delta:onboarding(本变更新增的规则)

> 合入后并入 `openspec/specs/onboarding/spec.md`。

## 新增规则(MUST)
- 服务端提供 `GET /shims/manifest`,返回当前 shim 内容版本与文件清单;清单条目必须含下载 `path`、
  安装 `target`、`sha256`、`size`、`executable`。
- `install.sh` 必须按 manifest 全量下载 shim 目标文件,校验 sha256 后才把当前 manifest 写入
  `~/.tranfu/manifest.json`;全量安装失败时不得写入假的本地版本基线。
- 自更新器必须只写入 manifest 声明的 `~/.tranfu/` 相对目标路径,拒绝绝对路径与 `..` 路径。
- 自更新器必须先下载到 staging 并完成 sha256 校验;`.py` 文件还必须通过 `py_compile` 后才允许替换正式文件。
- 自更新失败不得影响宿主 agent:不得抛出到 hook、不得删除旧文件、不得阻塞主流程。
- `TF_AUTO_UPDATE=0` 必须完全关闭后台自更新。
- Claude Code / Codex / Hermes 更新生效点为下一次 hook 触发;OpenClaw 文件可被刷新,但 JS 插件需重启 OpenClaw 生效。

## 可验证行为(新增)
- 本地 manifest 与服务端一致 → 自更新器不下载 shim 文件。
- 本地 manifest 与服务端版本一致但某 target 缺失或哈希不符 → 自更新器下载并修复该 target。
- 服务端某 shim 文件变化 → 下一次 SessionStart 后本地目标文件被替换,manifest 更新。
- 下载内容与 manifest sha256 不一致或 `.py` 语法错误 → 更新中止,旧文件保留。
- 两个 SessionStart 同时触发 → 文件锁保证最多一个更新流程执行。
- `TF_AUTO_UPDATE=0` → hook 不启动更新流程或更新器立即退出。
