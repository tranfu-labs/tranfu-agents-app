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
- [x] `server/app.py`:读 `TF_READ_KEY`(作为"读侧已就位"信号,用于内容捕获硬闸)。
- [ ] 加只读鉴权中间件(放行写/安装/探活路径)——**未实现**,目前仅靠信号位,未强制校验 `/api/*`。
- [ ] `/` 提供极简口令输入 → 写 `tf_read` Cookie。
- [ ] TestClient:无令牌取 `/api/state`→401;带令牌→200;`/v1/events` 不带读令牌→仍可 POST。
- [x] 文档:`.env.example` 增加 `TF_READ_KEY`/`TF_READ_AUTH`(可空);DEPLOY「D」补说明。
- [x] 记录决策:新增 **ADR-0012**(内容捕获硬闸,服务端强制)。

## 通用
- [x] 仅在确认读侧受保护后,才允许存储 `input/output/instructions/memory`——
      由服务端硬闸强制(ADR-0012):未声明读侧鉴权则丢弃这些字段。
