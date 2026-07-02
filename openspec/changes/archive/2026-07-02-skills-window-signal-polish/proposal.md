# 变更提案:skills-window-signal-polish(SKILLS 时间窗与线索呈现打磨)

- 状态:Proposed
- 关联:skills-stats-page、skills-operator-view、skills-view-ux-polish

## 背景 / 问题
SKILLS 总览页已经具备时间窗、按人视角、证据页和问题线索,但当前实现还有几处会让运营判断偏移:

1. **操作员排行没有真正跟随观察窗口**:后端 `operator_table` 固定按 30 天排序,前端切到 `last_week`、`30d` 或 `90d` 后,排行仍可能由 30 天历史决定。
2. **`过去 W 变化` 与 `W` 文案太工程化**:页面直接露出 W,没有用当前时间窗的中英文 label,例如用户选择 `last_week` 时应该看到「上周变化」而不是「过去 W 变化」。
3. **问题线索露出具体 skill 例子**:首屏线索卡出现 `figma-implement-d...` 这类长名字,会把判断焦点从"哪里断了"带到个别样例;具体名单应留给证据页。
4. **环比开关没有产品意义**:环比是默认分析上下文,不需要给用户一个关闭入口;无 previous-window 数据时走空态即可。
5. **证据跳转图标垂直不稳**:问题线索里的跳转 icon 视觉上偏上,不像同一行内的操作按钮。

## 目标
- 操作员排行按当前观察范围排序和呈现:继承 `w/days`,以及定义证据范围的 `runtime/source`;不继承 skill 搜索词、Top N、隐藏 0 使用等列表局部控制。
- 所有首屏 `W` 展示改为当前时间窗 i18n label 派生,如「上周变化 / 本周变化 / 近 7 天变化」和 `Last week changes / Last 7 days changes`。
- 问题线索卡只给可行动结论和证据入口,不在首屏露具体 skill 名;证据页继续保留明细名单。
- 删除环比开关;previous-window 变化默认一直展示,没有 previous 数据时沿用空态。
- 证据 icon 在 KPI 卡、问题线索、排行行里保持视觉居中。
- 问题线索保持"哪里断了、下一步看哪份名单"的语气,不变成 KPI 评分、红绿箭头、达成率或庆祝式增长。

## 非目标
- 不改变 `skill_uses` 写入、去重、used/equipped 口径。
- 不把 skill 搜索词、Top N、隐藏 0 使用变成全局证据范围。
- 不重做证据页信息架构;证据页仍展示 records / items 明细。
- 不新增外部依赖或运行期前端服务。

## 方案概述
- `server/routes/board.py`:让 `/api/skills` 的 operator 聚合接收 `rt/src`,补 `operator_table.sessions_window` / `previous_sessions`,默认按 `sessions_window` 排序;skill 聚合仍沿用现有前端本地筛选。
- `frontend/src/views/Skills.tsx` + `skillsWindowQuery`:移除环比开关;overview 请求只带 `w/days` 与 `rt/src`;操作员视角切换时清理 skill 搜索串;OperatorTable 改用窗口内列排序/展示。
- `frontend/src/lib/skillsPresentation.ts` 与 i18n:新增时间窗标题/句内 label helper,替换首屏 `W` 文案。
- `frontend/src/components/skills/KpiStrip.tsx`:默认展示环比,删除 `showComparison` 分支;标题用当前时间窗变化 label。
- `frontend/src/components/skills/HealthBar.tsx`:问题线索改成结论型文案,去掉首屏具体 skill 名;视觉状态改为中性信号。
- `frontend/src/styles.css`:修正 `.evidence-icon-link` 在健康线索和排行行内的对齐。
- `docs/wireframes/pages/skills.md` 在后续事实源回流时吸收本次 `wireframes.md` 的变化。

## 影响
- 行为事实源:更新 `openspec/specs/board/spec.md` 的 SKILLS 总览规则。
- 版式事实源:更新 `/skills` wireframe 中控制条、时间窗变化、问题线索、操作员排行口径。
- 测试:后端聚合新增 TestClient 覆盖;前端新增/更新 node:test 单元测试;人工/AI 验证覆盖桌面与手机 `/skills`。
