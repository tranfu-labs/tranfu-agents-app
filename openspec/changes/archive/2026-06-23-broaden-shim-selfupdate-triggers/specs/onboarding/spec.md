# 规格 delta:onboarding(扩大 shim 自更新触发面)

> 本 delta 仅替换 `openspec/specs/onboarding/spec.md` 中第 8 / 9 条;其余规则不变。

## 修改后的规则

8. **自更新安全边界**:`tf_selfupdate.py` 在 hook 事件
   `SessionStart` / `on_session_start` / `UserPromptSubmit` / `Stop` / `SessionEnd`
   触发后台静默更新(实际拉取频率受 `~/.tranfu/.selfupdate.json` 的 1 小时节流约束,所有触发点共享一个窗口);
   `PreToolUse` 不触发(频率过高,无收益)。
   必须先下载到 staging,校验 sha256,`.py` 通过 `py_compile`,全部通过后才替换正式文件;失败静默且保留旧文件。
   本地 manifest 与服务端版本一致但目标文件缺失或哈希不符时,必须补齐该文件。`TF_AUTO_UPDATE=0` 完全关闭。

9. Claude Code / Codex / Hermes 的新 shim 在下一次 hook 触发时生效。
   **OpenClaw 在 `session_start` 中 fire-and-forget spawn `python3 ~/.tranfu/tf_selfupdate.py`,
   shim 文件被刷新**;JS 常驻代码本身的生效仍需重启 OpenClaw(`SIGUSR1` 只重读 manifest 的版本号显示)。

## 修改后的可验证行为

- `TF_AUTO_UPDATE=0` 时,以上**任一**触发事件都不启动更新进程。
- 一小时内多次触发自更新,只有第一次会真正请求 `/shims/manifest`,其余被节流跳过(看 `.selfupdate.json` 的 `last_check`)。
- OpenClaw session_start 后,`~/.tranfu/manifest.json` 若与服务端 manifest 不一致,会在 ≤ 1h 内被刷新。

## 不变项(此 delta 不修改,列出以避免误解)

- 规则 1-7 完全不变。
- `tf_selfupdate.py` 自身的下载 / staging / sha256 校验 / py_compile / 原子替换协议不变。
- profile 协议、`shim_version` 字段位置(顶层、sticky)、看板三态不变(由 `fix-shim-version-reporting` 治理)。
