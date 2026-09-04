# 设计：daily-auto-update-managed-skills

> 后续变更 `backup-planned-skill-updates` 已将本设计中的全量 `tfs installed --json` 备份替换为
> `tfs update --skills-only --check-only --json` 返回的 `outdated.path`;当前事实以 onboarding spec 为准。

## 核心决策

本项目只编排下面这一条命令，不介入命令内部更新规则：

```bash
tfs update --skills-only --json
```

职责链路：

```text
TRANFU//AGENTS install/selfupdate
  → 安装或修复用户级 scheduler
  → 每日启动 tf_skill_update.py
  → 从 tfs 获取受管安装清单
  → 备份清单中的现有路径和 tfs registry
  → 执行 tfs update --skills-only --json
  → 保存结果，按保留策略清理旧备份
  → 用户需要时显式 rollback
```

## 分层契约

### tfs 是更新事实源

runner 把 tfs 当成独立、可演进的更新工具：

- `tfs installed --json` 提供受管安装项及其路径，作为备份输入。
- `tfs update --skills-only --json` 决定本轮更新对象并执行更新。
- scope、runtime、版本、hash、本地修改、远端状态、下载和替换均由 tfs 负责。
- runner 不根据路径猜 scope，不比较版本，不计算 Skill hash，不改变 tfs 返回的单项状态。

以后 tfs 扩展 project scope、调整 hash 规则或增加保护状态时，本项目无需同步复制判断逻辑；只要命令与 JSON
入口保持兼容即可。

### runner 是调度与备份外壳

runner 只负责：

1. 到期与单实例守门。
2. 找到可执行的 tfs。
3. 获取 tfs 自己声明的受管路径并创建更新前快照。
4. 调用更新命令并保存有界结果。
5. 提供显式回滚和备份保留策略。
6. 安装、检查、卸载 OS 用户级调度。

runner 不承诺自动判断“该不该更新”，也不对 tfs 的成功结果做二次业务裁决。

## runner 接口

新增 `~/.tranfu/tf_skill_update.py`：

```text
tf_skill_update.py run [--json] [--force]
tf_skill_update.py status [--json]
tf_skill_update.py rollback --latest [--json]
tf_skill_update.py rollback --run <run-id> [--json]
tf_skill_update.py install-schedule [--json]
tf_skill_update.py ensure-schedule [--json]
tf_skill_update.py uninstall-schedule [--json]
```

- `--force` 只绕过 runner 的“本地日已执行”守门，不转换成 tfs 的 `--force` 参数。
- 所有子进程使用参数数组和绝对 executable，不通过 `shell=True`。
- 脚本只用 Python 标准库，异常转成状态结果，不进入 agent Hook 调用栈。

## 单轮执行

### 1. 到期和锁

- 读取 `~/.tranfu/skill-update-config.json`；disabled 时直接结束。
- scheduler 触发且本地日已经执行过时记录 noop；人工 `run --force` 可再次执行。
- 获取 `~/.tranfu/.skill-update.lock`，避免同一用户的重复 scheduler 进程并发。
- 锁只保护 runner 自身；tfs 是否与人工更新并发由 tfs 自己负责。

### 2. 发现 tfs

定时环境通常不读取交互 shell rc，runner 依次检查：

1. config 中上次可用的 tfs path hint；
2. 当前 PATH；
3. Homebrew、`/usr/local/bin`、`~/.local/bin` 与 `~/.nvm/versions/node/*/bin` 等常见入口。

候选必须是当前用户可执行常规文件，且 `tfs --version` 成功。找不到时记录 `tfs_not_found`；不自动安装或升级 CLI。
version、inventory、update 都通过同一个 tfs 执行入口,只在该子进程环境中把 tfs 所在 bin 目录前置到 PATH,
使 LaunchAgent 极简环境仍可解析 NVM 等 `#!/usr/bin/env node`;不加载用户 shell rc。

