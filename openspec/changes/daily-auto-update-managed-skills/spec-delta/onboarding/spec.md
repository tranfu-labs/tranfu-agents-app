# onboarding 规格增量：每日自动更新受管 Skill

## 新增规则（MUST）

1. 客户端每日自动更新 Skill 时，runner 必须且只能调用
   `tfs update --skills-only --json` 执行更新；不得添加 scope、runtime、self、force 或 ack-deletions 参数。
2. tfs 是更新行为的唯一事实源。哪些安装项被更新，以及 scope、runtime、版本、hash、本地修改、远端删除、下载和
   替换规则均由 tfs 决定；TRANFU//AGENTS runner 不得复制、覆盖或二次裁决这些规则。
3. runner 必须在更新前调用 `tfs installed --json` 获取 tfs 声明的受管安装路径。runner 只能把清单用作备份输入，
   不得按 scope/runtime 过滤；空路径、根目录、用户 home、重复路径、缺失路径和 symlink 必须经过安全守门。
4. 只有清单中全部现有有效目标以及存在的 `~/.tfs/installed.json` 完成备份后，runner 才能调用 update。任一现有目标
   备份失败时，本轮必须停止且不得更新。
5. 备份必须保存在 `~/.tranfu/skill-backups/<run-id>/`，包含可校验 manifest、每个目标的原始绝对路径与完整快照。
   默认只保留最近 3 个完成的 managed run；清理不得离开该根目录、跟随 symlink 或触碰非 managed 文件。
6. rollback 必须由用户显式执行，并按选定 run 整轮恢复 Skill 目标和 tfs registry。scheduler 不得根据 tfs 状态自动
   rollback；回滚前后的失败保护和结果必须本地可诊断。
7. 自动更新必须使用用户级原生调度：macOS managed LaunchAgent；Linux managed systemd user timer。同一 OS 用户
   最多一个任务，安装、重复接入、状态检查和卸载必须幂等，不得请求 sudo 或修改第三方任务。
8. `install.sh` 必须在新安装时立即确保 schedule；runner 必须由 shim manifest 分发。旧客户端第一次 Hook 下载新版
   runner/selfupdate，下一次 Hook 由新版 selfupdate 在远端节流前 best-effort 补齐 schedule。
9. Skill 自动更新默认开启；以 `TF_SKILL_AUTO_UPDATE=0` 重跑安装器或传 `--no-auto-update-skills` 明确关闭并卸载 managed schedule，
   但不得删除 Skill、备份、tfs registry、Hook 或第三方任务。
10. runner 必须 stdlib-only、best-effort、不经 shell 拼接命令、不阻塞 agent 会话。tfs 缺失、inventory 失败、备份失败、
    update 失败、坏 JSON、超时或 scheduler 不可用均不得影响 Hook、TRANFU 上报或 agent 运行。
11. 配置、状态和 backup manifest 必须 mode 0600、原子写入并保持有界；不得保存密钥、环境变量、prompt、代码、输出或
    无限日志，也不得把更新或备份结果加入 Agent 遥测和看板。

## 可验证行为

- fake tfs 观察到 runner 先调用 `installed --json`，备份完成后才调用一次
  `update --skills-only --json`，update argv 不含其它业务参数。
- inventory 同时返回不同 scope/runtime 时，runner 不按这些字段筛选，所有现有有效唯一路径均进入备份。
- inventory 中出现 `/`、用户 home、空路径、重复路径、缺失路径或 symlink 时，runner 按安全规则拒绝、去重或记录，
  不扩大读取范围。
- 任一现有目标备份失败时 update 未被调用，原 Skill 与 registry 不变。
- update 成功、非零退出、坏 JSON 或超时后，对应 backup run 仍存在且状态文件给出有界结果；runner 不自动 rollback。
- 创建第 4 个完成 run 后只删除最旧 managed run，`skill-backups` 外文件和无效 manifest 目录不受影响。
- 显式 rollback 可恢复选定 run 的全部目标和 registry；未执行 rollback 时备份不会改变当前 Skill。
- 两次安装或两个 runtime 先后接入后，macOS 只有一个 LaunchAgent，Linux 只有一组 systemd user unit/timer。
- 新安装立即获得 schedule；旧客户端通过一次更新 Hook 下载新文件，下一次 Hook 补齐 schedule。
- `TF_SKILL_AUTO_UPDATE=0` 或 `--no-auto-update-skills` 后 managed schedule 消失，其它本地数据不被删除。
- tfs 不存在、设备离线或 scheduler 不可用时，agent Hook 正常返回，TRANFU 上报不受影响。
