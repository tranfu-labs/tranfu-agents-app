# 任务:add-read-access-control

## 方案 A(边缘)
- [ ] 在 Cloudflare Access 建应用策略(host = agents 域名),允许公司邮箱/SSO。
- [ ] 配置 Bypass:`/v1/events*`、`/install.sh`、`/shims/*`、`/healthz`。
- [ ] 验收:
  - [ ] 未登录访问 `/` 与 `/api/state` → 被拦/跳登录。
  - [ ] `curl -XPOST .../v1/events -H X-TF-Key:..` 仍 200(关键)。
  - [ ] `curl .../install.sh`、`.../shims/tf_hook.py` 仍可取。
- [ ] 更新 DEPLOY.md「D」为带放行清单的标准步骤。

## 方案 B(应用内,若需要)
- [ ] `server/app.py`:读 `TF_READ_KEY`;加只读鉴权中间件(放行写/安装/探活路径)。
- [ ] `/` 提供极简口令输入 → 写 `tf_read` Cookie。
- [ ] TestClient:无令牌取 `/api/state`→401;带令牌→200;`/v1/events` 不带读令牌→仍可 POST。
- [ ] 文档:`.env.example` 增加 `TF_READ_KEY`(可空);DEPLOY/UPDATE 补说明;新增 ADR-0010。

## 通用
- [ ] 仅在确认读侧受保护后,才允许开启 `TF_CAPTURE_CONTENT` / `TF_REPORT_MEMORY`。
