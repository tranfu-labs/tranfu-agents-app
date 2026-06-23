# 变更提案:broaden-shim-selfupdate-triggers(扩大 shim 自更新触发面)

- 状态:Proposed(回补:代码已落地,待归档时合并 spec-delta)
- 关联:specs/onboarding、`self-update-shims` (引入自更新)、`fix-shim-version-reporting` (修正版本上报)

## 背景 / 问题

`self-update-shims` 实现了 `/shims/manifest` 自更新协议:本地 `tf_selfupdate.py` 拉服务端 manifest,
按 sha256 增量替换 `~/.tranfu/` 下的 shim 文件。`fix-shim-version-reporting` 让看板能稳定看出"谁还在跑旧 shim"。

但线上观察到一个执行面盲点:看板上明明显示了一批 `outdated` 的 agent,可它们的 shim 始终不自动升级。
排查后定位到自更新的**触发面**有两个洞:

1. **`tf_hook.py` 只在 `SessionStart` / `on_session_start` 触发 selfupdate**(见 `SELFUPDATE_EVENTS`)。
   现实里 Claude Code / Codex 用户开一个长会话跑半天,从不退出——也就**永远不会触发自更新**;只有重启
   会话才有机会拉新 manifest。结果是 manifest 在服务端早换了,客户端纹丝不动。
2. **OpenClaw 完全不走自更新链路**。它的 reporter (`shims/openclaw/reporter.mjs`) 是独立 JS 插件,
   不调用 `tf_hook.py`,也从未 spawn `tf_selfupdate.py`。OpenClaw 一旦装上,**永远不会自更新**。

线上证据(2026-06-23 抽样):
- `阿发/codex`、`阿萌/claude-code` 已升到 `8e0b47a0…` (manifest latest):新开过会话,触发了 SessionStart。
- `Wing/claude-code`、`Wing/codex`、`NEZHA/claude-code`、`小北/codex` 卡在 `24116eef…`:活跃的老会话。
- `阿萌/openclaw`、`小北/openclaw`:`shim_version` 全为 `None`,因为 OpenClaw 这条路径根本不上报也不更新。

## 目标(MUST)

- **`tf_hook.py` 触发面扩展**:`SELFUPDATE_EVENTS` 增加 `UserPromptSubmit`、`Stop`、`SessionEnd`。
  长会话每次发 prompt / 一轮结束 / 会话关闭都顺手做一次自更新检查。
- **OpenClaw 接入自更新**:`reporter.mjs` 在 `sessionStart` 中 fire-and-forget spawn `python3 ~/.tranfu/tf_selfupdate.py`,
  跟 Python shim 同款 detached + unref + 静默失败。
- **触发面扩展不能放大资源消耗**:依赖 `tf_selfupdate.py` 自带的 1 小时 `CHECK_INTERVAL` 节流
  (`~/.tranfu/.selfupdate.json` 的 `last_check`),所有新触发点共享同一个节流窗口,manifest 真实拉取频率不变。
- **失败必须静默**:`spawn` 抛错 / `python3` 缺失 / 脚本缺失 / 节流跳过 → 都不能影响宿主 agent 的 hook / 会话。
- **`TF_AUTO_UPDATE=0` 完全有效**:扩展后的所有触发点都尊重这个开关。

## 非目标

- 不动 `tf_selfupdate.py` 本身的下载 / staging / py_compile / 原子替换协议。
- 不增加 `PreToolUse` 作为触发事件——一轮可能跑几十次,即便有节流也是无谓的文件 IO。
- 不做 OpenClaw 进程内的 JS 热重载;`reporter.mjs` 仍然依赖 `SIGUSR1` 重读 manifest 才能更新 `shim_version` 显示,
  实际 JS 逻辑生效仍需重启 OpenClaw(`self-update-shims` proposal 的"非目标"延续)。
- 不改前端的三态判定;触发面扩大本身不引入新的状态。

## 影响

- **specs/onboarding**:第 8 条"自更新安全边界"事件清单从 `SessionStart/on_session_start` 扩展为五项;
  第 9 条 OpenClaw 路径从"不接自动更新"改为"`session_start` 触发自更新"。
- **不影响**:specs/ingest(`shim_version` 字段位置与 sticky 协议不变)、specs/board、specs/admin。
