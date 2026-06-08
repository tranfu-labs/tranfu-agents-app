# 变更提案:root-docker-entrypoint(根路径 Docker 部署入口)

- 状态:Implemented
- 关联:ADR-0001(单容器 + SQLite)、ADR-0008(默认端口 8788)、DEPLOY.md、README.md

## 背景 / 问题
当前 Dockerfile 位于 `server/`,Compose 与 `.env.example` 位于 `deploy/`。管理员部署时需要进入子目录或显式指定
`-f deploy/docker-compose.yml`,容易与文档中已有的根目录命令混用。

## 目标
- 将 Docker 部署入口集中到仓库根目录:`Dockerfile`、`compose.yml`、`.env.example`。
- 保持单容器、SQLite 卷 `tf-data`、默认端口 8788 不变。
- 优化镜像构建缓存与运行权限,降低部署误用风险。

## 非目标
- 不改变服务端 API、事件协议、数据库 schema 或看板行为。
- 不引入外部数据库、消息队列或独立前端构建步骤。

## 方案概述
- 根目录新增 `Dockerfile`,先复制 `server/requirements.txt` 安装依赖,再复制运行所需目录。
- 容器内创建非 root 用户 `tranfu`,并将 `/data` 用于 SQLite 持久化。
- 根目录新增 `compose.yml`,从当前目录构建,挂载 `tf-data:/data`,暴露 `${TF_PORT:-8788}:8788`。
- 根目录新增 `.dockerignore`,减少构建上下文并避免把 `.env`、本地数据库、文档和测试目录送入镜像上下文。
- 删除旧的 `server/Dockerfile`、`deploy/docker-compose.yml`、`deploy/.env.example`,文档统一为根目录命令。
