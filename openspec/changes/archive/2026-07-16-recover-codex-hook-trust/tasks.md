# 任务：recover-codex-hook-trust

- [x] 实现 `tf_codex_hook_guard.py` 的 app-server 客户端、信任状态解析与严格纯排列判定。
- [x] 实现备份、原子重排、写后复查、失败回滚、状态 fingerprint 与 macOS 去重通知。
- [x] 实现 LaunchAgent 幂等安装、状态与卸载。
- [x] 把守护接入 `tf_hooks.py` 的 Codex install/uninstall 和 `tf_selfupdate.py` 的升级自举。
- [x] 把新 shim 加入 manifest/fallback 安装并更新接入文档、模块地图、ADR 与 AGENTS.md。
- [x] 增加纯换序、拒绝条件、回滚、通知、LaunchAgent、自更新与安装生命周期单元测试。
- [x] 运行 py_compile、shim 定向测试、全量 pytest、覆盖率与本机只读 AI 验证。
- [x] 对照本 change 反思实现，修正偏差后归档并合并 spec-delta。
