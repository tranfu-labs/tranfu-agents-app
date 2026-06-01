# 变更提案:add-read-access-control(看板读侧访问控制)

- 状态:Proposed(设计中,未实现)
- 关联:ADR-0002(写侧已有 TF_KEY)、specs/board、specs/ingest、DEPLOY.md「D. 访问控制」

## 背景 / 问题
看板默认"谁有网址谁就能看"。写入有 `TF_KEY` 保护,但**读取(看板页 + `/api/state`)无鉴权**。
在对全员开放、尤其在开启敏感上报(`TF_CAPTURE_CONTENT` / `TF_REPORT_MEMORY`)之前,需要给"读"加一道门。
当前线上 `tranfu-agents-app.tranfu.com` 经 Cloudflare(Caddy/Tunnel)暴露,具备在边缘加 Access 的条件。

## 目标
- 让看板页与只读 API 仅对授权成员可见。
- **绝不**因此挡住 agent 写入(`POST /v1/events`)与安装分发(`/install.sh`、`/shims/*`)。
- 优先用边缘方案(Cloudflare Access / Caddy Basic Auth),尽量少改应用代码。

## 非目标
- 不做账号体系/多租户;不引入登录数据库(与 ADR-0001 单容器一致)。
- 不改变写侧 `TF_KEY` 机制。

## 方案概述(详见 design.md)
首选 A:**边缘鉴权**——在 Cloudflare Access(或 Caddy basicauth)对受保护路径加策略,放行 `/v1/events`、`/install.sh`、`/shims/*`、`/healthz`。
备选 B:**应用内只读令牌**——服务端新增 `TF_READ_KEY`,对 `/` 与 `/api/*` 校验(Cookie/Authorization),其余放行。

## 影响
- specs/board:为只读接口增加"可选读侧鉴权"规则(见本 change 的 spec delta)。
- DEPLOY.md「D」从建议升级为带默认配置的步骤。
