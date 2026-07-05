# 提案：isolate-skills-route-state

## 背景
M3 T9 暴露了公开 SKILLS 看板的全局缺陷：两个独立浏览器会话同时访问 `/skills` 时，一个访客的筛选、下钻或 `sel` 选择会改写另一个已在线访客的 URL 与当前视图。

产品消歧后，本 issue 的目标不是新增协作浏览，而是把「实时数据刷新」和「本地导航意图」彻底隔离。公开访客视图默认完全隔离；URL 仍可复制分享，但只有主动打开该链接的浏览器会话才应用其中的 route/search state。

## 提案
- 将 SKILLS 路由组的 route/search/view state 定义为当前浏览器会话内导航状态。
- SKILLS 查询状态只从当前 `location.search` 派生，并只写当前 window 的 React Router search params。
- 数据刷新层只允许更新 payload/loading/error，不得驱动 `window.history`、React Router navigation、search params 或 `sel`。
- 不使用 `localStorage`、`sessionStorage`、服务端状态、BroadcastChannel 或 storage event 保存/广播业务 route/search/view state。
- 保留现有可分享 URL 语义：刷新、前进后退、复制链接仍按当前 URL 工作。

## 影响
- 受影响模块：M2 `frontend/`，重点是 SKILLS 路由组、URL query hook、SKILLS 数据 hooks 与前端边界测试。
- 不改变服务端 API、统计口径、SQLite schema、shim 协议或实时 state payload。
- 不新增协作浏览能力；未来若做，必须另起显式协作会话设计，包含 room/session/scope 与加入动作。

## 正式验收语句
1. 两个独立 browser context 访问 `/skills?w=7d&view=skill`，A 修改 `w/q/rt/src/view` 中至少两类筛选并打开/关闭 `sel` 后，B 的 URL、history、当前视图、筛选控件值和选中项保持原样。
2. 源码边界测试证明公开访客视图没有默认启用的业务 route/search/view 跨会话同步：除主题 `tf-theme-mode` 与 `/admin` 管理钥匙例外外，不从 storage 恢复业务路由；SKILLS route state 不使用 BroadcastChannel/storage event/server state；数据 hooks 不写 navigation/history/search params。
3. 两个独立 browser context 回放 `/skills` 在线场景：A 逐步点 evidence、进 `/skills/evidence`、进 `/skills/clues/:kind`、进 `/skill/:name`、进 `/operator/:name`、返回并刷新；每一步后 B 的 URL、route、history length、控件值和选中项保持原样，只允许数据 payload 正常刷新。
4. 在 B context 预置任意业务 route/search/view 相关 `localStorage` 与 `sessionStorage` key，保留 `tf-theme-mode` 例外；打开 `/skills?w=7d&view=skill` 后 2 秒内 B URL、筛选控件和选中项不得被 storage 残留改写。
5. B 的 `/api/state/stream` 分别模拟连接失败、永久不首包、延迟 5 秒后返回 state event；A 同时筛选和下钻；B 在 6 秒内保持原 URL、route、history、筛选控件和选中项。
6. B 的 `/api/skills` 或 `/api/skills/evidence` 响应延迟超过一个刷新周期；延迟期间 A 连续进入 `/skills/evidence`、`/skills/clues/untracked`、`/skill/:name`、`/operator/:name`；B 响应落地后仍保持原 URL 和当前视图。
7. 两个 context 同时在线，A 进入 `/skills/new` 再返回 `/skills`；B 的 URL、当前视图、history 和筛选控件保持原样。
8. A 改筛选并打开 `sel` 后，B 主动 reload 自己的原 URL；B reload 后只应用自己的 URL search，不得出现 A 的筛选、`sel` 或下钻 route。
