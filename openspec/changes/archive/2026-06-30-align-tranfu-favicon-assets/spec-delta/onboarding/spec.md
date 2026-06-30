# spec-delta：onboarding

## 修改

### 根静态 icon 分发
`server/routes/onboarding.py` MUST 从构建后的 `frontend/dist` 根目录提供 TRANFU//AGENTS head/manifest 引用到的浏览器与 PWA icon 文件，包括未版本化兼容文件与版本化实体文件。

版本化 icon 文件 MUST 走与既有根静态资源相同的白名单与路径穿越保护；不得通过 SPA fallback 服务带点静态路径。

## 新增可验证行为

- `GET` / `HEAD` `/favicon-20260626.ico` 返回 200，content-type 为 `image/x-icon`。
- `GET` / `HEAD` `/favicon-32x32-20260530.png`、`/favicon-16x16-20260530.png`、`/apple-touch-icon-20260530.png`、`/android-chrome-192x192-20260530.png`、`/android-chrome-512x512-20260530.png` 返回 200，content-type 为 `image/png`。
- 未被白名单允许的带点根路径仍返回 404，不落入 SPA 深链 fallback。
