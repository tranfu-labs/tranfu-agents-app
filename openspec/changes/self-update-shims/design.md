# 设计:self-update-shims

## 服务端 manifest
- `server/app.py` 启动时扫描 `shims/` 常规文件,计算每个文件 sha256,并对排序后的文件哈希再次 sha256 得到整体 `version`。
- manifest 条目包含:
  - `path`:服务端 `/shims/{path}` 下载路径;
  - `target`:安装到 `~/.tranfu/` 下的相对路径;
  - `sha256`、`size`、`executable`。
- `wrapper/*` 保持安装器现状拍平到 `~/.tranfu/<basename>`;`openclaw/*` 保持在 `~/.tranfu/openclaw/`。

## 安装器基线
- `install.sh` 优先读取 manifest,按每个条目的 `path -> target` 全量下载目标文件,校验 sha256 后落到
  `~/.tranfu/`。
- 只有全量安装成功才写入 `~/.tranfu/manifest.json`;若 manifest 下载或任一文件校验失败,不得写入假的
  本地版本基线。

## 客户端自更新器
- 新增 `shims/tf_selfupdate.py`,仅用 Python 标准库。
- `TF_AUTO_UPDATE=0` 时立即退出;没有 `TF_SERVER` 时退出。
- 用 `~/.tranfu/.update.lock` 做互斥,避免多个 SessionStart 并发更新;用 `~/.tranfu/.selfupdate.json`
  记录 `last_check`,默认 1 小时节流。
- 拉取 `/shims/manifest`;若版本与 `~/.tranfu/manifest.json` 一致且所有目标文件存在、哈希一致,则退出。
- 若版本一致但目标文件缺失或哈希不符,仍按 manifest 下载并修复这些文件。
- 对缺失或哈希不同的文件下载到 `~/.tranfu/.staging/`,逐个校验 sha256;`.py` 文件先跑 `py_compile`。
- 全部通过后才逐个 `os.replace` 到正式路径,按 manifest 设置权限,最后原子写入新 manifest。
- 任何失败都清理 staging、保留旧文件、静默退出。
- 更新成功后调用 `tf_report.py --status running --step "shim 已自动更新到 <version>"`,留一条看板事件。

## hook 触发点
- `tf_hook.py` 仅在 `SessionStart` / `on_session_start` 时用 detached 子进程启动 `tf_selfupdate.py`。
- hook 主流程仍继续调用 `tf_report.py --profile` 并立即返回;自更新不参与 hook 成败。

## 版本可见
- `tf_profile.py` 从本地 `manifest.json` 读取 `shim_version` 并随 profile 上报。
- 服务端把 `shim_version` 存进 profile;`/api/state` 返回 `shim.version` 作为当前服务端版本。
- 前端在卡片与详情里显示版本短码;若 `session.shim_version !== state.shim.version`,显示过期角标。

## Runtime 生效时机
- Claude Code / Codex / Hermes:文件替换后下一次 hook 触发即生效。
- OpenClaw:文件可更新到 `~/.tranfu/openclaw/`,但常驻插件需重启 OpenClaw 才加载新 JS。
