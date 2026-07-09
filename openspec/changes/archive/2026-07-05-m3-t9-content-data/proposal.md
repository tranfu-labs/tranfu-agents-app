# 提案：m3-t9-content-data

## 背景
`/skills?w=7d` 总览页存在一组内容与数据一致性缺陷：未收录数量在 KPI 与线索区不一致，KPI 会重复展示同一数字，`post-illustration-images` 与 `product-title-generation` 出现“0 人安装却有使用”，新增发布 Skill 计数与零装机区分叉，占位/测试 skill 名泄漏到页面，时间窗与 Top3 文案中英文和大小写不统一。

本任务只覆盖 `/skills?w=7d` 总览页及其直接数据/展示口径，不扩展到 `/skills/evidence`、`/skills/clues/*`、`/skill/:name` 等详情页。

## 提案
- 将 `/skills?w=7d` 未收录 KPI、问题线索、待处理线索统一为 `governance.untracked_usage.used_sessions` 与 `skill_count` 派生，不再用 Top 列表长度或在 KPI detail 重复同一数字。
- 对当前窗口有 `mode=used` 记录但 profile 安装态为 0 的公司库 skill，排除出 zero-install 区和当前窗口新增发布 Skill 计数；本次不新增异常文案。
- 在 overview 响应和页面 fallback 中过滤 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*` 占位/测试名，原始 evidence/detail 事实不纳入本任务范围。
- 统一 `/skills?w=7d` 与 demo fallback 的时间窗和排行文案为「近 7 天」/ `Last 7 days` / `Top3`。
- 补固定造数测试覆盖 API 三处字段、前端 settled/fallback 展示和占位过滤。

## 验收语句
1. 打开 `/skills?w=7d` → KPI 未收录数与线索区未收录数一致，且 KPI 不再重复展示同一数字。
2. 打开 `/skills?w=7d` → `post-illustration-images` 与 `product-title-generation` 不再显示 0 人安装却有使用，新增发布计数与零装机区一致。
3. 打开 `/skills?w=7d` 并搜索页面文本 → 应看不到 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*`，时间和排行文案统一为近 7 天与 Top3。
4. 造数 `post-illustration-images`、`product-title-generation` 为当前 7 天发布的 `own|meta`，当前 7 天有 `mode=used`，profile 安装态为 0 → `/api/skills?w=7d` 的 `governance.cataloged_not_installed.top`、`published_skills[]`、`period_comparison.current_published_skill_count` 均不包含这两个 skill，页面也不出现“0 人安装”与其使用记录并列的表达。
5. 造数非公司库 used 记录 N 条、M 个 skill，且 `governance.untracked_usage.top` 只返回部分 Top 项 → `/skills?w=7d` KPI、问题线索、待处理线索展示的未收录记录数/skill 数必须来自 `used_sessions=N`、`skill_count=M`，不得使用 Top 列表长度。
6. 让 `/api/skills?w=7d` 请求失败进入 demo fallback → `/skills?w=7d` 渲染完成后页面文本仍不得包含 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*`，窗口与排行文案仍为「近 7 天」/ `Last 7 days` / `Top3`。
7. 构造占位名同时出现在 table、daily、operator_table、operator_daily、governance、funnel、published 输入中 → `/api/skills?w=7d` 响应和页面可见文本都不得返回这些名字；原始 evidence/detail 不作为本任务验收对象。

## 影响
- 影响模块：M1 服务端 `/api/skills` overview 聚合，M2 前端 SKILLS 总览展示、demo fallback 和文案。
- 不改变 ingest 协议、profile 上报模型、evidence/detail 原始事实或 PR/merge 流程。
