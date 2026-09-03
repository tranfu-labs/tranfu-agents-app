# 设计：fix-scheduled-tfs-node-path

## 方案

`_exec()` 增加可选 `env` 参数,缺省仍复制当前进程环境。新增:

```python
def _tfs_env(tfs_bin):
    env = dict(os.environ)
    env["PATH"] = str(Path(tfs_bin).parent) + os.pathsep + env.get("PATH", "")
    return env

def _tfs_exec(tfs_bin, args, timeout=COMMAND_TIMEOUT):
    return _exec([tfs_bin] + list(args), timeout=timeout, env=_tfs_env(tfs_bin))
```

`_resolve_tfs()`、`_inventory()`、`run_update()` 不再直接 `_exec([tfs_bin, ...])`,统一调用 `_tfs_exec()`。

## 边界

- 只补 tfs 所在 bin 目录,不执行用户 shell 文件。
- 不在 LaunchAgent plist 硬编码 NVM 版本路径;runner 每次仍按现有候选规则重新发现 tfs。
- 不判断 node manager 类型。NVM/Homebrew/asdf/Volta 只要 node 与 tfs 的入口位于同一 bin 目录即可。
- 找到 tfs 但仍无法启动时沿用现有 `tfs_not_found` / `inventory_failed` / `update_failed` 状态。

## 验证

- 构造临时 bin,其中 tfs 使用 `#!/usr/bin/env node`,node 是同目录可执行代理。
- 把测试进程 PATH 缩为 `/usr/bin:/bin:/usr/sbin:/sbin`,确保没有临时 bin。
- `run_update(force=True)` 仍能依次完成 version、installed 和 update,证明专用 PATH 覆盖三个入口。
- 现有 fake subprocess、备份、调度与回滚测试继续通过。
