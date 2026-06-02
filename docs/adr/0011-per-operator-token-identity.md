# ADR-0011 per-operator 令牌身份(轻量入职注册,不做账号体系)

- 状态:Accepted
- 关联:ADR-0001(单容器/无账号库)、ADR-0002(团队写凭证 TF_KEY)、PROTOCOL.md §4

## 背景 / 问题
只有团队级 `X-TF-Key` 时,`operator` 字段是**完全自证**的:任何拿到团队密钥的人都能发
`"operator":"alice"` 冒充别人上报。对一个"治理 / 可见性"工具,这意味着看板数据**无法可靠归因到真人**。

## 决策
在团队密钥之上增加 **per-operator 令牌**(`X-TF-Token`),走一个**轻量入职注册**流程,
**不引入登录页 / 会话 / 多租户 / 账号库**(与 ADR-0001 一致):

- 新增一张 `operators(operator, token_hash, created)` 绑定表,服务端**只存 sha256(token)**。
- `POST /v1/enroll`(团队密钥鉴权)为某 operator 签发一次性明文令牌,响应里只出现一次。
- 上报时带 `X-TF-Token`;服务端校验 token 绑定的 operator == body 的 `operator`,
  不一致 → 403。匹配则事件标 `verified=true`。
- `TF_REQUIRE_TOKEN=1` 开启强制归因;关闭时(默认,向后兼容)允许自证但标 `verified=false`,
  看板显示"未验证"。

## 后果
- ✅ 看板数据可归因到真人,且未破坏"无账号体系"的取舍。
- ✅ 向后兼容:不开强制时旧 shim 照常工作。
- 约束:令牌明文仅签发时可见;丢失需重新 enroll(覆盖旧绑定)。
- 约束:`operator` 永远不得被当作可信身份凭证,除非 `verified=true`。
