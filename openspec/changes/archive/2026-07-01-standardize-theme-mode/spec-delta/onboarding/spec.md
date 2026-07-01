# spec-delta：onboarding

## 修改

### 根静态主题初始化脚本
`server/routes/onboarding.py` MUST 从构建后的 `frontend/dist` 根目录提供看板 HTML head 引用的同源主题初始化脚本 `/theme-init.js`。

该文件 MUST 走与既有根静态资源相同的白名单与路径穿越保护；不得通过 SPA fallback 服务带点静态路径。

## 新增可验证行为
- `GET` / `HEAD` `/theme-init.js` 返回 200，content-type 为 JavaScript。
- 未被白名单允许的带点根路径仍返回 404，不落入 SPA 深链 fallback。