### 3. 创建备份

runner 先执行：

```bash
tfs installed --json
```

它只消费每条受管安装项的 `name` 和 `path`：

- 不解释或筛选 scope/runtime。
- path 不存在时记入 snapshot manifest 的 skipped，不创建猜测目录。
- 拒绝备份 `/`、用户 home 本身或空路径；相同真实路径去重。
- 对每个有效目录使用 `shutil.copytree(..., symlinks=True)` 复制，不跟随目录内 symlink 越界读取。
- 同时备份存在的 `~/.tfs/installed.json`。

备份结构：

```text
~/.tranfu/skill-backups/<run-id>/
  manifest.json
  tfs-installed.json
  items/
    0001/
    0002/
```

`manifest.json` 记录原始绝对路径、备份相对路径、Skill 名、开始时间和备份状态，不保存环境变量或凭证。
只有清单中所有存在的目标都备份成功后才执行 update；备份不完整则本轮停止，避免产生不可回滚更新。

### 4. 执行更新

备份成功后只执行：

```text
[tfs_bin, "update", "--skills-only", "--json"]
```

- 不加 scope、runtime、force、ack-deletions 或 self 参数。
- 设置总超时和 stdout/stderr 大小上限。
- JSON 能解析时保存 tfs 返回的摘要；不能解析时只保存有界错误码和截断摘要。
- runner 不因为某个 tfs 单项状态自行恢复备份；自动更新和一致性仍由 tfs 负责。
- 备份始终保留，供用户在观察结果后显式回滚。

### 5. 状态与保留

`~/.tranfu/skill-update-state.json` 使用 mode 0600 原子写入，只保留最近一次状态：

```json
{
  "schema": 1,
  "enabled": true,
  "scheduler": "launchd",
  "last_attempt_at": "UTC instant",
  "last_attempt_local_day": "YYYY-MM-DD",
  "last_success_at": "UTC instant",
  "status": "updated|noop|completed_with_errors|failed|busy|disabled",
  "backup_run": "20260903T120000Z",
  "updated": 2,
  "error": "bounded_error_code"
}
```

备份默认保留最近 3 个完成 run。清理只允许删除
`~/.tranfu/skill-backups/` 下能解析且 manifest schema/路径均有效的旧 run，不跟随 symlink，不触碰其它目录。

## 人工回滚

回滚是显式、整轮恢复：

```bash
python3 ~/.tranfu/tf_skill_update.py rollback --latest
python3 ~/.tranfu/tf_skill_update.py rollback --run 20260903T120000Z
```

流程：

1. 校验 run id、manifest schema、备份路径和所有目标。
2. 获取 runner lock。
3. 在每个目标同级建立 restore staging。
4. 将当前目录保留为本次 rollback 的临时保险副本。
5. 用备份恢复所有目标，并恢复当时的 tfs registry。
6. 全部完成后记录 rollback 结果；失败时尽量恢复 rollback 前现场。

rollback 会覆盖更新后产生的本地变化，因此绝不由 scheduler 自动触发。用户必须显式执行；实现时的 CLI 输出要先列出
run id 和目标数量，再开始恢复。

## 调度

### macOS

- `~/Library/LaunchAgents/com.tranfu.skill-update.plist`
- Label：`com.tranfu.skill-update`
- `ProgramArguments`：绝对 Python、runner、`run --json`
- `StartCalendarInterval`：每日一个稳定 Hour/Minute
- `RunAtLoad=true`：登录时做一次到期检查
- stdout/stderr 指向 `/dev/null`

安装使用 `launchctl bootstrap gui/$UID`；重复安装只在 plist 变化或 service 未加载时重载。卸载前验证 Label，只删除
managed plist。

### Linux

- `~/.config/systemd/user/tranfu-skill-update.service`
- `~/.config/systemd/user/tranfu-skill-update.timer`
- service 使用 `Type=oneshot` 和绝对 ProgramArguments
- timer 使用 `OnCalendar=daily`、`Persistent=true`、`RandomizedDelaySec`

