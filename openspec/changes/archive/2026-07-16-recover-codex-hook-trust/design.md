# 设计：recover-codex-hook-trust

## 目标与安全不变量

守护只修复“内容未变、位置变了”这一种可证明安全的状态。Codex 仍是信任事实源；TRANFU 不计算替代 hash、不写 trusted hash、不批准新命令。

必须同时满足：

1. `hooks/list` 返回的 source 是 user，且 `sourcePath` 精确指向目标 `hooks.json`。
2. 当前 handler hash 与 `[hooks.state."<key>"] trusted_hash` 能按事件组成完整集合。
3. 每个当前 group 的 handler hash 向量与一个已信任位置 group 的 hash 向量完全相等。
4. 映射是完整且唯一的；任何新增、删除、重复、缺失、复杂结构歧义都拒绝自动修复。
5. 只移动完整 group，保留 matcher、timeout、status message、第三方字段和 group 内 handler 顺序。

## 健康检查流程

1. 获取进程锁；并发检查直接静默退出。
2. 读取 `~/.codex/hooks.json` 与 `~/.codex/config.toml`。配置解析优先使用 Python 3.11 `tomllib`，旧 Python 使用只识别 `[hooks.state."..."]` 与 `trusted_hash` 的窄解析器。
3. 启动 `codex app-server`，发送 `initialize` 与 `hooks/list`，设置总超时并确保子进程退出。
4. 若所有 TRANFU handler 已为 `trusted + enabled`，记录 healthy fingerprint 并结束。
5. 对存在 `modified` 的事件构造“当前 group hash 向量 → 已信任位置 group hash 向量”的唯一双射。只有完整双射成立才进入修复。
6. 写入 `hooks.json.tranfu-guard.bak.<UTC>` 备份，以同目录临时文件 + `os.replace` 原子写入重排结果。
7. 再次调用 `hooks/list`。受影响的 TRANFU handler 必须全部 `trusted + enabled`；否则恢复备份，并再次验证/记录失败。
8. 对不可安全修复但确实需要用户动作的状态计算 fingerprint；fingerprint 与上次通知相同则不重复通知。恢复 healthy 后清除通知 fingerprint，使未来新异常可以再次提醒。

`hooks/list` 属于 Codex 0.144 系列已验证能力，但不是稳定公开契约。命令不存在、方法不存在、响应字段变化、超时或解析失败统一视为 `unsupported/error`：不改文件、不发“重新信任”通知，只写本地状态供诊断。

## 通知

macOS 使用：

```text
osascript -e 'display notification "打开 Codex 输入 /hooks 检查并信任 TRANFU Hook" with title "TRANFU//AGENTS"'
```

通知只说明用户动作，不声称内容安全；不使用 Logo，不创建 `.app`。`osascript` 不存在或调用失败时静默，不能影响 Codex。

## LaunchAgent 生命周期

脚本提供 `install-launch-agent / uninstall-launch-agent / status / check --json`：

- plist 固定为 `~/Library/LaunchAgents/com.tranfu.codex-hook-guard.plist`。
- `ProgramArguments` 使用当前 Python、守护脚本与解析到的 Codex 可执行文件绝对路径。
- `RunAtLoad=true`，`WatchPaths` 监听 `~/.codex/hooks.json`，`StartInterval=300` 兜底。
- 安装使用 `plistlib` 原子写入；内容未变化时不重写。随后 best-effort `launchctl bootout/bootstrap/kickstart`。
- 卸载 best-effort bootout 后删除 plist；不会删除用户 Hook 或信任记录。
- 非 Darwin 平台不安装 LaunchAgent，健康检查本身仍可手动执行。

## 安装与升级自举

- `tf_hooks.py --target codex install` 在完成 Hook 幂等安装后调用守护的 `install-launch-agent`；`uninstall` 对称移除。
- `tf_selfupdate.py` 每次启动时先 best-effort 调用已安装守护的 `install-launch-agent`，再判断远端更新节流。这样旧版自更新器首次下载新文件后，下一个正常 Hook 事件即使仍处于一小时节流窗口，也会补齐 LaunchAgent。
- 如果旧安装的 Codex Hook 在下载新 shim 之前已经全部不执行，自更新链路没有任何进程入口，无法自举；安装文档明确要求重跑一次安装器。

## 状态与隐私

状态文件仅保存 schema、最近检查结果、异常 fingerprint、最近通知时间和必要的短错误类别；不保存 hook command、密钥、prompt、代码或输出。备份沿用用户目录权限，不进入仓库。

## 单元测试

1. 已健康配置不写文件、不通知。
2. 两个 singleton group 纯换序时自动恢复，第三方字段和 matcher 原样保留。
3. 多 handler group 以完整 hash 向量匹配，只移动整个 group。
4. 新增/删除/重复 hash、缺 trusted hash、映射不唯一时拒绝修改并通知一次。
5. 写后 `hooks/list` 仍非 trusted 时恢复备份。
6. 相同 fingerprint 不重复通知；恢复 healthy 后新的同类异常可以再次通知。
7. app-server 不存在、方法不支持、超时、坏 JSON 时静默且不修改。
8. LaunchAgent 安装幂等、参数为绝对路径、卸载只删 managed plist。
9. `tf_selfupdate.py` 在远端检查被节流时仍先补齐守护；`TF_AUTO_UPDATE=0` 不影响本地守护生命周期。
10. `tf_hooks.py` Codex install/uninstall 对称调用守护，Claude 路径不受影响。

## AI 验证流程

1. 在临时 HOME 构造 CodeIsland + TRANFU 两组 Hook 及可信位置 hash，执行 `check --json`，核对备份、重排和复查结果。
2. 在临时 HOME 执行 LaunchAgent install/status/uninstall，解析 plist 核对 `WatchPaths / StartInterval / RunAtLoad`。
3. 在本机真实配置上执行只读 `check --json`，预期返回所有 TRANFU Hook `trusted + enabled` 且不改写文件。
4. 运行现有 shim、安装、manifest、模块边界与全量 pytest 回归。

## 权衡

- 选择位置 hash 的严格排列证明，而不是“看到 modified 就重装”：后者会产生新 hash 并再次要求信任，也可能覆盖第三方配置。
- 选择独立 shim + LaunchAgent，而不是 marketplace plugin：保持现有安装模型，对已安装用户的迁移最小。
- 选择简单系统通知而不是带 Logo 的通知应用：无需签名、打包和额外安装面。
- 不把传输超时并入本 change：Hook 信任修复与事件投递队列是不同故障域，分开更容易验证和回滚。

## 风险与回滚

- Codex 私有 JSON-RPC 变更：守护降级为 no-op/error，不写配置；更新 shim 适配。
- plist 异常：`tf_hooks.py --target codex uninstall` 或守护 `uninstall-launch-agent` 可移除。
- 重排错误：写后验证失败立即恢复备份；用户也可从 `.tranfu-guard.bak.*` 手动恢复。
- 通知骚扰：按异常 fingerprint 去重，unsupported/error 不通知。
