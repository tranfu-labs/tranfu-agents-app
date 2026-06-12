# 变更提案:frontend-react-rewrite(看板前端 React 重写)

- 状态:Proposed
- 关联:specs/board、ADR-0019、ADR-0001

## 背景 / 问题
现有看板是 `dashboard/index.html` 单文件原生 JS。切换 Pods / Agents / SKILLS / 详情视图时 URL
不变化,刷新或复制链接都会丢失当前视图。直接给单文件补状态同步可以解决表层问题,但长期维护上,
所有 CSS、i18n、轮询、图表、demo 数据和模板字符串都挤在一个文件里,后续视图扩展成本持续升高。

## 目标
- 将看板前端升级为 `frontend/` 下的 React + TypeScript + Vite 应用。
- 用 BrowserRouter 提供可刷新、可分享的 path 路由:
  `/`、`/agents`、`/agent/:key`、`/skills`、`/skill/:name`。
- 用 nuqs 将 SKILLS 总览筛选绑定到 URL search params,筛选刷新后保持。
- 尽量像素级保留现版视觉:CSS 变量、暗/亮主题、中英 i18n、红色 logo、组件 className 保持同档。
- 继续消费现有 API,不改 `/api/state`、`/api/skills`、`/api/skill/{name}`、`/api/agent/{key}`、
  `/v1/*`、`/shims/*`、`/install.sh`、`/healthz` 等契约。
- 部署仍是单容器;Docker 多阶段构建产物,仓库不提交 `dist`。

## 非目标
- 不改 shim、TATP 协议、collector 写入、计算逻辑或 SQLite schema。
- 不引入 TanStack Query、外部图表库、外部数据库、消息队列或独立前端服务。
- 不使用 localStorage/sessionStorage 持久化语言或主题。
- 不把 API 地址或后端端口写死进浏览器代码。

## 影响
- specs/board:看板前端实现形态从单文件 HTML 改为构建产物;新增 path 路由与 nuqs search param 规则。
- docs/architecture/module-map.md:更新 M2 边界,移除“无构建步骤”,保留同源相对 API 与禁止本地存储。
- AGENTS.md / 部署与开发文档:增加前端构建、开发服务器、Docker 多阶段说明。
- CI:增加 node 安装和 `frontend` 构建检查。
