# board spec delta：skills-loading-performance

## 新增规则
- `/assets/*` Vite 指纹化构建产物必须返回长期缓存响应头，例如 `Cache-Control: public, max-age=31536000, immutable`。SPA HTML (`/` 与 BrowserRouter 深链) 必须保持可重新校验，不得长期缓存入口 HTML。
- `/api/skills` 与 `/api/skills/evidence` 可以支持 ETag / conditional request，但默认不得引入会跳过服务端新鲜度校验的 TTL 或 stale 缓存。若返回 `304`，其 ETag 必须对应同 URL、同查询参数和当前响应数据版本。
- SKILLS 前端请求层可以复用同 URL in-flight 请求，并可在服务端 `304` 校验通过后复用同 URL、同参数的已缓存 payload；不得因本地内存命中而跳过服务端校验。
- `/skills`、`/skills/evidence`、`/skill/:name` 与 `/operator/:name` 不应等待 `/api/state` 首包才开始渲染自身 loading/skeleton 和请求自身数据，除非未来引入明确的认证、租户、权限或全局配置依赖。Pods、Agents 和 AgentDetail 仍必须复用 `/api/state` 数据源。
- `/skills` 性能变更必须记录 before/after 基线，至少覆盖冷进入、返回页面、筛选切换三类场景，并记录主 JS/CSS 大小、`/api/skills` 与 `/api/skills/evidence` 请求次数、耗时和 `200/304` 状态码分布。

## 不变规则
- `/api/skills`、`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}` 的 used-only、窗口、筛选、evidence 和来源语义不变。
- 未经业务确认，不得为 `/api/skills` 或 `/api/skills/evidence` 增加 5-15 秒 TTL，也不得使用会跳过服务端校验的客户端缓存。
