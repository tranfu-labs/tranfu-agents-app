# 变更提案:add-read-access-control(看板读侧访问控制)

- 状态:Partially implemented(部分实现)
- 关联:ADR-0002(写侧 TF_KEY)、**ADR-0012(内容捕获硬闸,已落地)**、ADR-0011(身份令牌)、specs/board、specs/ingest、DEPLOY.md「D. 访问控制」

## 进度(2026-06-02 更新)
- ✅ **内容捕获硬闸已实现**(ADR-0012):服务端用 `TF_READ_KEY`(非空)或 `TF_READ_AUTH=1`
  判断读侧是否受保护;未受保护时**丢弃** `input/output/instructions/memory` 不予存储。
  DEPLOY.md「D2」已写入带放行清单的标准步骤。
- ⬜ **方案 A(边缘鉴权)** 仍是首选,属部署侧配置(Cloudflare Access / Caddy),见 tasks。
- ⬜ **方案 B(应用内读侧中间件)** 未实现:目前 `TF_READ_KEY` 仅作"读侧已就位"的信号,
  **尚未**对 `/` 与 `/api/*` 强制校验 Cookie/Bearer。若将来脱离边缘平台部署再落地。

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
