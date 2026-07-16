# onboarding spec delta：Codex Hook 信任健康守护

## ADDED Requirements

### Requirement: Codex Hook 纯换序必须可安全自愈

Codex 安装 MUST 提供 stdlib-only 的 Hook 健康守护。守护 MUST 以 Codex `hooks/list` 返回的 `currentHash / trustStatus / enabled` 为运行时事实，并仅在当前 handler hash 与已持久化 trusted hash 按事件构成完整、唯一且内容不变的 group 排列时自动重排 `~/.codex/hooks.json`。重排 MUST 移动完整 group，保留 matcher、第三方字段与 group 内 handler 顺序；写入前 MUST 备份，写入 MUST 原子化，写后 MUST 再次确认受影响 TRANFU handler 全部 `trusted + enabled`，否则 MUST 回滚。

守护 MUST NEVER 写入 Codex trusted hash、自动批准新内容或以“重装 TRANFU Hook”冒充纯换序修复。新增、删除、重复、缺失或无法唯一映射的 hash，以及未知结构，均 MUST 拒绝自动修改。

#### Scenario: 第三方安装器交换 Hook group 顺序

- **GIVEN** 同一事件包含 CodeIsland 与 TRANFU 两个已信任 group
- **AND** 外部程序只交换两个完整 group，命令内容和 hash 集合未变
- **WHEN** 守护运行
- **THEN** `hooks.json` 被备份并重排回 trusted hash 对应位置
- **AND** 写后 `hooks/list` 中 TRANFU handler 为 `trusted + enabled`
- **AND** 第三方 group 的 matcher、字段和内容原样保留

#### Scenario: Hook 内容真正变化

- **GIVEN** TRANFU 或第三方 handler 出现 trusted state 中不存在的新 hash
- **WHEN** 守护运行
- **THEN** `hooks.json` 与 `config.toml` 均不被修改
- **AND** 用户收到提示打开 Codex `/hooks` 的通知

#### Scenario: 写后复查失败

- **WHEN** 守护完成重排但复查仍未得到 `trusted + enabled`
- **THEN** 守护恢复写入前备份
- **AND** 不留下半修复配置

### Requirement: Codex Hook 健康检查必须持续运行且可回退

macOS Codex Hook 安装 MUST 同步安装 managed LaunchAgent，在登录加载、`~/.codex/hooks.json` 变化和最长 300 秒周期内运行守护。安装 MUST 幂等；卸载 Codex Hook MUST 同步卸载 managed LaunchAgent，且不得删除用户 Hook、信任记录或第三方配置。非 macOS 平台 MUST 静默跳过 LaunchAgent，保留手动健康检查能力。

需要用户重新信任的异常通知 MUST 按状态 fingerprint 去重；恢复健康后 MUST 清除旧 fingerprint。Codex 命令不存在、`hooks/list` 不支持、响应字段变化、超时或解析失败时，守护 MUST 静默降级并记录本地诊断状态，不得改文件或反复通知。

#### Scenario: 重复运行安装器

- **WHEN** 用户多次安装 Codex Hook
- **THEN** 只存在一个 `com.tranfu.codex-hook-guard` LaunchAgent
- **AND** plist 内容与当前 Python、守护脚本、Codex 可执行文件及目标 `hooks.json` 一致

#### Scenario: 同一异常持续存在

- **WHEN** 周期检查多次看到同一个需要信任的异常 fingerprint
- **THEN** 系统通知只出现一次
- **AND** 异常恢复健康后，未来新的异常可以再次通知

### Requirement: 已安装用户升级后必须补齐守护

`tf_selfupdate.py` MUST 在远端更新节流判断之前 best-effort 补齐 Codex LaunchAgent，使仍能触发自更新的既有 Codex 安装在获得新 shim 后的下一次正常 Hook 事件完成守护安装。该本地补齐不得因远端 manifest 一小时节流而跳过，也不得抛错或阻塞宿主 agent。

升级前已经完全失去 Hook 执行入口的旧安装不具备自举条件；文档 MUST 明确要求这类用户重跑安装器一次，不得声称能够后台自动恢复。

#### Scenario: 新 shim 已下载但远端检查仍在节流

- **GIVEN** 本机已有 `tf_codex_hook_guard.py` 但尚无 LaunchAgent
- **AND** `.selfupdate.json` 表示远端 manifest 检查仍在一小时节流窗口内
- **WHEN** 新版 `tf_selfupdate.py` 被下一次 Hook 触发
- **THEN** LaunchAgent 被补齐
- **AND** 不发起新的 manifest 网络请求

## NON-GOALS

- 本 change 不修改事件传输 spool 或 `Stop` Hook 网络超时行为。
- 本 change 不引入 Codex plugin/marketplace、全局 `AGENTS.md` 恢复指令或带 Logo 通知应用。
