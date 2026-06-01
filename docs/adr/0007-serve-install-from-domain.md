# ADR-0007 install.sh 与 shim 从看板域名分发(支持私有库)

- 状态:Accepted
## 背景
部署仓库 `tranfu-labs/tranfu-agents-app` 为私有,匿名 `raw.githubusercontent.com` 取 install/shim 会 404,
导致"一句话自然语言接入"无法落地。
## 决策
服务端新增 `GET /install.sh` 与 `GET /shims/{path}`(带目录穿越防护);`install.sh` 的下载源改为
`${SERVER%/}/shims`。使用者一律从**看板域名**安装,不依赖 GitHub 可见性。
## 后果
- ✅ 私有库也能一键装;接入链路只依赖看板域名(始终可达)。
- 约束:服务端必须随仓库提供这两条路由;`/shims` 仅读 `shims/` 目录内文件。
