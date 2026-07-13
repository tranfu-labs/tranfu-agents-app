# 变更提案：agents-operations-dashboard（Agents 运营看板）

- 状态：Proposed
- 范围：board 域，覆盖 `/api/state` 与 `/agents`

## 背景

当前 `/agents` 只渲染一张宽表，能看到单个身份的基本字段，却难以回答“现在谁在运行”“哪些 Agent 需要治理”“不同 Runtime/操作员的活跃情况如何”等问题。SKILLS 页面已经形成了控制条、摘要、趋势、排行、问题线索和明细的证据型信息架构，Agents 页面需要达到同样的运营密度。

## 目标

- 保留按 `operator + agent||runtime` 合并的身份卡片与 `/agent/:key` 详情下钻。
- 增加 URL 筛选、排序、总览摘要、90 天活跃趋势、Runtime/操作员排行和问题线索。
- 通过 `/api/state` 顶层可选 `agent_overview` 提供服务端真实聚合，不新建实时轮询源。
- 在桌面、平板、手机上保持可读、可键盘操作、可切换中英文与主题。

## 非目标

- 不改变事件协议、身份合并、心跳写入、Shim 三态判定或 Agent 详情数据口径。
- 不引入新的数据库、缓存中间件、独立前端服务或浏览器持久化状态。
- 不把 prompt、代码、输出或 token/成本信息加入 Agents 统计。

## 预期影响

`/api/state` 保持现有字段兼容，仅增加 `agent_overview`；`/agents` 从表格升级为运营看板，Agents 线框与 board spec 同步更新。
