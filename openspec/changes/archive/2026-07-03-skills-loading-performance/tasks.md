# 任务：skills-loading-performance

- [x] 记录 before 基线：冷进入、返回 `/skills`、筛选切换；记录首屏感知、JS/CSS 大小、`/api/skills` 与 `/api/skills/evidence` 请求次数/耗时/状态码。
- [x] 服务端添加缓存头策略：`/assets/*` 长缓存，SPA HTML `no-cache`，SKILLS API 保守 revalidate。
- [x] 服务端为 `/api/skills` 与 `/api/skills/evidence` 添加 ETag / `If-None-Match` 处理，不引入 TTL。
- [x] 前端拆除 `/skills` 系列路由对全局 `/api/state` 首包的阻塞，保留 Pods / Agents / AgentDetail 的 state gate。
- [x] 前端 SKILLS 请求层添加同 URL in-flight 去重、同 URL ETag 校验复用与过渡态保留。
- [x] 补充单元测试：缓存头、ETag 200/304、不同 query 隔离、数据变化返回 200、请求去重与 304 复用。
- [x] 运行验证：`python -m py_compile server/*.py server/routes/*.py`、`pytest tests/`、`npm --prefix frontend run test:unit`、`npm --prefix frontend run build`。
- [x] 记录 after 基线，与 before 对比；明确报告冷进入、返回页面、筛选切换三类场景。
