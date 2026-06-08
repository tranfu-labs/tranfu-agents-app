# 任务:root-docker-entrypoint

- [x] 新增根目录 `Dockerfile`,保留单容器 + SQLite + 8788 约束。
- [x] 新增根目录 `compose.yml`,默认适配 Coolify / Traefik,Web 服务使用 `expose: 8788`。
- [x] 新增根目录 `.env.example`,迁移写侧密钥、身份归因、读侧鉴权配置。
- [x] 新增 `.dockerignore`,避免本地数据、密钥、文档、测试进入 Docker 构建上下文。
- [x] 删除旧位置 `server/Dockerfile`、`deploy/docker-compose.yml`、`deploy/.env.example`。
- [x] 同步 README/DEPLOY/UPDATE/DEV-SETUP/AGENTS/ADR 中的部署入口说明。
