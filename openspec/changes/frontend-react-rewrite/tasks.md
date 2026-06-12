# tasks:frontend-react-rewrite

- [x] 0. 治理:新增 ADR-0019,更新 module-map / AGENTS,新增本 OpenSpec change。
- [x] 1. 脚手架:新增 `frontend/` Vite + React + TypeScript + react-router + nuqs。
- [x] 2. 迁移静态壳:SEO head、logo、CSS 变量、暗/亮主题、中英 i18n、demo/offline badge。
- [x] 3. 数据 hook:实现 `/api/state` 3s 轮询、`/api/skills` 和 `/api/skill/{name}` 10s 轮询。
- [x] 4. 路由与视图:实现 5 条 path 路由,支持刷新/深链/前后退/tab active。
- [x] 5. SKILLS URL 状态:用 nuqs 绑定搜索/runtime/source/window/sort/dir,筛选 replace,详情 push。
- [x] 6. 服务端:FastAPI 静态资源 + SPA fallback,保留既有 API/shim/install 路由与目录穿越防护。
- [x] 7. Docker/CI:多阶段 build;CI 增加 node 安装和前端 build。
- [x] 8. 文档:同步 AGENTS、module-map、DEPLOY、DEV-SETUP、UPDATE、README 等前端构建说明。
- [x] 9. 测试:新增 fallback 不吞 API 用例;跑前端 build、py_compile、pytest。
- [x] 10. 清理:删除旧看板入口;更新未归档 OpenSpec change 中旧前端落点与旧脚本检查命令。
