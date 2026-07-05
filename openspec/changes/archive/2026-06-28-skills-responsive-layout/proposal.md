# 变更提案:skills-responsive-layout(SKILLS 统计域平板/手机适配)

- 状态:Proposed
- 关联:skills-stats-page / skills-operator-view / skills-view-ux-polish

## 背景 / 问题
当前前端已有基础窄屏兜底,但 SKILLS 统计域仍偏桌面表格形态:

1. `/skills` 的视角卡、筛选条、趋势图、排行表、治理 Lens 和公司库漏斗在平板/手机下没有统一的统计域响应式规则。
2. 趋势图和表格依赖横向滚动,但目标应是"组件内部可滚",不能把整页撑出横向滚动。
3. 手机上排行表仍是桌面表格压缩版,可读性差;需要转换为摘要行,把主语、来源、7d/30d/总计/最近等关键字段折行展示。
4. `/skill/:name` 与 `/operator/:name` 两个子页面的指标卡、趋势图、分布区和最近记录也需要同一套平板/手机断点规则。
5. 既有 wireframes 已覆盖页面结构,但缺少这次更细的 SKILLS 统计域响应式形态。

## 目标
- 覆盖 SKILLS 统计域三个路由:
  - `/skills`
  - `/skill/:name`
  - `/operator/:name`
- 明确三个断点:
  - 桌面:`>1080px`,尽量保持现有布局。
  - 平板:`601px-1080px`,主区域单列,表格/图表仅在组件内部横向滚动。
  - 手机:`≤600px`,筛选控件单列、排行/记录表转摘要行、统计卡压为 2 列。
- 让统计组件在平板/手机下可读:
  - 视角卡说明可见,按钮满宽/等分。
  - 筛选条单列或紧凑多列,不溢出。
  - 趋势图容器内部滚动,浮窗不溢出视口。
  - 治理 Lens 按钮和说明换行。
  - 公司库漏斗跟在排行下方。
- 子页面平板/手机适配:
  - 指标卡平板 3-4 列、手机 2 列。
  - 趋势图内部滚动。
  - 分布区在 ≤1080px 单列。
  - 最近记录手机改摘要行。

## 非目标
- 不改后端 API、SQLite schema、聚合口径或 Skill 统计规则。
- 不改 `/agents`、`/`、`/agent/:key`、`/admin` 的移动端形态。
- 不移除或重构既有 `/token-usage` 相关代码;该事项触碰项目"无 token/成本 UI"硬约束,应走独立 change。
- 不引入新 UI 库、图表库或运行期依赖。

## 影响
- 前端:`frontend/src/views/Skills.tsx`、`SkillDetail.tsx`、`OperatorDetail.tsx`、`components/Charts.tsx`、`styles.css`。
- 规格:`openspec/specs/board/spec.md` 增补 SKILLS 统计域平板/手机规则。
- 线框:`docs/wireframes/pages/skills.md`、`skill-detail.md`、`operator-detail.md` 在归档时回流本 change 的 wireframes。
- 测试:纯展示/响应式变更,不新增单元测试;用 `npm --prefix frontend run build` 和浏览器视口走查验证。
