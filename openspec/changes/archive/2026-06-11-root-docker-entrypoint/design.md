# 设计:root-docker-entrypoint

## 部署入口
Docker 入口统一放在仓库根目录:

| 文件 | 职责 |
|---|---|
| `Dockerfile` | 构建单容器 FastAPI collector + dashboard 服务 |
| `compose.yml` | Coolify / Traefik Docker Compose 启动入口 |
| `.env.example` | 部署环境变量模板 |
| `.dockerignore` | 控制 Docker 构建上下文 |

## Dockerfile
- `server/requirements.txt` 单独复制,用于依赖层缓存。
- 只复制运行时必要内容:`server/`、`dashboard/`、`install.sh`、`shims/`。
- 容器以非 root 用户 `tranfu` 运行。
- 默认 `TF_DB=/data/tf.db`、`PORT=8788`,保留 ADR-0008 端口约束。

## Compose
- Web 服务不发布宿主机端口,用 `expose: 8788` 交给 Coolify / Traefik 反向代理。
- 继续使用命名卷 `tf-data` 持久化 `/data`。
- 环境变量通过 Compose 变量替换传入;本地可用 `.env`,Coolify 可用应用环境变量。
- 添加 `/healthz` healthcheck,不引入 curl/wget 等额外系统包。
