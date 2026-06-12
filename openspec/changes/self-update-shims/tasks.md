# tasks:self-update-shims

- [x] 1. `server/app.py`:新增 `/shims/manifest`,profile 接收 `shim_version`,`/api/state` 返回当前 shim 版本。
- [x] 2. `shims/tf_selfupdate.py`:实现 manifest 拉取、节流、文件锁、staging 校验、原子替换、成功事件。
- [x] 3. `shims/tf_hook.py` / `shims/tf_profile.py` / `install.sh`:接入后台触发、版本采集、安装基线。
- [x] 4. `dashboard/index.html`:卡片、列表或详情显示 shim 版本,旧版标记过期。
- [x] 5. 测试:服务端 manifest/目录穿越、profile 版本、hook 触发、自更新无变更/正常更新/坏包/节流/开关。
- [x] 6. 文档/spec:同步 PROTOCOL、QUICKSTART、USAGE、UPDATE、SKILL、module-map 与 specs。
