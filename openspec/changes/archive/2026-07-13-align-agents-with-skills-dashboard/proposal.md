# 提案：align-agents-with-skills-dashboard

## 背景

Skills 统计页已经形成相对完整的运营 dashboard 结构、信息密度和响应式节奏，作为本次对齐基线保持不变。Agents 列表虽然已经具备时间窗、稳定摘要、问题线索、排行、趋势和 Agent 明细，但实际渲染仍有明显差距：

- 当前把四张时间窗变化卡和五张稳定摘要卡拆成两个连续区块；而 Skills 的时间窗变化区域是一个统一的八卡 KPI 网格，所有核心事实使用同一种卡片语言，并在数值同行提供真实下钻入口。
- `today` 趋势只有一个统计日，却占用与长窗口相同的图表高度，形成大块空白。
- 排行、趋势和 Agent 卡片在字号、间距、条形轨道、标题层级上仍像独立页面，没有达到 Skills 主分析区的完成度。
- 手机依次铺满变化卡、摘要卡、问题线索、排行和空趋势，第一张 Agent 明细被推得过后；控制摘要以下的判断路径不够清晰。

本次变更只优化 `/agents`，以现有 `/skills` 为参照，不修改 Skills 页面、Skills 组件、Skills 数据、Skills 断点或 Skills 事实源。

## 提案

1. 把 Agents 控制区标题和当前视角说明对齐 Skills 的“控制条”结构；不再用重复的页面标题占据控制条 frame。
2. 把 Agents 的时间窗变化与稳定摘要合并成 Skills 同款单一八卡 KPI 网格：窗口活跃 Agent、窗口活跃时长使用环比；Agent 总数、操作员数、当前在线/运行中、本周活跃（detail 保留今日活跃）、运行质量、待处理 Agent 使用快照。桌面 8×1、平板 4×2、手机 2×4。每格数值同行提供真实的趋势、排行、筛选或 Agent 明细入口，不放装饰性假图标。
3. 保持问题线索独立且可点击筛选，并把它放在主分析前；桌面形成与 Skills 一致的“排行左、趋势右”近等宽节奏，统一 `//标题 + cnt` 面板头和居中 Empty。
4. 让 Agents 趋势完整对齐现有 Skills chart 的几何、空态与交互完成度：测量容器宽度、短窗铺满且限制柱宽、长窗内部横滚并定位最新日期、今日斜纹、整日命中区、自定义 tooltip、hover/focus 高亮和日期抽样。today 有数据时使用紧凑的单日 plot，不伪造小时数据；全窗为 0 时显示 Skills 同款空态，不渲染一排空轴。
5. 收紧 Agent 卡片的信息层级和间距，保留任务/步骤、今日/本周、Skill/MCP、质量、Shim、最近活跃和整卡下钻。
6. 调整 Agents 自身的平板/手机顺序与密度。手机首屏采用控制摘要 → 问题线索 → Agent 明细，八卡和分析区下沉，避免“Agents 列表”先铺满统计再让用户找 Agent；页面根不得横向滚动。
7. Agents 直接消费现有 `resolveSkillsChartLayout` 几何规则而不修改 Skills，并将八卡展示/动作模型、today/空态 chart 模型抽成纯函数补单测；通过 1440×900、768×1024、375×812 浏览器验证。
8. 实现复核后补齐四个完整性缺口：八卡标题必须与 Skills 一样由当前窗口派生为“今天变化 / 近 N 天变化”；长窗口尾部全零时初始定位最后一个非零日期；窗口切换同步重置 roving focus；custom 窗口只有完整落在可用日序列内才展示聚合值。

## 非目标

- 不修改 `/skills` 的 TSX、组件、helper、CSS 行为、演示数据、API 请求或线框图。
- Agents markup 与样式不得依赖 `.skills-*` class；只复用共享 helper 与设计 token，避免未来修改 Skills CSS 时暗改 Agents。
- 不修改全局 TopBar、顶级导航或其它路由的手机头部。
- 不修改服务端 API、SQLite、事件协议、Agent 身份合并或任何 Skill 统计口径。
- 不新增 Agent 数据字段，不伪造小时级活跃序列。

## 影响

- 前端仅影响 `frontend/src/views/Agents.tsx`、`frontend/src/components/agents/`、`frontend/src/lib/agentsDashboard.ts`、Agents 相关测试/i18n，以及 `frontend/src/styles.css` 中 Agents 专用选择器。
- 规格与版式仅影响 `openspec/specs/board/spec.md` 的 Agents requirements 和 `docs/wireframes/pages/agents.md`。
- Skills 页面只是视觉参照，最终 diff 不应包含 Skills 页面或 Skills 专用组件行为变更。
