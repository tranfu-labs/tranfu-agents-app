# 设计:frontend-react-rewrite

## 锁定决策
- 技术栈:Vite + React + TypeScript + react-router + nuqs。
- 路由:BrowserRouter path URL,服务端提供 SPA fallback。
- 数据层:保留现有 fetch + 轮询节奏,用 React hook 封装;不引入 TanStack Query。
- 交付:Docker 多阶段构建,运行镜像只含 FastAPI + `frontend/dist`。
- 外观:迁移现有 CSS 变量和 className,将模板字符串渲染迁到 JSX。

## 路由
| URL | 视图 | 数据来源 |
|---|---|---|
| `/` | Pods 看板 | `/api/state` |
| `/agents` | Agents 列表 | `/api/state` |
| `/agent/:key` | 单 agent 详情 | `/api/state` 中的合并卡片 |
| `/skills` | SKILLS 总览 | `/api/skills?days={win}` |
| `/skill/:name` | 单 skill 详情 | `/api/skill/{name}` |

`key` 与 `name` 统一经 `encodeURIComponent` / react-router param decode 处理,支持中文和空格。

## nuqs search params
`/skills` 使用以下参数:
- `win`:7 / 30 / 90,默认 30,对应接口 `days`。
- `rt`:runtime 过滤,默认空。
- `src`:来源过滤,默认空。
- `q`:skill 名搜索,默认空。
- `sort`:排序列,默认 `sessions_30d`。
- `dir`:排序方向,`asc` / `desc`,默认 `desc`。

筛选变化使用 replace,避免污染历史;进入详情和切顶级 tab 使用 push。

## 前端目录
```
frontend/
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    styles.css
    components/
    views/
    lib/
```

## 轮询
- `/api/state`:每 3 秒刷新;失败时使用内置 demo 数据并显示 demo badge。
- `/api/skills`:仅 `/skills` 激活时每 10 秒刷新;首次进入立即拉取。
- `/api/skill/{name}`:仅 `/skill/:name` 激活时每 10 秒刷新;首次进入立即拉取。
- 时钟每 1 秒刷新。

## 服务端
- 挂载 Vite 输出的 `/assets` 到 `frontend/dist/assets`。
- 保留所有 API / ingest / shim / install / health / llms / robots 路由。
- 最后注册 `GET /{full_path:path}` 返回 `frontend/dist/index.html` 作为 SPA fallback。
- catch-all 必须显式拒绝 API/系统前缀,避免未来路由顺序或挂载变化造成吞路由。

## 验证
- `npm --prefix frontend run build`
- `python -m py_compile server/app.py`
- `python -m pytest tests/ -q`
- TestClient 覆盖:
  - `/agent/<encoded>`、`/skills?...`、`/skill/<encoded>` 返回 SPA index。
  - `/api/*`、`/v1/*`、`/shims/*`、`/install.sh`、`/healthz` 不被 SPA fallback 吞掉。
  - `/shims/../server/app.py` 仍 404。
