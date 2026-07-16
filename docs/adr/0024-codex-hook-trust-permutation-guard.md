# ADR-0024 Codex Hook 信任纯换序守护

- 状态:Accepted
- 关联:[ADR-0010](0010-idempotent-local-hook-management.md)(Hook 配置幂等管理)、[ADR-0016](0016-codex-skill-usage-from-rollout.md)(Codex Skill 补采)、`openspec/changes/recover-codex-hook-trust/`

## 背景

Codex 将用户 Hook 信任绑定到 `sourcePath:event:group-index:handler-index` 位置 key，并在该位置保存 `trusted_hash`。多个安装器共同维护 `~/.codex/hooks.json` 时，单纯交换完整 group 的顺序也会让当前位置 hash 改变；Codex 将内容未变的 Hook 标记为 `modified` 并停止执行。ChatGPT 客户端不保证主动弹出信任提示，TRANFU 状态与 Skill 统计会静默中断。

只重新运行 `tf_hooks.py install` 不能解决该问题：它会保留当前 group 顺序，且任何真实命令变化仍应由用户确认，TRANFU 不得绕过 Codex 信任模型。

## 决策

1. 新增 stdlib-only `tf_codex_hook_guard.py`，以 Codex app-server `hooks/list` 返回的 `currentHash / trustStatus / enabled` 为运行时事实。
2. 守护只接受严格证明的纯排列：同一事件的当前完整 group hash 向量与 trusted 位置 group hash 向量集合完全相同、数量一致且映射唯一。修复只移动完整 group。
3. 写前备份、原子替换、写后重新调用 `hooks/list`；TRANFU handler 未全部恢复 `trusted + enabled` 时立即回滚。
4. 永不写 `~/.codex/config.toml`，永不生成或批准 trusted hash。新 hash、缺失/重复 hash、未知结构或 API 不兼容一律不自动修改。
5. 需要用户动作的新内容/禁用状态用 macOS 简单通知提示打开 `/hooks`，按异常 fingerprint 去重；API 不兼容只记本地状态，不骚扰用户。
6. macOS 用 managed LaunchAgent 在登录、`hooks.json` 变化与 300 秒周期运行；Codex Hook 安装/卸载对称管理 LaunchAgent，自更新器在远端节流之前补齐它。

## 后果

- ✅ 第三方安装器只改变 Hook group 顺序时可自动恢复，不要求用户重复信任同一内容。
- ✅ 真实内容变化仍由 Codex `/hooks` 和用户决定，TRANFU 不扩大信任边界。
- ✅ 已安装且仍有 Hook 入口的用户升级后可自动获得守护。
- ✅ 守护失败不影响宿主 agent，Codex 私有 API 变化时安全降级。
- ⚠️ 依赖 Codex 0.144 系列已验证但未承诺稳定的 app-server `hooks/list`；字段变化需更新 shim。
- ⚠️ 升级前已经完全失去 Hook 执行入口的机器无法靠自更新自举，需重跑安装器一次。
- ⚠️ 本决策不解决服务不可达时 `Stop` Hook 的网络超时；传输可靠性另案处理。
