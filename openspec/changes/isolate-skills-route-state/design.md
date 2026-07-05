# 设计：isolate-skills-route-state

## 目标边界
本变更只修 SKILLS 路由组的默认访客隔离，不做全站协作浏览、不改统计 API、不改实时数据协议。

SKILLS 路由组包括：

- `/skills`
- `/skills/new`
- `/skills/evidence`
- `/skills/clues/:kind`
- `/skill/:name`
- `/operator/:name`

## 实现方案
1. 用项目内 `useSkillQueryState` 封装 React Router `useSearchParams`。
   - 读取：每次 render 从当前 `location.search` 解析为 typed query state。
   - 写入：patch 当前 `URLSearchParams`，用 `setSearchParams(next, { replace: true })` 写当前 window。
   - 默认值仅存在于内存解析结果；写入空字符串或默认无效值时删除对应 query key。
2. 移除 `NuqsAdapter` 和 `nuqs` 依赖。
   - 本项目不需要 URL query 外的状态同步能力。
   - 这样可以直接通过源码边界测试证明 SKILLS route state 没有 BroadcastChannel/storage/server-state 隐式通道。
3. 保持下钻语义。
   - 筛选变化继续使用 replace，不污染 history。
   - 详情跳转继续由 React Router `Link`/`navigate` push 目标 route。
   - `sel` 打开/关闭只写当前 URL search；关闭抽屉同步清理当前会话自己的 `sel`。
4. 数据 hooks 边界。
   - `usePollingState`、`useSkillsOverview`、`useSkillsEvidence`、`useSkillDetail`、`useOperatorDetail` 只更新 data/loading/error/demo。
   - SSE 失败、挂起、延迟 state event 与 SKILLS API revalidate 均不得调用 navigate/history/search writer。
5. 测试策略。
   - 单元/源码边界测试覆盖 storage 残留、同步通道、数据 hook 写导航禁用、query patch 清理规则。
   - Playwright 两 context smoke 覆盖 A 操作不影响 B，以及 reload/延迟 API/SSE 场景。

## 权衡
- 直接使用 React Router search params 比继续包装第三方 query-state 库更窄，减少隐式同步通道排查面。
- 当前 hook 只支持本项目用到的 object patch，不实现函数式 updater；如果未来需要更复杂批量更新，先补测试再扩展。
- 不新增前端持久化，也不把 route state 送服务端保存；复制链接的分享能力由 URL 本身提供。

## 风险与缓解
- 风险：删除 query 默认值序列化后 URL 比以前更短。
  缓解：解析层保留默认值，刷新和复制链接语义不变；需要显式分享时，当前 URL 中已有用户改过的参数。
- 风险：详情页读取 `win` 的兼容逻辑仍需工作。
  缓解：`useSkillQueryState` 保留 `win` number 解析和无效值 fallback。
