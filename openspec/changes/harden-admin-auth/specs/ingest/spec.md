# 规格（delta）：ingest —— 写侧认证加固

事实来源：`server/app.py` 的 `check_auth` / `/v1/enroll` / `/v1/events`。本 delta 与 admin 域的「鉴权比较」「防爆破速率限制」条款保持一致，实现完成后合并回 `openspec/specs/ingest/spec.md`。

## 写侧钥匙比较（MUST）
- `TF_KEY`（请求头 `X-TF-Key`）比较 MUST 用常量时间比较（`hmac.compare_digest`），与管理钥匙一致、不得短路。

## 签发端点防爆破（SHOULD）
- `/v1/enroll`（凭 `TF_KEY` 签发持久 per-operator token）SHOULD 纳入与管理接口同类的按 IP 速率限制，遏制对写侧钥匙的在线猜测。
- `/v1/events` 高频上报路径 SHOULD 用更宽阈值或豁免，避免误伤正常心跳。
