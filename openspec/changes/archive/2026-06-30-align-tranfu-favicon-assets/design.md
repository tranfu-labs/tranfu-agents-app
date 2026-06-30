# 设计：align-tranfu-favicon-assets

## 方案
### 静态资源
- 从 `https://tranfu.com/` 当前公开 icon 链路下载同款资源，保存到 `frontend/public/`：
  - `favicon-20260626.ico`
  - `favicon-32x32-20260530.png`
  - `favicon-16x16-20260530.png`
  - `apple-touch-icon-20260530.png`
  - `android-chrome-192x192-20260530.png`
  - `android-chrome-512x512-20260530.png`
- 保留现有 `favicon.ico`、`favicon-32x32.png`、`favicon-16x16.png`、`apple-touch-icon.png`、`android-chrome-*.png`，避免旧缓存和旧文档链接失效。

### HTML head
- `frontend/index.html` 继续使用 `<link rel="canonical">` 当前部署域名作为绝对 URL 基准。
- favicon/touch icon 链路改为版本化本地资源：
  - `<link rel="shortcut icon" ...>`
  - `<link rel="icon" ... sizes="any">`
  - 32/16 PNG icon
  - Apple touch icon 与 precomposed touch icon
- 从 favicon 候选里移除 `favicon.svg` 的 `<link rel="icon" type="image/svg+xml" ...>`，因为浏览器可能优先选 SVG；保留 `frontend/public/favicon.svg` 文件和 JSON-LD `publisher.logo` 对它的引用，继续满足 1:1 symbol logo 约定。
- `og:image`、`twitter:image`、`link rel="image_src"` 与 JSON-LD `publisher.logo` 不做功能性变更，避免把“ico 效果”扩大成社交主图重做。

### PWA manifest
- `manifest.json` 保持项目名称、描述、`theme_color` / `background_color`。
- icons 改为版本化本地资源的部署域名绝对 URL，继续包含 `180x180`、`192x192`、`512x512`。

### 服务端根静态文件
- `server/routes/onboarding.py` 的 `_ROOT_STATIC_FILES` 加入新增版本化文件。
- 为新增版本化 icon 增加 `GET` / `HEAD` 路由，复用 `_frontend_root_static()` 的白名单、路径穿越保护与 MIME 处理。

### 测试与验证
- 服务端单测：覆盖新增版本化 root static 路径 `GET`/`HEAD` 可取、返回正确 content-type，并保持未知带点路径 404。
- Head 静态检查：构建后的 HTML favicon 候选不再包含 `type="image/svg+xml"`，且包含 `shortcut icon` 与版本化 `.ico`。
- 构建/静态验证：
  - `file frontend/public/favicon-20260626.ico ...` 确认 ico/png 编码；
  - `npm --prefix frontend run build`；
  - `python -m py_compile server/*.py server/routes/*.py`；
  - 若已有相关 pytest，运行静态路由相关测试或全量 `pytest tests/`。
- AI 验证流程：本地启动服务或用 TestClient 打 `/favicon-20260626.ico`、`/apple-touch-icon-20260530.png`、`/manifest.json`，检查状态码、content-type 与 manifest icon URL。

## 权衡
- 使用版本化实体文件名而不是 query 参数，符合官网与社交预览缓存刷新经验。
- 保留未版本化文件，避免兼容风险；新版 head/manifest 优先使用版本化资源。
- 不直接引用 `https://tranfu.com/...`，遵守项目要求：本项目网站 head 图标必须使用 `frontend/public/` 本地资源与本项目部署域名。

## 风险
- 浏览器或 IM 平台可能缓存旧 favicon。版本化文件名能降低新缓存命中旧资源的概率；旧未版本化路径继续可取，回滚时只需恢复 head/manifest 链路。
- 如果未来部署域名变化，现有 head 中的绝对 URL 仍需按项目既有方式同步更新；本变更不改变域名策略。
