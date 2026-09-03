# 提案：daily-auto-update-managed-skills

- 状态：Implemented
- 关联：`specs/onboarding`、M3 shim、M4 安装与分发、ADR-0007、ADR-0010、ADR-0024

## 背景

用户安装公司 Skill 后，目前仍需主动执行更新命令才能获得新版。TRANFU//AGENTS 已经具备 shim manifest、
客户端自更新和用户级 LaunchAgent 的基础设施，可以在客户端补充一个独立、低频的 Skill 自动更新任务。

用于每日更新 Skill 的命令确定为：

```bash
tfs update --skills-only --json
```

裸 `tfs update` 还会升级 CLI 自身，不属于本需求。

## 目标

- 新安装和已升级的 TRANFU//AGENTS 客户端默认获得每日 Skill 更新能力，并允许明确关闭。
- 每次更新前备份当前由 tfs 管理的 Skill 和 tfs 安装登记，保留可人工回滚的最近快照。
- 更新本身完全交给 `tfs update --skills-only --json`；本项目不判断 user/project scope、版本 SHA、
  本地修改或具体更新对象。
- 定时、备份或命令失败不得影响 agent 会话、Hook 或 TRANFU 状态上报。
- 同一 OS 用户只维护一个定时任务，安装、升级、重复接入和关闭均幂等。

## 分层边界

### `tranfu-skills` / tfs 负责

- 定义哪些 Skill 属于已安装和受管对象。
- 决定更新哪些 runtime、scope 和路径。
- 判断版本、hash、本地修改、远端删除以及是否允许覆盖。
- 下载、替换 Skill，并通过 JSON 返回更新结果。

上述行为如何演进只修改 tfs；TRANFU//AGENTS 不复制这些业务规则。

### `tranfu-agents-app` 负责

- 在用户端安装每日调度。
- 从 `tfs installed --json` 获取 tfs 声明的受管路径，并在更新前创建完整快照。
- 调用且只调用 `tfs update --skills-only --json` 执行更新。
- 保存最近执行结果，提供显式的人工回滚命令。
- 通过 install/selfupdate 链路为新旧客户端安装或修复定时任务。

## 非目标

- 不在本项目里实现 scope、版本、hash 或本地修改判断。
- 不解析 Skill 内容来决定是否更新，不自动合并用户修改。
- 不自动执行 `tfs update --self`，不安装新 Skill。
- 不让服务端远程触发客户端命令，不新增服务端 API。
- 不把备份或更新结果写进 Agent 遥测、事件、身份、session 或看板。
- 不承诺当前运行中的 agent 热加载新 Skill；生效时机由 runtime 和 tfs 决定。

## 提案

### 客户端 runner

新增 stdlib-only `shims/tf_skill_update.py`，提供：

- `run --json`：获取受管清单、创建备份、执行 tfs 更新、保存结果。
- `status --json`：查看是否启用、调度后端和最近结果。
- `rollback --latest|--run <id>`：显式恢复某次更新前的备份。
- `install-schedule` / `uninstall-schedule`：管理用户级定时任务。

### 每日调度

- macOS 使用 managed LaunchAgent：`~/Library/LaunchAgents/com.tranfu.skill-update.plist`。
- Linux 使用 managed systemd user service/timer。
- 每日执行一次；登录或 timer 恢复时可补查漏跑，同一本地日不重复执行真实更新。
- 定时任务只启动 runner，不直接写 tfs 路径或拼接 shell 命令。

### 安装与升级带入

- `install.sh` 完整安装 shim 后立即确保定时任务存在。
- `tf_skill_update.py` 纳入 `/shims/manifest`，由现有 `tf_selfupdate.py` 下载给旧客户端。
- 新版 `tf_selfupdate.py` 每次启动时在远端 manifest 节流前 best-effort 确保定时任务存在。
- 旧客户端第一次 Hook 下载新版 runner/selfupdate，下一次 Hook 使用新版逻辑补齐定时任务。
- 默认开启；`TF_SKILL_AUTO_UPDATE=0` 或 `--no-auto-update-skills` 明确关闭并卸载 managed schedule。

## 影响

- **M3 shim**：新增 runner；`tf_selfupdate.py` 增加本地 schedule ensure。
- **M4 安装与分发**：manifest 分发 runner；`install.sh` 增加自动更新开关并管理 schedule。
- **本机文件**：新增更新配置、最近状态、备份目录，以及对应的 LaunchAgent/systemd user unit。
- **文档与测试**：补安装、关闭、状态、回滚和新旧客户端迁移说明。

## 验收摘要

- 新安装完成后只有一个用户级 Skill 更新任务；重复安装不会增加副本。
- 旧客户端通过 shim 自更新拿到新文件后，下一次正常 Hook 自动补齐定时任务。
- 每轮先依据 `tfs installed --json` 完成备份，再执行一次且仅一次
  `tfs update --skills-only --json`。
- runner 不按 scope/hash/版本做更新判断，tfs 返回什么更新结果就记录什么结果。
- 人工回滚可恢复选定 run 的 Skill 快照和 tfs registry；不会自动静默回滚。
- 缺少 tfs、备份失败、更新失败或调度不可用时，agent 和 TRANFU 上报不受影响。
