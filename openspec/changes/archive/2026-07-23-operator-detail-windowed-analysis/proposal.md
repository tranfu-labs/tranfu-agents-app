# 提案：operator-detail-windowed-analysis

## 背景

SKILLS 总览按人视角已经允许选择 `today`、预设窗口或自定义窗口，并可用 runtime、来源限定观察范围；操作员排行也按这组条件计算。但点击操作员后，当前 `/operator/:name` 虽然把总览的整串 query 带进 URL，详情请求仍固定调用无参数的 `/api/operator/{name}`，页面继续展示固定 30 天趋势与 7/30/累计排行。

这造成两个直接问题：

- 用户从“今天”的操作员排行下钻后，看到的并不是今天的个人统计，上下文断裂。
- 单日趋势退化为一根柱，而全量 Skill 排行又把历史所有 Skill 铺开，主分析区既不适合概览，也容易变得过长。

## 提案

- 操作员详情只继承会改变个人统计事实范围的 `w/wstart/wend/rt/src`；搜索词、Skill Top N、隐藏零使用、选中 Skill 等总览展示条件不进入个人统计。
- 额外保存一份只用于返回 `/skills?view=operator...` 的来源 query，使显式返回可以恢复总览原有视角和筛选，同时不污染详情统计。
- 以新增 `analysis` 子对象扩展 `/api/operator/{name}`，按所选窗口、runtime 和来源返回统一口径的摘要、上期对比、日序列、Skill 明细、runtime 分布和最近记录；现有顶层 `metrics/daily/skills/runtime/records` 保持原语义，避免无参数调用方被静默改成 7 天。
- 单统计日使用“Skill 使用构成”环形图（Top 5 + 其他）与紧凑 Top 5 排行；多日窗口使用“每日使用 · 按 Skill”趋势（Top 8 + 其他）与紧凑 Top 8 排行。
- 把当前窗口内的完整 Skill 清单放在主分析区下方，继续支持整行下钻；runtime 分布和最近记录保留，但全部服从当前观察范围。
- 同步操作员详情字符线框和 SKILLS 下钻/返回流转设计，并补充查询状态、聚合口径、单日/多日模式和响应式验收。

## 影响

- 服务端：`server/routes/board.py` 的操作员详情聚合与路由 query 契约。
- 前端：`frontend/src/App.tsx`、`frontend/src/views/Skills.tsx`、`frontend/src/views/OperatorDetail.tsx`、API/type/query 纯模块、图表/排行组件、i18n 与样式。
- 测试：服务端 API 聚合测试、前端纯查询/展示模型单测，以及桌面/平板/手机浏览器验证。
- 事实源：`openspec/specs/board/spec.md`、`docs/wireframes/pages/operator-detail.md`、`docs/wireframes/flow.md` 和根 `AGENTS.md` 中的操作员详情约束。
- 不改变事件协议、`skill_uses` 去重粒度、数据库结构、Skill 详情口径、总览 Top N 控件或公司库漏斗。
