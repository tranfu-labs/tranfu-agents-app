# 设计:root-docker-entrypoint

## 部署入口
Docker 入口统一放在仓库根目录:

| 文件 | 职责 |
|---|---|
| `Dockerfile` | 构建单容器 FastAPI collector + dashboard 服务 |
| `compose.yml` | 本地/服务器 Docker Compose 启动入口 |
| `.env.example` | 部署环境变量模板 |
| `.dockerignore` | 控制 Docker 构建上下文 |

## Dockerfile
- `server/requirements.txt` 单独复制,用于依赖层缓存。
- 只复制运行时必要内容:`server/`、`dashboard/`、`install.sh`、`shims/`。
- 容器以非 root 用户 `tranfu` 运行。
- 默认 `TF_DB=/data/tf.db`、`PORT=8788`,保留 ADR-0008 端口约束。

## Compose
- 默认 `docker compose up -d --build` 即可从根目录启动。
- 继续使用命名卷 `tf-data` 持久化 `/data`。
- 支持通过 `TF_PORT` 调整宿主机暴露端口,容器内端口仍固定为 8788。
- `env_file` 默认读取 `.env`,也支持用 `TF_ENV_FILE=.env.example` 做配置解析验证。
- 添加 `/healthz` healthcheck,不引入 curl/wget 等额外系统包。
