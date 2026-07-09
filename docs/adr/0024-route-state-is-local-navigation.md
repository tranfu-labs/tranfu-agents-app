# ADR-0024 Route state is local navigation, realtime data is payload-only

- 状态:Accepted
- 关联:ADR-0019、ADR-0023、specs/board、openspec/changes/isolate-skills-route-state

## 背景
公开 SKILLS 看板需要同时支持实时数据刷新和可分享 URL。M3 T9 缺陷说明这两个概念必须隔离：一个访客筛选、下钻或选择 `sel` 时，不得改写其它已在线访客的 URL、history、当前视图或筛选控件。

## 决策
- 公共 SPA 的业务 route/search/view state 是浏览器会话本地导航状态。
- SKILLS 路由组的 search params 只从当前 URL 读取，只写当前 window 的 React Router search params。
- SSE、polling、SKILLS revalidate 与详情 API hooks 只更新数据 payload、loading 与 error 状态，不得写 navigation/history/search params。
- 不使用 `localStorage`、`sessionStorage`、BroadcastChannel、storage event 或服务端状态保存、恢复、广播业务路由状态。
- 显式主题偏好 `tf-theme-mode` 和 `/admin` 管理钥匙例外仍按 ADR-0023 与 board spec 限定执行。

## 后果
- ✅ 两个独立访客可以同时查看 `/skills`，互不劫持 URL 或视图。
- ✅ URL 刷新、复制分享、前进后退仍由浏览器原生导航语义承担。
- ✅ 实时数据刷新路径可以独立优化，不会成为导航广播通道。
- ⚠️ 若未来要做协作浏览，必须另起显式 room/session/scope 设计，不得复用公开访客默认通道。
