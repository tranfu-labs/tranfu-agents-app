# 提案：skills-loading-performance

## 背景
`/skills` 页面当前体感仍有加载优化空间。公开快速检查显示入口 HTML 较小且响应快，但主 JS、CSS、`/api/skills?w=7d` 与 `/api/skills/evidence?w=7d` payload 均有一定体量，响应头也没有明确缓存策略。当前前端还会在 `App` 根部等待 `/api/state` 首包后才渲染所有路由，导致 `/skills` 这类只依赖 SKILLS 聚合 API 的页面可能被全局 state 首包阻塞。

本次不把问题预设为单一瓶颈，先做分层基线，再执行低风险局部优化。分支 base 已验证：创建方案前当前 detached HEAD 与 `origin/main` 均为 `824d16724a7c77f71674d59a7da83f989801009c`。

## 提案
- 建立 before/after 基线，覆盖冷进入 `/skills`、从其它页面返回 `/skills`、切换筛选三类场景。
- 为 Vite 指纹化 `/assets/*` 添加长期缓存响应头，为 SPA HTML 保持 `no-cache`，避免旧 HTML 引用过期 bundle。
- 让 `/skills`、`/skills/evidence`、`/skill/:name`、`/operator/:name` 在不依赖 `/api/state` 首包的情况下渲染自身 loading / skeleton，并并行加载各自 API。
- 为 `/api/skills` 与 `/api/skills/evidence` 增加保守 ETag / conditional request 支持：每次请求仍到服务端校验，不引入 5-15 秒 TTL，不跳过服务端新鲜度校验。
- 在前端 SKILLS 请求层增加同 URL in-flight 去重；`304` 只允许复用同 URL、同参数、已校验的新鲜 payload。
- 刷新或筛选切换时保留旧数据作为过渡态，并用 loading / refreshing 状态表达后台刷新中，不把旧数据伪装成已刷新结果。

## 影响
- 受影响模块：M1 `server/routes/onboarding.py` / `server/routes/board.py` / 安全头中间件，M2 `frontend/src/App.tsx` 与 `frontend/src/lib/api.ts`。
- 不改变 `/api/skills`、`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}` 的统计语义、筛选语义和 payload 结构。
- 不引入 SSR、预渲染、大状态库、外部缓存、外部数据库或运行期 node 依赖。
- 若后续业务明确接受 5-15 秒统计陈旧，再作为独立 change 讨论 API TTL / stale-while-revalidate。
