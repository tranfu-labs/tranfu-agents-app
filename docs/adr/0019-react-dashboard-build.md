# ADR-0019 React dashboard build, while keeping one runtime container

- 状态:Accepted
- 关联:ADR-0001、specs/board、openspec/changes/frontend-react-rewrite

## 背景
看板最初是 `dashboard/index.html` 单文件原生 JS,部署简单,但视图状态只存在内存中:
切到 Agents / SKILLS / 详情页后 URL 不变,刷新会回首页,也无法分享具体 agent 或 skill 的深链。

这次变更的真实目标不是给单文件补一个 hash router,而是借路由问题把看板前端升级到可维护的
React 技术栈,同时保留本项目最重要的运维取舍:单容器、SQLite、同源 API、无外部服务。

## 决策
- 看板前端改为 `frontend/` 下的 Vite + React + TypeScript 应用。
- 路由使用 BrowserRouter path URL:
  `/`、`/agents`、`/agent/:key`、`/skills`、`/skill/:name`。
- SKILLS 总览筛选状态使用 nuqs 绑定到 search params,例如
  `/skills?win=30&rt=claude-code&src=own&q=geo&sort=sessions_30d`。
- 交付仍是单容器: Docker 多阶段构建在 node stage 里执行 `npm ci && npm run build`,
  Python runtime stage 只复制 `frontend/dist`,不携带 node 运行时。
- 仓库不提交 `frontend/dist`;FastAPI 只在运行时提供构建产物。
- API、事件协议、SQLite schema、shim、collector 计算逻辑不因本 ADR 改动。
- 前端仍必须使用同源相对路径访问 API,不得使用 localStorage/sessionStorage 等浏览器本地存储。

## 对 ADR-0001 的修订
ADR-0001 的“单容器 + SQLite + 无外部 DB/MQ”继续有效。

被本 ADR 取代的部分是“禁止独立前端构建”。新约束是:允许前端构建步骤,但只能作为仓库内
构建阶段存在,最终运行形态仍是一个 FastAPI 容器,且运行镜像不依赖 node。

## 后果
- ✅ URL 可刷新、前进后退、复制分享。
- ✅ 前端代码可按视图、组件、hook、类型拆分,降低单文件维护成本。
- ✅ 运行部署仍保持一个 service、一个域名、一个 SQLite 文件。
- ⚠️ 构建链路新增 npm 依赖,CI 与 Docker build 必须覆盖前端构建。
- ⚠️ FastAPI 需要 SPA fallback,必须保证 `/api`、`/v1`、`/shims`、`/install.sh`、`/healthz`、
  `/llms.txt`、`/robots.txt` 等既有路由不被 catch-all 吞掉。
