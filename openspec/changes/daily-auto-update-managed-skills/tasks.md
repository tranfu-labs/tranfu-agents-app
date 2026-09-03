# 任务：daily-auto-update-managed-skills

> 实现、测试与事实规格同步均已完成。

## Runner 与备份

- [x] R1. 新增 stdlib-only `shims/tf_skill_update.py`，实现 `run/status/rollback/install-schedule/ensure-schedule/uninstall-schedule`。
- [x] R2. 实现 tfs 路径发现、本地日到期守门、runner 单实例锁、超时和有界输出。
- [x] R3. 调用 `tfs installed --json` 获取受管路径；不解释 scope/runtime，完成路径安全校验、去重和缺失记录。
- [x] R4. 更新前备份全部现有受管路径和 `~/.tfs/installed.json`，任一现有目标备份失败时不调用 update。
- [x] R5. 只调用 `tfs update --skills-only --json`，保存结果但不复制 tfs 的 scope/hash/本地修改判断。
- [x] R6. 实现最近 3 个 managed backup run 的安全保留和显式整轮 rollback。

## 调度与升级带入

- [x] S1. 实现 managed macOS LaunchAgent，支持每日日历、登录到期检查、幂等安装/状态/卸载。
- [x] S2. 实现 managed Linux systemd user service/timer；无 user systemd 时安全跳过。
- [x] S3. 把 runner 加入 shim manifest 分发，并让 `tf_selfupdate.py` 在远端节流前 best-effort ensure schedule。
- [x] S4. `install.sh` 增加 `--auto-update-skills` / `--no-auto-update-skills` 与 `TF_SKILL_AUTO_UPDATE`，默认开启。
- [x] S5. `tf-doctor` 展示 enabled/backend/last result/backup run，不打印凭证或 Skill 内容。

## 测试与文档

- [x] V1. 增加 inventory、路径安全、备份顺序、更新 argv、失败保留、清理和 rollback 单元测试。
- [x] V2. 增加 LaunchAgent、systemd、install flags、manifest、自更新补齐和双 runtime 幂等测试。
- [x] V3. 验证新安装立即带 schedule，旧客户端两次正常 Hook 内完成 runner 下载与 schedule 补齐。
- [x] V4. 运行 `python -m py_compile server/*.py server/routes/*.py shims/*.py`、`pytest tests/`、覆盖率门槛与 `bash -n install.sh`。
- [x] V5. 更新 `INSTALL.md`、`QUICKSTART.md`、`USAGE.md`、`UPDATE.md`、`SKILL.md`、`docs/architecture/module-map.md` 与根 `AGENTS.md`。
- [x] V6. 将 spec delta 合并进 `openspec/specs/onboarding/spec.md`，完成实现与事实规格闭环。
