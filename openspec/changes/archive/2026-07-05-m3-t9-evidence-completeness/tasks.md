# 任务：m3-t9-evidence-completeness

- [x] 在 `frontend/src/lib/skillsEvidence.ts` 增加 evidence 分页 query、query key、总量计算、has-more 判断和追加合并纯函数。
- [x] 为分页 query、筛选保留、追加去重、367 条唯一记录完整可达、重试同 offset、总量漂移语义补 `frontend/src/lib/skillsEvidence.test.ts`。
- [x] 为慢响应跨筛选丢弃、请求 abort/timeout 后恢复为可重试状态补 query-key 与请求 helper 单元测试。
- [x] 在 `frontend/src/views/SkillsEvidence.tsx` 增加“加载更多记录”按钮、已加载/总量、加载中、错误重试和完成态。
- [x] 在 `frontend/src/views/SkillsEvidence.tsx` 为加载更多请求接入 query key 校验、AbortController 和有界 timeout，确保旧响应不得污染新筛选列表。
- [x] 补必要 CSS，确保按钮在桌面/手机下不挤压主表，并保持键盘可见焦点。
- [x] 验证刷新带筛选参数的 evidence URL 后首批、总量和继续加载能力一致。
- [x] 跑 `npm --prefix frontend run test:unit`。
- [x] 跑 `npm --prefix frontend run build`。
