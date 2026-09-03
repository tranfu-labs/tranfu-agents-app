# onboarding 规格增量：非交互 tfs 执行环境

## 新增规则（MUST）

每日 Skill 更新 runner 调用 tfs 时,必须为该子进程把 tfs 入口所在目录前置到 PATH,使 NVM 等用户级
Node 安装下的 `#!/usr/bin/env node` 能解析同目录 node。version、inventory、update 必须复用同一环境构造。
runner 不得为此加载 `.zshrc`、`.bashrc` 等用户交互 shell 文件,也不得修改其它子进程或 LaunchAgent 的全局环境。

## 可验证行为

- 极简 PATH 不含临时 NVM bin,临时 tfs 使用 `#!/usr/bin/env node`,同目录存在 node → version、installed、
  `update --skills-only --json` 均成功。
- 去掉同目录 node → tfs 候选验证失败并保持 best-effort,不影响 Hook 或 Agent。
