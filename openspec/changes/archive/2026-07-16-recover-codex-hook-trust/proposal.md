# 提案：recover-codex-hook-trust

## 背景

Codex 把用户级 Hook 的信任绑定到 `hooks.json` 中事件、group index 与 hook index 形成的位置 key。多个工具都维护 `~/.codex/hooks.json` 时，即使 TRANFU 与第三方 Hook 的命令内容都没有变化，单纯交换 group 顺序也会让当前位置的 `currentHash` 与 `~/.codex/config.toml` 中该位置的 `trusted_hash` 不一致，Codex 随即把 Hook 标为 `modified` 并停止执行。ChatGPT 客户端不会稳定弹出信任提示，结果是 TRANFU 状态与 Skill 统计静默中断。

现有 `tf_hooks.py` 只能保证 TRANFU Hook 存在、去重和升级命令，不能识别 Codex 的运行时信任状态，也不能区分“安全的纯换序”与“内容确实改变”。已经安装的用户因此需要人工发现并打开 `/hooks`，缺乏持续健康守护。

## 提案

1. 新增 stdlib-only 的 Codex Hook 健康守护脚本，通过版本受控的 `codex app-server` JSON-RPC `hooks/list` 读取 Codex 自己计算的 `currentHash / trustStatus / enabled`。
2. 仅当当前 Hook group 与已信任位置 hash 构成完整、唯一、内容不变的纯排列时，自动把整个 group 重排回已信任位置；写前备份、原子替换、写后复查，失败立即回滚。
3. 新 hash、缺失/重复 hash、复杂结构无法唯一映射、Codex API 不可用或复查失败时不修改信任配置，也不替用户批准内容；只对需要用户动作的异常做去重系统通知，提示在 Codex 打开 `/hooks`。
4. macOS 使用 LaunchAgent 在登录后、`hooks.json` 变化时以及固定周期运行健康检查。Codex Hook 安装/卸载同步安装/卸载该 LaunchAgent。
5. 自更新器在网络更新节流之前补齐 LaunchAgent，让仍可执行 Hook 的既有 Codex 安装在升级后自动获得守护。

## 影响

- **M3 shim**：新增 `tf_codex_hook_guard.py`；`tf_hooks.py` 与 `tf_selfupdate.py` 增加守护生命周期接线。
- **M4 安装与分发**：manifest 分发新脚本；Codex 安装与卸载同步管理 LaunchAgent。
- **onboarding 事实源**：补充 Codex Hook 运行时健康、自愈、通知、升级自举和卸载契约。
- **本机文件**：可能新增 `~/.tranfu/codex-hook-guard-state.json`、守护锁、Hook 备份和 `~/Library/LaunchAgents/com.tranfu.codex-hook-guard.plist`。
- **不改变**：服务端协议、Skill 统计口径、前端、Hook 信任数据的所有权。

## 非目标

- 不自动信任新 hash，不写 `~/.codex/config.toml`。
- 不把 TRANFU 改造成 Codex marketplace/plugin。
- 不写全局 `AGENTS.md` 恢复指令。
- 不处理本次实验发现的服务不可达时 `Stop` Hook 超时；该传输可靠性问题另立 change。
- 不承诺救回在升级前已经全部停止执行、因而无法取得新 shim 的旧安装；这类机器需要重跑安装器一次。
