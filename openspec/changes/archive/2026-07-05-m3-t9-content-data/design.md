# 设计：m3-t9-content-data

## 服务端 overview 口径
- 在 `server/routes/board.py` 增加 overview 专用占位名过滤：精确过滤 `$name`、`$d`、`$s`、`foo`、`foo-bar`，前缀过滤 `dbs`、`gstack`。
- 过滤只作用于 `/api/skills` overview 相关聚合：table、daily、operator_table、operator_daily、governance、funnel、published 和 period comparison。`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}` 不在本任务范围内删除原始事实。
- `governance.cataloged_not_installed` 的 zero-install 口径从公司库名单中排除当前窗口已有 used 的 skill，避免显示“0 人安装但有使用”。
- `published_skills[]` 与 `current_published_skill_count` 仍保留“当前窗口发布但未使用也计入”的既有规则，但若当前窗口有 used 且 installers=0，则按 PM 消歧从当前发布名单和计数排除。

## 前端展示口径
- `KpiStrip` 的未收录 KPI detail 和 records 使用 `governance.untracked_usage.used_sessions` / `skill_count`；Top 列表只作为预览名单，不作为总数事实源。
- 新增发布 KPI detail 显示短名单或空态文案，不再重复显示与核心数值相同的数字。
- `demoSkillsOverview()` 接收请求窗口并返回对应 `window.key/days/start/end` 与日级序列；`useSkillsOverview()` fallback 传入当前 query 中的 `w` 或 `days`。
- i18n 统一短窗口文案为「近 7 天」/ `Last 7 days`，Top3 使用固定大小写。

## 测试设计
- 后端固定造数覆盖 used-but-uninstalled company skill 同时从 `governance.cataloged_not_installed.top`、`published_skills[]`、`period_comparison.current_published_skill_count` 排除。
- 后端固定造数覆盖占位名出现在 catalog/profile/usage 后不进入 overview 响应。
- 前端单测覆盖移动摘要、window label、Top3 文案、未收录聚合字段不依赖 Top 长度，以及 demo fallback 不泄漏占位名。
- 验证命令覆盖 Python 编译、相关 pytest、全量 pytest、前端 unit、前端 build、coverage 和 `git diff --check`。

## 权衡
- 本任务不清洗原始数据表，也不改变 evidence/detail 路由。原因是 issue 范围限定在 `/skills?w=7d` 总览页和直接展示口径；删除原始事实会扩大行为边界。
- 过滤函数集中在 board overview 层，避免在前端用字符串兜底掩盖 API 分叉。
