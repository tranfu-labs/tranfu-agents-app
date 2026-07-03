# 设计：published-skills-page

## 方案

### 1. Catalog 元数据保留
`server/catalog.py` 的 `_parse_catalog_payload` 继续兼容旧 catalog，但新增保留这些字段：

- `version`
- `author`
- `updated_at`
- `published_at`
- `path`
- `sha`

`name/type/description` 仍保持现有清洗逻辑。`published_at` 缺失或格式不可解析时，该 skill 不进入“新增发布”统计，但不能导致 catalog 同步失败。

### 2. 新发布聚合
在 board 域新增一个聚合 helper，输入为当前 skills window、catalog items、安装态和 used 记录聚合，输出当前窗口内新发布的公司库 skill 列表。

口径：

- 只统计 `type in {own, meta}`。
- `published_at` 作为 UTC instant 解析后转换到 `Asia/Shanghai` 统计日。
- `published_day` 落在 `[window.start, window.end]` 的 skill 计入当前窗口。
- 同长上一窗口也按同一规则计算数量，用于 delta。
- `external` 不计入。
- 发布但未安装、未使用的 skill 也计入，使用数为 `0`。

建议返回字段：

```json
{
  "published_skills": [
    {
      "name": "agent-architecture-decision",
      "source": "own",
      "version": "0.2.0",
      "author": "griffithkk3-del",
      "published_at": "2026-07-03T09:04:22.000Z",
      "published_day": "2026-07-03",
      "updated_at": "2026-07-03",
      "path": "own-skills/agent-architecture-decision",
      "sha": "7e3b67669dbd17c9f54aa01cc6290ed909babdfe",
      "installers": 0,
      "window_sessions": 0,
      "last_day": null
    }
  ],
  "period_comparison": {
    "current_published_skill_count": 1,
    "previous_published_skill_count": 0
  }
}
```

`published_skills` 只返回当前窗口列表。排序按 `published_at desc, name asc`。catalog 不可达时返回空列表和 `0`，前端用既有 `catalog` 状态显示不可达或过期提示。

### 3. `/skills` 首屏替换
`KpiStrip` 中 skill 视角的第四格从 `kpiAvgSkillPerSession` 改为 `kpiPublishedSkills`：

- value：`period_comparison.current_published_skill_count`。
- previous：`period_comparison.previous_published_skill_count`。
- 点击入口：`/skills/new`，保留 `w/wstart/wend`，可保留 `q` 作为页面内搜索词；不保留 `rt/sel/topn/view`。

`HealthBar` / 问题线索中同名项也改为 `新增发布 Skill`，同样跳 `/skills/new`。该项只显示事实值和图标入口，不在首屏铺名单。

### 4. `/skills/new` 独立页面
新增 React route `/skills/new`。该路由不等待全局 `/api/state` 首包，复用 `useSkillsOverview` 拉取 `/api/skills`，并使用 `published_skills` 渲染名单。

页面结构：

- 页头：返回 `/skills`、标题「新增发布 Skill」、当前窗口 chip、catalog stale/unavailable 提示。
- 控制：时间窗选择、搜索 skill、来源筛选 `全部/own/meta`。
- 主列表：名称、来源、版本、发布时间、更新时间、作者、装机数、当前窗口使用数、最近使用日。
- 行为：有详情页的 skill 行可点到 `/skill/:name`；未使用或查无 used 详情时仍保持名单可读，不强行跳 raw evidence。
- 空态：窗口内无新发布时显示“当前时间窗没有新发布 Skill”。

### 5. 测试与验证
后端改动含可测逻辑，必须加 pytest：

- catalog parser 保留 `published_at/version/path/sha` 等字段。
- 当前窗口内 `own` 或 `meta` 的 `published_at` 计入，即使没有 `skill_uses`。
- `external` 的 `published_at` 不计入。
- 上一同长窗口数量进入 `previous_published_skill_count`。
- 缺失或无效 `published_at` 不抛错且不计入。

前端改动至少运行：

- `npm --prefix frontend run test:unit`
- `npm --prefix frontend run build`

页面验证使用本地 Vite 或构建预览打开 `/skills` 与 `/skills/new`，检查桌面与手机宽度下文字不重叠、列表可读、入口可键盘访问。

## 权衡
- 不复用 `/api/skills?scope=new`：`scope=new` 是历史首次 used 口径，和新发布不是同一事实源，复用会误导用户。
- 不新增单独 `/api/skills/new`：当前列表可以随 `/api/skills` 一次返回，避免再增加一个低频 API；如列表未来变大或需要分页，再拆独立端点。
- 用 `published_at` 而不是 `updated_at`：用户明确关心“发布了但未使用”的 skill，`published_at` 能区分首次发布，避免版本更新被误算为新发布。
- 统计 `own|meta` 不含 `external`：现有公司库治理漏斗把 `own|meta` 作为公司库资产口径，`external` 只作为已收录外部来源参与来源归因。

## 风险
- 旧 catalog 或内网镜像可能暂时没有 `published_at`。缓解：字段缺失时返回 0 和空列表，不影响其它 SKILLS 聚合。
- `/api/skills` 响应体会增加 `published_skills`。当前 catalog 规模小，短期可接受；若 catalog 增长到数千条，需要改为分页端点。
- `published_at` 是 instant，窗口是 `Asia/Shanghai` date-only。实现必须统一用服务端统计时区转换，否则 UTC 晚间发布会落错统计日。
