# specs/onboarding delta:localize-tranfu-favicon

## 修改:根静态资源分发
- 服务端根路径 MUST 支持 GET/HEAD 访问前端 public 中用于网站 head 的版本化 favicon 资源:
  `/favicon-20260626.ico`、`/favicon-32x32-20260530.png`、`/favicon-16x16-20260530.png`、
  `/apple-touch-icon-20260530.png`、`/android-chrome-192x192-20260530.png`、
  `/android-chrome-512x512-20260530.png`。
- 上述路径 MUST 复用现有 `_frontend_root_static()` 安全检查,只从 `frontend/dist` 内取文件,并按扩展名返回正确 MIME。

## 可验证行为新增
- `GET /favicon-20260626.ico` 返回 200 且 `content-type` 含 `image/x-icon`。
- `HEAD /favicon-32x32-20260530.png` 返回 200 且 `content-type` 含 `image/png`,响应体为空。