没有可用 user systemd 时记录 `scheduler_unavailable`，不请求 sudo，也不自动修改 crontab。

## 安装和旧客户端迁移

`install.sh` 增加：

```text
--auto-update-skills
--no-auto-update-skills
```

`TF_SKILL_AUTO_UPDATE=0` 明确关闭，其余情况默认开启。最终选择写入 mode 0600 的
`~/.tranfu/skill-update-config.json`；scheduler 不依赖 shell 环境继承。

新安装流程：

1. 按 manifest 安装全部 shim。
2. 写 config。
3. 开启时执行 `install-schedule`，关闭时执行 `uninstall-schedule`。
4. schedule 失败只显示 warning，继续完成 Hook 安装、注册和 doctor。

旧客户端迁移：

1. 旧版 `tf_selfupdate.py` 在正常 Hook 中下载包含 runner 的新 manifest。
2. 当前进程仍运行旧代码，因此不要求同一轮立即安装 schedule。
3. 下一次 Hook 启动新版 `tf_selfupdate.py`。
4. 新版在远端 manifest 节流前 best-effort 调用 runner `ensure-schedule`,只修复调度而不改变持久化开关。
5. 如果持久化配置为 disabled,则不安装并确保 managed schedule 被卸载。

## 失败处理

- tfs 不存在：不创建备份、不执行更新，记录 `tfs_not_found`。
- inventory 失败或 JSON 无效：不执行更新，记录 `inventory_failed`。
- 任一现有目标备份失败：不执行更新，保留未完成 run 供诊断和后续清理。
- update 失败：保存 tfs 结果和备份 run id，不自动 rollback。
- scheduler 安装失败：不影响 TRANFU 安装与 agent 使用。
- 设备离线：当日失败；下次日历或登录到期检查重试。

所有失败都不写 Agent 遥测，不上报 Skill 内容，不阻塞 Hook。

## 备选方案

### 直接调 tfs、不备份

最短，但用户无法从客户端侧恢复一次不符合预期的更新，不选。

### runner 复制 tfs 的 scope/hash 判断

会形成两份事实源，tfs 行为变化时必然漂移，不选。

### 自动回滚所有 tfs 失败

tfs 可能部分成功，整轮自动回滚会撤销已成功更新；而单项恢复又要求 runner 理解 tfs 业务状态。保持显式整轮回滚更简单。

### 每次会话开始更新

会把网络与磁盘工作带到交互时段，并与 runtime 读取 Skill 竞态；保持独立每日 scheduler。

## 测试设计

- fake tfs 断言 runner 先调用 `installed --json`，完成备份后才调用 `update --skills-only --json`。
- update argv 不含 scope、runtime、self、force 或 ack-deletions。
- inventory 返回混合 scope/runtime/path 时，runner 不按 scope 筛选，所有有效唯一路径都进入备份。
- 空路径、home、根目录、重复路径、缺失路径和 symlink 均按安全规则处理。
- 任一备份失败时 update 不被调用。
- update 成功、非零退出、坏 JSON 和超时均保留 backup run 并写有界状态。
- 最近第 4 个完整 backup 创建后只清理最旧 managed run，不触碰其它文件。
- rollback 恢复全部目标和 registry；restore 中途失败时尽量恢复 rollback 前现场。
- LaunchAgent/systemd user timer 安装、重复安装、状态和卸载幂等。
- 新安装立即有 schedule；旧客户端下载新 shim 后下一次 Hook 补齐 schedule。
- `TF_SKILL_AUTO_UPDATE=0` 不安装或卸载 schedule，但不删除备份、Skill、tfs registry 或 Hook。

## 调度语义参考

- [Apple：Scheduling Timed Jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html)
- [systemd：systemd.timer](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml)
