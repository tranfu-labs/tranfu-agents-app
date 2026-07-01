# 任务：redesign-skills-page

> 归档动作（移动 change / 合并 spec-delta / 回流 wireframes）不写在这里——参见 `openspec/changes/AGENTS.md` 的「归档」节。

## 后端

- [x] `/api/skills` 补齐 `period_comparison`：本期 vs 上期同长度窗口的 sessions / operators / avg_skills_per_session / top3_share / untracked_share
- [x] `/api/skills` 补齐 `governance.idle_installed`：装机窗口内无触发的 skill 列表（含装机操作员数）
- [x] `/api/skills` 补齐 `governance.cataloged_not_installed`：收录但零装机的 skill 列表
- [x] `/api/skills` 补齐 `attribution.by_source` / `attribution.by_runtime`：按 sessions 加权的分布
- [x] 无破坏性变更：所有新字段可选返回；前端读不到时降级
- [x] 后端单测覆盖：期间对比正确、闲置定义正确、加权聚合正确（`tests/test_skills_stats_page.py` 追加用例）

## 前端 · 拆分与新组件

- [x] 抽出 `frontend/src/lib/skillsThresholds.ts`：治理健康 5 项阈值常量（design.md §三 表格搬进来）
- [x] `frontend/src/lib/skillsSelection.ts`：URL query `sel` 读写 hook（选中态贯穿源头）
- [x] `frontend/src/lib/skillsWindow.ts`：时间窗名 `w` → 起止时间戳的解析（含 `custom`、含 `win` 向下兼容 fallback）
- [x] `frontend/src/components/skills/KpiStrip.tsx`：8 格 KPI 环带；按 Skill/按人视角切换口径；每格支持 delta 或 snapshot
- [x] `frontend/src/components/skills/HealthBar.tsx`：5 项健康信号，按阈值着色；按人视角换为使用健康
- [x] `frontend/src/components/skills/RankBars.tsx`：Top N + "其他 N 个" 聚合，点击 = 设置全局 sel
- [x] `frontend/src/components/skills/GovernanceTodo.tsx`：3 组待办列表 + 当前页面会话态忽略 + 恢复（不写 localStorage,遵守 ADR-0023）
- [x] `frontend/src/components/skills/AttributionDonuts.tsx`：来源（双层 sunburst，内环 已收录/未收录 · 外环 own/meta/external/non_catalog，父子角度一致性 <0.5°）+ runtime（单层）两张 Donut；中心大字 + 未收录 X% 红线；点扇区筛选联动 `src`；选中 skill 时切到该 skill 的 runtime 分布
- [x] `frontend/src/components/skills/SkillsDetailTable.tsx`：新版明细表（W 内 / W′ / Δ% 三动态列）
- [x] `frontend/src/components/skills/SkillDrawer.tsx`：右侧抽屉，KPI4 格 + 趋势 + runtime 拆分 + 最近 5 次触发 + 「前往详情页 →」
- [x] `frontend/src/components/skills/FunnelSection.tsx`：漏斗下沉 + 默认折叠版本

## 前端 · Skills.tsx 主页面重画

- [x] 实现修正：新版直接替换原 `/skills`，不引入 `SKILLS_V2` build-time flag；回滚走提交或上一版镜像
- [x] 组合顺序（8 层）：`SkillsToolbar → KpiStrip → HealthBar → DailyStackedChart(全宽独占) → MainSplit(RankBars | GovernanceTodo) → AttributionDonuts → SkillsDetailTable(+SkillDrawer) → FunnelSection`
- [x] 扩展现有 `StackedSkillChart`：全宽独占一层；接入 `sel` 让选中 skill 段落加粗描边、其他 α=.4
- [x] 「按人」视角下：KPI 换算成人指标；治理待办换成"重度使用者 / 近 7 天沉睡 / 低覆盖使用者"；明细表切成 `OperatorTable`
- [x] URL query 新增 `w / wstart / wend / cmp / topn / hz / sel`；旧参数 `win` 向下兼容 fallback；`lens` 做 no-op 兼容
- [x] 全局选中态五组件联动（RankBars / 堆叠柱 / Donuts / 明细表 / 抽屉）
- [x] CSV 导出（当前筛选 / 全量），仿 `exportTokenRows` 模式

## 样式

- [x] `styles.css` 追加：`skills-kpi / skills-health / skills-attribution / skills-drawer / skills-governance / skills-rank-bars`
- [x] 桌面 / 平板 / 手机三档响应式，与 wireframes.md 一致
- [x] 抽屉：桌面 480px 侧滑、平板 80% 宽、手机全屏

## 验证

### 单元测试（可测逻辑）
- [x] `AttributionDonuts` 父子角度一致性：内环「已收录」角度 = 外环 own+meta+external 角度之和，误差 <0.5°；外环「未收录」= 内环「未收录」
- [x] `AttributionDonuts` 零值扇区：sessions=0 的分片不生成 path；own+meta+external 全为 0 时内环「已收录」也不画（此时应显示 Empty）
- [x] `skillsWindow.ts`：`w=today / this_week / last_week / 7d / 14d / 30d / 90d / custom` 各自解析出正确的起止 unix；`w=custom` 但 `wstart/wend` 缺失时降级到 30d
- [x] `skillsThresholds.ts`：边界值（10% / 25% / 30% / 50% / 60% / 80%）分别落入 good / warn / bad
- [x] `RankBars` 长尾聚合：Top N = 8 且总数 10 时生成 "其他 2 个"；总数 ≤ N 时不生成
- [x] KPI delta 计算：previous=0 且 current>0 → `+∞%`；两边 0 → `—`；正常 → 保留 1 位小数
- [x] URL query 往返：设置 `sel=foo` 后 URL 写入、刷新页面能读回
- [x] 治理忽略：忽略后当前页面会话内隐藏，恢复后清空

### AI 验证流程
- [x] 用 chrome-devtools MCP 或 playwright 打开 `/skills`，截图核对：8 格 KPI 完整、5 项健康条颜色对、Donut 有饼图、抽屉能弹出
- [x] 切换时间窗（30d ↔ 7d），核对：KPI 主值变、delta 重算、明细表 W 内列更新
- [x] 切视角（skill ↔ 人），核对：KPI 换算、明细表切表、Skill Donut 在按人视角隐藏
- [x] 点按来源双层 Donut 内环「未收录」扇区，核对：全局筛选变为 `src=non_catalog`，排行 / 明细更新；点外环 own 扇区，核对：`src=own` 联动
- [x] 点排行 Bar 一个 skill，核对：柱图加粗、Donut 切换到该 skill 的 runtime 分布、明细表该行加高亮、抽屉可打开
- [x] URL 分享回归：复制 URL 到新窗口，选中态 / 筛选 / 时间窗全部保留
- [x] 后端降级：前端按 optional 字段渲染；缺失时主值仍显示
- [x] 手机 375 宽度：三档断点渲染无横向滚动条，抽屉全屏可关闭

## 反思代码符合度（步骤 6 · 归档前必做）

- [x] 对照 design.md 逐节核 KPI 口径、健康阈值、治理三组定义
- [x] 对照 wireframes.md 三档字符图核桌面 / 平板 / 手机布局
- [x] 核 URL query 参数集完整、旧参数兼容
- [x] 核后端新字段可选返回、前端降级路径
