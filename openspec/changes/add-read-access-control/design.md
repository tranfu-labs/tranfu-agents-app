# 设计:add-read-access-control

## 路径分级
| 路径 | 谁访问 | 鉴权 |
|---|---|---|
| `POST /v1/events` | agent(机器) | `X-TF-Key`(写,已存在);**必须放行边缘读鉴权** |
| `/install.sh`、`/shims/*` | 新机器安装 | 公开放行(否则装不了) |
| `/healthz` | 探活 | 公开放行 |
| `/`(看板)、`/api/state`、`/api/agent/*` | 团队成员(人) | **新增读鉴权** |

## 方案 A(首选):边缘鉴权,应用不改
- Cloudflare Access:对 `agents host` 建策略(公司邮箱/Google SSO);为 `/v1/events*`、`/install.sh`、`/shims/*`、`/healthz` 配 **Bypass**。
- 或 Caddy:对 `/` 与 `/api/*` 加 `basic_auth`,对上述路径不加。
- 优点:零代码、零状态;符合单容器约束。缺点:依赖边缘平台配置正确(放行清单是关键)。

## 方案 B(备选):应用内只读令牌
- 新增环境变量 `TF_READ_KEY`(为空=不启用,保持现状)。
- 中间件:当 `TF_READ_KEY` 非空时,对 `/` 与 `/api/*` 要求匹配(Cookie `tf_read` 或 `Authorization: Bearer`);
  `/v1/events`、`/install.sh`、`/shims/*`、`/healthz` 永远放行。
- `/` 提供一个极简输入框,提交后写 Cookie。
- 优点:自包含、可移植。缺点:增加少量代码与一处状态(Cookie)。

## 决策倾向
线上已在 Cloudflare 后 → **先用方案 A**;若将来脱离边缘平台部署,再落地方案 B(届时补 ADR)。

## 风险
- 最大风险:**把 `/v1/events` 也挡了**,导致全员上报失效。验收必须显式测这条仍可匿名 POST。
