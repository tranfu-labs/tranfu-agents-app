# 设计:fix-skills-daily-window

## 方案
1. 在前端展示层把趋势卡标题改成窗口派生文案:
   - Skill 视角:`windowUsedLabel(windowKey, t)`,例如「近 7 天使用」/ `Used in Last 7 days`。
   - Operator 视角:在同一窗口标题后追加现有按人语义,例如「近 7 天使用 · 按人」/ `Used in Last 7 days · by operator`。
   - `SectionTitle` 与 `StackedSkillChart` 的 `aria-label` 共用该标题。
2. 在图表轴生成层新增 date-only 窗口 helper:
   - 输入 `start` 与 `end` ISO 日,输出闭区间日期序列。
   - 非法边界、end < start 或超出合理上限时返回空数组,由调用方回退到旧 `daySeries(axisEnd, days)`。
3. `StackedSkillChart` 优先从 `overview.window.start..end` 生成轴:
   - 服务端已经保证 `daily` / `operator_daily` 按当前窗口聚合,前端轴也必须对齐同一窗口。
   - 今日进行中标记仍只在 `overview.today` 落入轴内时出现;切到 `last_week` 时不会误标今天。
4. 单元测试覆盖:
   - `isoDayRange('2026-07-01','2026-07-07')` 产出 7 天闭区间。
   - `resolveSkillsChartAxis()` 在有 payload window 时忽略 fallback `days`。
   - 趋势标题中英文随窗口变化。

## 权衡
- 不在后端补零行:后端 payload 已提供窗口边界,前端生成空槽更轻,也避免放大响应体。
- 不引入新图表库:现有 SVG 图表已经满足需求,只需修正轴事实源。
- 不重做 loading 行为:同 URL revalidate 与刷新过渡态已有约束,这次只修复趋势卡窗口绑定和标题语义。

## 风险
- 若旧 payload 缺失 `window.start` 或 `window.end`,图表会回退到原 `daySeries(axisEnd, days)` 路径,保持兼容。
- 如果窗口范围异常过长,helper 返回空数组并回退,避免渲染超宽异常 SVG。
- 回滚方式:还原 `Charts.tsx` 的轴选择逻辑和 `Skills.tsx` 的标题调用即可,不涉及数据迁移。
