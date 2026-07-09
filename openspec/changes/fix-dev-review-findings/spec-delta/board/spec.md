# board spec delta：fix-dev-review-findings

## 修改
- `/api/skills?w=...` overview placeholder/test skill 过滤必须大小写不敏感，过滤 `$name`、`$d`、`$s`、`foo`、`foo-bar`、`dbs*`、`gstack*` 的大小写变体。
- `/api/skills/evidence?kind=total` 的 `summary.records` 必须与同窗口 `/api/skills` 的 `period_comparison.current_sessions` 使用同一 placeholder/test skill 过滤口径；其它 raw-record evidence kind 也不得泄漏 overview 明确过滤的 placeholder/test skill 名。
- `/api/skills.published_skills` 与 `period_comparison.current_published_skill_count` / `previous_published_skill_count` 必须使用同一口径：当前或上一统计窗口内 `used>0 && installers=0` 的 company skill 不计入对应窗口的新发布 skill 数。
- `/skills/evidence` 切换 URL filter 时，晚返回的旧筛选响应不得污染当前 URL；分页入口必须在 `loaded < total` 时保持可聚焦可操作，并支持从带 `offset` 的直达 URL 继续加载后续页。
- Docker/Compose healthcheck 必须探测当前运行端口 `PORT`，未设置时回退 `8788`；既有部署的数据卷名不得因 compose 变更而断挂。
