# 提案：agents-duration-by-agent-dashboard

## 背景

Agents 列表页当前把顶部观察视角定义为“操作员｜运行终端”，排行和趋势也跟随该视角分组；趋势又允许在“活跃 Agent｜活跃时长”之间切换。这个模型把查看者带向人员或运行环境分析，偏离了页面本身要回答的核心问题：团队全部 Agent 在所选时间窗里分别运行了多久、合计运行了多久。

操作员与运行终端同时出现在控制条筛选和列表明细，进一步增加了非 Agent 维度的视觉重量。用户已确认本页不再保留这些观察、筛选和列表字段，只以全部 Agent 为统计集合、以运行时长为唯一主指标，并保留单日环形扇形图。

## 提案

- 移除 Agents 控制条中的“操作员｜运行终端”切换、操作员筛选与运行终端筛选，以静态口径“全部 Agent · 按运行时长”说明当前统计对象和指标。
- 排行固定为 Agent 运行时长排行，按当前窗口 `active_seconds` 降序；点击排行行进入对应 Agent 详情。
- 趋势固定为运行时长：单日正值显示按 Agent 分区的环形扇形图，中心显示全部 Agent 总运行时长；多日显示按 Agent 分段的逐日堆叠柱。
- 保留 Top 8 + 其他、tooltip、主题、响应式、键盘 roving focus、短窗铺满和长窗图内横滚规则。
- Agent 明细删除操作员与运行终端列，默认按窗口运行时长排序；搜索不再匹配已从列表页移除的两个字段。
- 八卡把主指标前置，并以“平均运行时长”替换“操作员数”：窗口总时长、平均时长/活跃 Agent、活跃 Agent、Agent 总数、当前在线、本周时长、运行质量、待处理 Agent。
- 旧 `rank`、`rt`、`op` 查询参数作为兼容输入被忽略，并在页面 URL 规范化时移除；其它筛选、时间窗和排序参数继续可复制、刷新与前进后退恢复。

## 影响

- 影响 `frontend/src/views/Agents.tsx`、Agents 组件、`frontend/src/lib/agentsDashboard.ts`、中英文文案、样式与前端单元测试。
- 更新 `openspec/specs/board/spec.md`、`docs/wireframes/pages/agents.md`、`docs/architecture/module-map.md` 与根 `AGENTS.md` 的 Agents 事实描述。
- 不改变 `/api/state`、`agent_overview` 服务端结构、SQLite、事件协议、身份合并规则、Agent 详情页或采集 shim。
