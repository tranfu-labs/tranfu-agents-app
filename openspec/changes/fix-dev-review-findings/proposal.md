# 提案：fix-dev-review-findings

## 背景
`dev` 相对 `main` 的最近提交引入了 SKILLS 证据页分页、overview 占位 skill 过滤、发布 skill 统计和 GHCR/Coolify 部署链路调整。代码审查发现几类回归风险：

- evidence 请求切换筛选时，旧响应可能晚返回并污染当前 URL。
- overview 已过滤占位/测试 skill 名，但 evidence 下钻仍按原始 rows 计数，KPI 与记录页不一致。
- 发布 skill 的 previous-window 计数和当前窗口的零装机使用排除口径不一致。
- dev 部署 workflow 缺少 tag 默认值/校验，compose volume 改名会让现有 SQLite 数据看起来丢失，healthcheck 与可配置 `PORT` 不一致。

## 提案
- 让 SKILLS overview 与 evidence 在占位/测试 skill 过滤上保持同一口径，并让大小写变体也被过滤。
- 修复发布 skill previous/current 两个窗口的同口径统计。
- 给 evidence 请求加 query identity 防护，并修复 load-more 在非默认 `limit` / 直达 offset 下的后续分页。
- 保守修复部署配置：恢复既有命名卷，给 workflow 镜像 tag 设默认值并校验，healthcheck 使用当前 `PORT`。

## 影响
- 影响 `server/routes/board.py` 的 SKILLS overview/evidence 聚合口径。
- 影响 `frontend/src/lib/api.ts`、`frontend/src/lib/skillsEvidence.ts`、`frontend/src/views/SkillsEvidence.tsx` 的 evidence 数据刷新和分页行为。
- 影响 `.github/workflows/deploy.yml`、`Dockerfile`、`compose.yml` 的 dev 镜像部署与健康检查。
- 不改变 TATP 写入协议，不引入 token/费用统计，不新增外部运行依赖。
