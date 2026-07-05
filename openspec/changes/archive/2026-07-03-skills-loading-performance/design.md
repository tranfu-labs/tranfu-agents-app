# 设计：skills-loading-performance

## 方案
1. 基线测量
   - 使用同一环境采样 before/after：冷进入 `/skills`、从其它页面返回 `/skills`、切换 `w/rt/src/q/view` 等筛选。
   - 记录首屏可见时间、主 JS/CSS 构建产物大小、`/api/skills` 与 `/api/skills/evidence` 请求次数、耗时、状态码分布。
   - 若使用 ETag，指标必须区分 `200` 与 `304`；修改数据后验证不会被客户端错误吃掉。

2. 路由首包解耦
   - 当前 `App` 只有在 `state.data` 存在时才挂载所有 `Routes`，这会让 `/skills` 等低频聚合页先等 `/api/state` 或 SSE 首包。
   - 将 state 依赖收敛到 Pods、Agents、AgentDetail 等真正需要 `/api/state` 的路由；SKILLS 总览、证据页、Skill 详情、Operator 详情改为可先渲染自身 loading/skeleton 并独立请求数据。
   - `TopBar` 已接受 `state: StatePayload | null`，可继续显示空统计占位，不需要等待 state 才显示 SKILLS 主体。
   - 安全/权限确认：当前 `/api/state`、`/api/skills`、`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}` 均为同源只读公开路由；`/skills` 系列页面不依赖 `/api/state` 的认证、租户、权限或全局配置副作用。若实施时发现隐性依赖，只拆出最小必要依赖，不绕过 gate。

3. 静态缓存
   - `/assets/*` 是 Vite 指纹化构建产物，响应头设置 `Cache-Control: public, max-age=31536000, immutable`。
   - SPA HTML 深链与 `/` 返回 `Cache-Control: no-cache`，让浏览器每次 revalidate HTML，避免长期缓存入口 HTML。
   - API 默认不做 TTL；可以为 SKILLS API 设置 `Cache-Control: no-cache` 搭配 ETag，使客户端和中间缓存必须向服务端校验。

4. API ETag
   - `/api/skills` 与 `/api/skills/evidence` 在生成响应后基于请求参数与响应数据版本计算 ETag。
   - ETag 输入至少包含归一化 query 参数、响应 JSON bytes 或等价稳定序列化结果；不同 URL / 参数不得共用 ETag。
   - 若请求 `If-None-Match` 命中同参数当前响应 ETag，返回 `304` 且无 body；否则返回 `200` JSON 与新 ETag。
   - 不引入服务端 `/api/skills` TTL，不用缓存掩盖 SQL 聚合问题；本次只减少未变化 payload 的传输和客户端解析成本。

5. 前端请求去重与已校验复用
   - 为 SKILLS 相关 GET 建立小型内存态：`url -> inFlight Promise` 与 `url -> { etag, data }`。
   - 同 URL 正在请求时复用同一个 Promise，避免筛选快速切换或多组件挂载造成重复请求。
   - 发送请求时如果有同 URL etag，带 `If-None-Match`；收到 `304` 只复用同 URL、同参数、已由本次服务端校验通过的 payload。
   - 不做时间 TTL，不因为本地 Map 命中而跳过服务端请求。

6. 过渡态
   - 首次加载仍显示 SKILLS 控制条 + loading/empty skeleton。
   - 增量刷新、返回页面和筛选切换时保留旧数据，并通过 `loading` / `is-refreshing` / 错误提示表达后台刷新状态。
   - 错误时保留旧数据优先于清空页面；无旧数据时才落到 demo/empty/error。

## 权衡
- 选择“保守新鲜度 + 局部优化”，放弃本轮 API TTL。这样性能收益可能小于 5-15 秒缓存，但不会改变统计实时语义。
- 不做 SSR/预渲染或大架构迁移，因为当前证据还不足以证明 SPA 架构是主要瓶颈。
- 不引入状态库，请求去重只放在现有 `frontend/src/lib/api.ts` 附近，保持模块边界清晰。
- ETag 需要先生成响应才能比较，不能降低服务端聚合 CPU；它主要减少未变化响应的传输、JSON parse 和重渲染成本。若 before/after 显示服务端 SQL 仍是主瓶颈，后续按 board spec 的 SQL/索引优化路径另开 change。

## 风险
- 路由解耦可能暴露某些组件隐式依赖 `state.data` 的假设。实现时逐路由检查，Pods/Agents/AgentDetail 保持 gate。
- 手写 ETag 若参数归一不完整，可能误用旧 payload。测试必须覆盖不同 query 不共享 ETag、同 query 304 复用、数据变化后返回 200。
- 静态缓存若误加到 HTML，会导致旧入口引用旧资源。缓存头测试必须区分 `/assets/*` 与 SPA HTML。
- 前端保留旧数据可能让用户误以为已刷新完成。UI 必须保留 loading/refreshing 状态，失败时显示错误提示。

## 验证记录
- 环境：同一 seeded SQLite DB（约 60k `skill_uses`），before 使用 `origin/main` worktree，after 使用当前 change；生产构建后用本地 FastAPI + Chrome headless CDP 采样。
- 构建体积：before 主 JS `442.83 kB`、CSS `64.66 kB`；after 主 JS `444.00 kB`、CSS `64.66 kB`。本次未降低 bundle 体积。
- 冷进入 `/skills`：before FCP/LCP `304 ms`，列表/排行首次可见约 `816.8 ms`，`/api/skills?w=7d&days=7` 为 `200`，约 `396.2 -> 635.5 ms`；after FCP/LCP `248 ms`，列表/排行首次可见约 `741.9 ms`，`/api/skills?w=7d&days=7` 为 `200`，约 `237.9 -> 534.2 ms`。`/api/state/stream` 仍会打开，但不再阻塞 `/skills` 自身请求启动；EventSource 为长连接，无正常 response end。
- 从其它页返回 `/skills`：before 50ms 采样旧列表已清空（`rowsAt50=0`，loading），`/api/skills` 再次 `200`，约 `2.7 -> 181.2 ms`，列表/排行约 `343.4 ms` 后恢复；after 50ms 采样旧列表保留（`rowsAt50=900`，refreshing），`/api/skills` 为 `304`、body `0`，约 `163.0 -> 335.2 ms`，不会闪空。
- 切换窗口筛选：before/after 都保留旧列表，不清空页面；after 浏览器 waterfall 中 `/api/skills?w=14d&days=14` 为 `200`，`44.3 -> 254.6 ms` 是同一次请求相对筛选动作的 start/end，不是 before/after 对比。为排除 200 路径回归，另用同一 DB、本地 FastAPI、完整读取 body 的 5 次复测：before 中位数 `190.8 ms`、平均 `193.2 ms`；after 中位数 `192.2 ms`、平均 `191.2 ms`；body 均为 `1,382,752 bytes`。结论是没有稳定 200 耗时回归，ETag 计算没有在该路径形成可观测额外成本。
- `/api/skills/evidence` 不在上述 `/skills` 三类场景中触发；单独 HTTP/TestClient 验证覆盖同 URL `200 -> 304`、body `0`，不同参数与数据变化不复用旧 payload。
