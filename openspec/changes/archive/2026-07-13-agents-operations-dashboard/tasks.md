# 任务：agents-operations-dashboard

- [x] 1. `server/routes/board.py` 在现有 `_snapshot` 后增加 `agent_overview` 聚合：90 天日序列、摘要、Runtime/操作员排行和 Shim 计数；补充服务端契约测试。
- [x] 2. `frontend/src/lib/types.ts` 增加 Agents overview 类型与 Agent `last_seen` 字段；新增 `agentsDashboard.ts` 纯逻辑与单元测试，并登记到前端测试入口。
- [x] 3. 新增 Agents 趋势/排行组件，重做 `frontend/src/views/Agents.tsx` 的控制条、摘要、问题线索、分析区和 Agent 卡片；保持 `/agent/:key` 下钻。
- [x] 4. 补齐中英文 i18n 文案、Agents 专用 CSS、桌面/平板/手机布局和键盘可达状态。
- [x] 5. 更新 `docs/wireframes/pages/agents.md`、本 change 的 `wireframes.md` 与 board spec delta，记录新 state 契约和页面规则。
- [x] 6. 运行 Python 编译/pytest/coverage、前端 unit/build；启动本地服务用 TestClient 与浏览器走查真实数据、空态、筛选、主题和窄屏。
