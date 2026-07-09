# board spec delta：isolate-skills-route-state

## 新增规则
- SKILLS 路由组的 route/search/view state 是当前浏览器会话内的导航状态。`/skills`、`/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/skill/:name` 与 `/operator/:name` 的 URL、history、筛选控件值、视角和 `sel` 只允许被当前 window 的用户导航或主动打开的 URL 改变。
- 实时数据层只负责刷新 payload。`/api/state/stream`、`/api/state`、`/api/skills`、`/api/skills/evidence`、`/api/skill/{name}` 与 `/api/operator/{name}` 的成功、失败、延迟、重连或 revalidate 结果不得驱动 `window.history`、React Router navigation、search params 或 `sel`。
- 公开访客视图默认不得启用业务 route/search/view 跨会话同步。不得用 `localStorage`、`sessionStorage`、storage event、BroadcastChannel、服务端状态或实时 state payload 保存、恢复或广播 SKILLS 业务导航状态。
- URL 仍是可分享事实源。复制 `/skills?...`、`/skills/evidence?...`、`/skills/clues/:kind?...`、`/skill/:name?...` 或 `/operator/:name?...` 后，只有主动打开该链接的浏览器会话应用其中的 search params；已在线的其它访客不得被改写。
- 未来若新增协作浏览或共享状态能力，必须作为显式协作会话设计，至少包含可识别的 session/room/scope 与显式加入动作；不得默认作用于公开访客视图。

## 不变规则
- SKILLS search params、刷新、前进后退、复制链接和详情 push/筛选 replace 语义保持不变。
- 主题模式仍是唯一普通看板 localStorage 例外，key 为 `tf-theme-mode`；`/admin` 管理钥匙仍只允许使用本会话 sessionStorage。
- 本变更不改变服务端统计口径、SKILLS payload 结构、SSE payload 结构、shim 协议或 SQLite schema。
