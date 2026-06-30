# 提案：align-tranfu-favicon-assets

## 背景
GitHub Issue 要求 TRANFU//AGENTS 使用与 `https://tranfu.com/` 一样的浏览器 ico 效果。已核对官网当前首页 head：

- `favicon-20260626.ico`
- `favicon-32x32-20260530.png`
- `favicon-16x16-20260530.png`
- `apple-touch-icon-20260530.png`
- `manifest.json` 内的 app icon 资源

本项目现有 icon 视觉像素与官网基本一致，但 head/manifest 链路仍使用未版本化文件名，且服务端根静态文件白名单只覆盖旧文件名。要让浏览器、收藏夹、PWA 与 IM/social crawler 更稳定地拿到同款 icon，需要把官网同款版本化资源落成本项目本地资源，并由本项目部署域名提供。

## 提案
1. 在 `frontend/public/` 增加官网同款版本化 icon 文件，并保留现有未版本化文件作为兼容兜底。
2. 更新 `frontend/index.html`：
   - 增加 `shortcut icon`；
   - favicon/png/apple-touch-icon 指向本项目部署域名下的版本化本地资源；
   - 移除 `favicon.svg` 作为浏览器 `rel="icon"` 候选，避免现代浏览器优先选择透明 SVG 而不是官网同款 ico；
   - 增加 `apple-touch-icon-precomposed`；
   - 不改页面内 logo，不改 `og:image` / `twitter:image` 分享主图；JSON-LD `publisher.logo` 继续使用本地 1:1 symbol SVG。
3. 更新 `frontend/public/manifest.json`，让 PWA icons 指向本项目部署域名下的版本化本地资源，并保持 `theme_color` 与 HTML `<meta name="theme-color">` 一致。
4. 更新 `server/routes/onboarding.py` 的根静态文件放行与路由，使版本化 icon 文件线上可直接 `GET` / `HEAD`。
5. 同步 README 的部署后 icon 探针，加入版本化 favicon/touch/PWA icon 路径。

## 影响
- 影响模块：`frontend/` 静态 head 与 public 资源、`server/routes/onboarding.py` 根静态资源分发、README 部署验证说明。
- 不影响数据协议、SQLite schema、shim 安装、事件上报、看板业务计算。
- 不引入外部运行期依赖；所有新增 icon 资源均由 `frontend/public/` 本地文件提供，禁止直接引用 `tranfu.com` 远端资源。
