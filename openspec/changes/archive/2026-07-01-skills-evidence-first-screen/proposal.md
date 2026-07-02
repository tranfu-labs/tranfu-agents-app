# 变更提案：skills-evidence-first-screen

- 状态：Proposed
- 关联：
  - Issue 时间线：`#0..#5` 对 `/skills` 14 寸首屏的产品审查
  - 事实源：`openspec/specs/board/spec.md`
  - 线框基线：`docs/wireframes/pages/skills.md`、`docs/wireframes/flow.md`

## 背景 / 问题

当前 `/skills` 首屏已经具备控制条、8 格 KPI、治理健康条、排行、趋势和治理待办，信息密度够，但语义偏「KPI dashboard」。它把团队 Skill 生态包装成分数、百分比和健康状态，用户第一眼看到的是被考核的指标，而不是下一步该处理的线索。

产品审查结论已经明确：

1. 首屏应该像 operator console，不像治理报表。
2. `有使用但未收录` 是最高行动价值线索，应比综合指标更靠前。
3. 能看到问题的位置必须立刻有「下一步动作 + 详细证据」。
4. 聚合数不能只显示 `N 个` 或百分比；必须能追到名单和原始记录。
5. `总触发次数` 不能只是一个数字，应能进入当前时间范围下的证据页，看这批触发到底是什么。
6. 本次排除顶部导航的 `+N 新增 SKILL` 供给侧入口。

## 目标

- **降 KPI 语气**：把 `KPI 环带`、`治理健康`、`良好/偏高/需关注` 改成变化、线索、证据和下一步动作。
- **证据优先**：每个首屏聚合数字都能进入继承当前时间窗和筛选条件的证据页。
- **原始记录可追**：证据页展示当前窗口内的会话 x skill used 记录，并提供 skill/operator/runtime/source 分组。
- **待办有动作**：问题线索行直接展示 `看证据`、`找使用者`、`忽略本页` 等非破坏动作。
- **未收录前移**：按 Skill 视角中，`有使用但未收录` 是首屏右侧待处理线索第一组，并露出 Top names。

## 非目标

- 不改采集协议、shim、自更新或 `skill_uses` schema。
- 不把 `equipped` 混入 used 统计；证据页默认只服务 `/skills` 总览 used 口径。
- 不实现公司库写入、永久忽略、分派任务或通知 IM；本轮只做下一步入口和证据呈现。
- 不处理顶部导航的 `+N 新增 SKILL`。
- 不重做 `/skill/:name` 和 `/operator/:name` 详情页的信息架构。

## 方案概述

1. 后端新增 `GET /api/skills/evidence`：
   - 复用 `/api/skills` 的 `w/wstart/wend/days` 时间窗解析。
   - 支持 `kind=total|untracked|coverage|operators|avg_per_session|idle|unused_ratio|top3|runtime|source`。
   - 支持 `q/rt/src/skill/operator/limit/offset` 筛选。
   - 返回 `window/today/summary/top_skills/top_operators/daily/records/items/actions`。

2. 前端新增 `/skills/evidence` 路由：
   - 从首屏卡片、待处理线索、排行、Donut 进入时保留当前 query。
   - 页面包括返回 SKILLS、摘要、下一步动作、分组证据和记录表。
   - `idle` / `unused_ratio` 这类无窗口内触发记录的证据展示名单和最近历史使用，不伪造成触发记录。

3. 首屏组件改语义：
   - `KpiStrip` 改为「过去 W 变化 / 证据入口」，每格显示 Top names 或证据按钮。
   - `HealthBar` 改为「问题线索」，移除 `良好/偏高/需关注` 文案，只呈现线索和可追证据。
   - `GovernanceTodo` 改为「待处理线索」，未收录组前移，行内显示动作按钮。

## 影响

- **后端**：`server/routes/board.py` 新增只读 evidence payload helper 和路由；不引入新依赖，不触碰 DB schema。
- **前端**：新增 Evidence view、API hook 和类型；修改 `/skills` 首屏组件文案、链接和待办动作。
- **事实源**：更新 `openspec/specs/board/spec.md` 的 API、SKILLS 首屏与可验证行为；更新 wireframes。
- **测试**：新增 `/api/skills/evidence` 口径测试；新增前端链接/文案测试；运行前后端构建验证。
