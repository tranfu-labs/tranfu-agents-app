# spec delta:board(本变更新增/修改的规则)

> 合入后并入 `openspec/specs/board/spec.md`。

## 新增规则(MUST)
- 当启用读侧访问控制时,`GET /`、`GET /api/state`、`GET /api/agent/{key}` 仅对授权访问者可见。
- 无论读侧如何配置,以下路径**必须保持可匿名访问**:`POST /v1/events`(凭 `X-TF-Key`)、`GET /install.sh`、`GET /shims/{path}`、`GET /healthz`。
- 方案 B 实现时:`TF_READ_KEY` 为空 = 不启用(行为同现状);非空则对上述只读路径要求匹配令牌。

## 可验证行为(新增)
- 启用后:匿名 `GET /api/state` → 拒绝;授权后 → 200 JSON。
- 启用后:匿名 `POST /v1/events`(带正确 `X-TF-Key`)→ 仍 200。
