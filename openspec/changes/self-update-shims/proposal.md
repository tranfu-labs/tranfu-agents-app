# 变更提案:self-update-shims(shim 自更新与版本可见)

- 状态:Proposed
- 关联:specs/ingest、specs/board、specs/onboarding、ADR-0005、ADR-0007、ADR-0009

## 背景 / 问题
本项目的本地 hook 每次触发都会重新启动 `python3 ~/.tranfu/tf_hook.py`。这意味着 shim 文件本身是
"每次调用现读"的,只要安全替换 `~/.tranfu/` 下文件,下一次 hook 就会自动使用新代码。

当前升级仍依赖队友手动重跑 `install.sh`;一旦新增采集逻辑或修复 shim bug,线上会长期混杂多代本地 shim,
看板也无法直接判断谁还停在旧版。

## 目标
- 服务端提供 `/shims/manifest`,返回 shim 文件清单、安装目标路径、sha256 与内容版本。
- `install.sh` 按 manifest 全量安装 shim,成功后写入本地 `~/.tranfu/manifest.json` 作为版本基线。
- hook 在会话开始时后台静默触发自更新;更新失败不得阻塞或破坏宿主 agent。
- profile 上报 `shim_version`;看板显示当前版本,并标记落后于服务端 manifest 的 agent。

## 非目标
- 不做远程执行任意命令;只允许下载服务端 manifest 中声明的 `shims/` 文件。
- 不改变已有 hook 接线命令形态,也不主动改用户身份 env。
- 不让 OpenClaw 常驻进程热加载 JS;文件可刷新,但生效仍需重启 OpenClaw。

## 影响
- specs/onboarding:新增 `/shims/manifest` 与自更新安装/触发规则。
- specs/ingest:profile 可选字段新增 `shim_version`。
- specs/board:`/api/state` 暴露服务端当前 shim 版本,看板可标记过期客户端。
