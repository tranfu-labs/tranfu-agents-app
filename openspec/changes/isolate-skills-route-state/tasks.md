# 任务：isolate-skills-route-state

- [x] 采访/消歧：确认“在线客户端”为两个独立浏览器访客；默认不保留共享状态；范围限 SKILLS 路由组。
- [x] 回写 QA 增补 1-5 到正式验收语句。
- [x] 补齐 spec delta，明确实时数据刷新不得驱动本地导航。
- [x] 实现 `useSkillQueryState` 为 React Router search params 本地绑定。
- [x] 移除 `NuqsAdapter` 与 `nuqs` 依赖。
- [x] 关闭抽屉时清理当前会话自己的 `sel`。
- [x] 补充源码级边界测试：storage 例外、无同步通道、数据 hooks 不写导航、query patch 规则。
- [x] 同步 ADR / module-map / AGENTS 边界说明。
- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 运行两独立 browser context 验收，记录 JSON 与截图。
- [x] 运行 `git diff --check`。
