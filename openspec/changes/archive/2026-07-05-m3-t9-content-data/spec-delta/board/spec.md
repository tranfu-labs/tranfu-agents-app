# board spec delta：m3-t9-content-data

## MUST
- `/api/skills?w=7d` overview 层必须过滤 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*` 占位/测试 skill 名；过滤范围包括 table、daily、operator_table、operator_daily、governance、funnel、published 和 period comparison。原始 evidence/detail 不作为本规则范围。
- `/api/skills?w=7d` 的 `governance.untracked_usage.used_sessions` 与 `skill_count` 是未收录使用展示的总量事实源；`top[]` 只是预览名单，前端 KPI、问题线索和待处理线索不得用 `top.length` 替代总量。
- 当前窗口有 `mode=used` 记录但 installers=0 的公司库 `own|meta` skill 不得进入 `/api/skills?w=7d` 的 `governance.cataloged_not_installed.top`、`published_skills[]` 或 `period_comparison.current_published_skill_count`。
- `/skills?w=7d` settled render 与 demo fallback 的窗口文案必须统一为「近 7 天」/ `Last 7 days`，排行文案必须使用 `Top3`。
- `/api/skills?w=7d` 请求失败进入 demo fallback 时，页面可见文本仍不得泄漏 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*`。

## 可验证行为
- 造数 `post-illustration-images`、`product-title-generation` 为当前 7 天发布的 company skill，当前 7 天有 used 且 profile 安装态为 0 → `/api/skills?w=7d` 三处字段和页面展示均不出现“0 人安装且有使用”的并列表达。
- 造数非公司库 used 记录 N 条、M 个 skill，且 Top 只返回部分项 → `/skills?w=7d` 未收录 KPI/线索展示 N/M，而不是 Top 项数量。
- 造数占位名同时进入 catalog/profile/usage → `/api/skills?w=7d` 响应字符串与页面可见文本不包含这些占位名。
