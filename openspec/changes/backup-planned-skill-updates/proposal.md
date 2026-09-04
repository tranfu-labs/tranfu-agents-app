# 提案：backup-planned-skill-updates

- 状态：Implemented

## 背景
每日 runner 目前调用 `tfs installed --json` 并备份全部 registry 项,范围大于
`tfs update --skills-only --json` 实际更新范围。本机 launchd 强制回放时,一个位于 Documents 的 project
Skill 因 File Provider `Resource deadlock avoided` 令全轮备份失败,user Skill 更新未执行。

## 提案
改为先调用 `tfs update --skills-only --check-only --json`,只取 `status=outdated` 且带绝对 path 的计划项
作为备份目标;备份成功后仍原样执行 `tfs update --skills-only --json`。

## 影响
- `tf_skill_update.py`:inventory 改为 update plan。
- 测试、onboarding spec、AGENTS/module-map/UPDATE。
- 依赖 tfs check-only JSON 提供 path;旧 tfs 缺 path 时安全停止,不退回全量 installed。
