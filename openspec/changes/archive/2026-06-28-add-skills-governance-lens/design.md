# 设计:add-skills-governance-lens

## 锁定口径
- **位置**:管理者筛选 Lens 放在 `/skills` 的"使用排行"卡片内部,位于标题/计数下、表格上方。
  不放页面顶部,不放趋势图之前,也不放右侧独立 KPI 卡。
- **默认不打断主线**:进入 `/skills` 时默认 Lens=`all`,表格仍是现有完整 Skill 使用排行。
- **Lens 只管排行**:切换 Lens 只影响使用排行表格;每日趋势图、全局过滤条、公司库采纳漏斗不跟着切。
- **只在按 Skill 视角展示**:按人视角不展示该 Lens,因为"未收录 Skill 占比"的主语是 Skill。
- **未收录定义**:服务端 `_skill_source(name, catalog_by) == CATALOG_SOURCE_UNKNOWN`(当前显示为 `非公司库`)。
  catalog 里 `type=external` 的 Skill 来源为 `external`,不算未收录。
- **统计口径**:只统计 `mode='used'`;`equipped` 永远不进分母或分子。
- **百分比公式**:`untracked_usage.ratio = untracked_used_sessions / total_used_sessions`。
  分母为当前 `days` 窗口内全部 used 会话×skill 记录数;空分母时 ratio=0。
- **Top 行占比**:`top[].share = 该未收录 Skill 在当前窗口内 used 会话数 / total_used_sessions`。
  Top 行按 `sessions desc`,平手按 `last_day desc`,再按 `name asc`。
- **窗口**:`days=7|30|90` 同时影响治理 Lens 的分母、分子、Top 列表和趋势。
  这与页面时间窗一致,便于管理者看"当前窗口内未收录占比"。

## 后端方案

### `/api/skills` 新增字段
在 `skills_overview(conn, days)` 里复用 catalog context,新增:

```ts
governance: {
  untracked_usage: {
    ratio: number
    used_sessions: number
    total_sessions: number
    skill_count: number
    top: Array<{
      name: string
      source: "非公司库"
      sessions: number
      share: number
      users_30d: number
      runtime_counts: Record<string, number>
      trend_14d: number[]
      trend_days: string[]
      last_day?: string
    }>
  }
}
```

实现细节:
- `total_sessions`: `SELECT COUNT(*) FROM skill_uses WHERE mode='used' AND day >= daily_start`。
- 候选未收录 Skill 不用 SQL join catalog;沿用现有 Python 侧 `_skill_source(skill, catalog_by)` 判定,
  保持和 `table[].source` 一致。
- `users_30d` 仍是近 30 天去重 operator 数,不随 `days` 变,与现有 `table[].users_30d` 列语义一致。
- `runtime_counts` 和 `trend_14d` 可复用现有 table 聚合产物,避免重复构造复杂 SQL。
- 当 catalog 不可达且从未成功拉取时,所有非 catalog 名都会被判为 `非公司库`。这是现有 `_skill_source`
  的行为;前端可通过既有 `catalog.stale/available` 提示目录状态。

### 为什么由后端计算
- 百分比分母和"非公司库"来源判定属于读侧契约,服务端统一输出能避免前端各处重算造成口径漂移。
- 后端已有 catalog context、`table` 聚合、UTC `today` 和窗口校验,增量成本低。

## 前端方案

### URL 状态
`frontend/src/lib/skillQuery.ts` 增加 `lens` query:
- 默认 `lens=all`。
- 支持 `all | untracked`。
- 切换视角到 `operator` 时不展示 Lens;可保留 query,回到 `skill` 时继续生效。

### SkillsView 布局
仅在 `view === 'skill'` 时,`使用排行`卡片内渲染:

```text
管理者筛选:
[ 全部 Skill ] [ 未收录使用占比 28% · 14/50 ]
```

`lens=all`:使用现有 `skillRows` 和 `SkillsTable`。

`lens=untracked`:使用 `data.governance.untracked_usage.top`,渲染 `GovernanceSkillTable`:
- Skill
- 占比
- used 会话
- 用户
- runtime
- 趋势
- 最近

行交互复用现有整行下钻规则,进入 `/skill/:name` 并透传当前 query。

### 空态
- total_sessions=0: Lens 按钮显示 `未收录使用占比 0% · 0/0`,选中后表格空态。
- total_sessions>0 但未收录为空:选中后显示"暂无未收录高频使用"空态。

### 视觉
- Lens 是排行内部的紧凑工具条,不是大号卡片。
- 使用现有 frame/card/table 风格;按钮高度接近现有 32px segmented control。
- 桌面:在排行卡片内占一行;移动端:按钮可换行,表格横向滚动沿用 `.skills-wrap`。

## 测试用例

### 后端单元测试
在 `tests/test_skills_stats_page.py` 增加:
- 构造 own、external、非公司库、equipped 数据。
- 请求 `/api/skills?days=7`。
- 断言:
  - `total_sessions` 只包含 7 天窗口内 used。
  - `used_sessions` 只包含 7 天窗口内 `source=非公司库` 的 used。
  - `external` 不进入 `used_sessions` 或 Top。
  - `equipped` 不进入分母/分子。
  - `ratio` 和 `top[].share` 以 `sessions / total_sessions` 计算。
  - `days=30` 时窗口扩大后数值随窗口变化。

### 前端验证
- `npm --prefix frontend run build`。
- 桌面 `/skills?view=skill&lens=all`:默认仍显示完整 Skill 主榜。
- 点击"未收录使用占比":主榜切成未收录列表,趋势图和漏斗不变,行点击进入 Skill 详情。
- `/skills?view=operator`:不显示管理者筛选 Lens。
- 窄屏 ≤600px:Lens 按钮不挤压表格,表格可横向滚动。

## 权衡
- **Lens 只影响排行,不影响图表**:保持页面主线稳定;代价是图表不会同步变成未收录趋势。若后续需要,
  可以新增独立 Lens 趋势,但这次不扩大范围。
- **百分比分母随窗口走**:符合用户"应该算百分比"的管理语义;代价是主表固定 7/30/累计列和 Lens
  窗口口径不同,需要文案明确"当前时间窗"。
- **不把 `external` 算未收录**:catalog 里 external 已被收录为外部来源,与"没有被我们收录"不同。

## 风险
- catalog 首次不可达时,服务端会把所有非 cached catalog 名视为 `非公司库`,导致占比偏高。
  现有 catalog 不可达/过期提示仍会暴露该风险。
- 新增 query `lens` 可能与旧链接并存;默认 `all` 向后兼容。
- 回滚:移除前端 Lens 和 `/api/skills.governance` 字段即可,不影响写侧数据。
