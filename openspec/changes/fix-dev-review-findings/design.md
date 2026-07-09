# 设计：fix-dev-review-findings

## 方案
### 后端 SKILLS 口径
- 将 overview placeholder SQL filter 改为大小写不敏感的精确名判断。
- `/api/skills/evidence` 默认套用同一 placeholder filter，使 `kind=total` 的 `summary.records` 与 `/api/skills` 的 `period_comparison.current_sessions` 保持一致。
- 对 list evidence 的 company catalog 名单也排除 placeholder 名称。
- `_published_skill_summary` 对 current 与 previous 使用同一 helper：只统计 company catalog、非 placeholder、可解析 `published_at`，并排除该统计窗口内 `used>0 && installers=0` 的 skill。

### 前端 evidence
- 在 `useSkillsEvidence` 内为每次请求记录 URL/request id，只有当前 URL 的响应才能 `setData`。
- `SkillsEvidenceView` 内的 page data identity 跟随 current query key；切换 URL 时清空旧 page data，避免旧 payload 被当前 key 包装。
- load-more 控件以 `hasMore` 为准显示；下一页 offset 用当前 URL offset + 已加载唯一数，支持直接打开 `offset=100` 的分页 URL 后继续加载下一页。

### 部署配置
- workflow 内设置 `IMAGE_TAG_ROLLING=dev`、`IMAGE_TAG_SHA_PREFIX=sha-` 默认值，并在 validate step 校验非空。
- compose 恢复旧 named volume，避免现有 `/data/tf.db` 断挂。
- Dockerfile / compose healthcheck 读取当前 `PORT` 环境变量并默认回退 `8788`，与实际 uvicorn 端口一致。

## 权衡
- 本次不尝试改写 Coolify Docker Image Application 的 `docker_registry_image_tag`，因为线上资源类型和 token 权限需要确认；先消除确定性的空 tag、数据卷和 healthcheck 回归。
- evidence 继续使用后端全量 rows 后切片的既有实现，只修复本次引入的可达性和口径问题，性能优化另走独立 change。

## 风险
- evidence 过滤 placeholder 会让原始 evidence 不再显示这些测试名；这与当前 board spec 的 overview/evidence 对齐约束一致。
- 恢复旧 volume 名对新部署会创建旧名字的卷；对现有部署是安全路径，避免数据“消失”。
- 如果线上实际希望完全使用 immutable SHA 镜像部署，还需要后续确认 Coolify 资源类型后补一个专门 change。
