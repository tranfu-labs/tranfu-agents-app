# 变更提案：ci-ghcr-image-publish（GitHub Actions 构建并发布镜像到 GHCR）

- 状态：Proposed
- 关联：ADR-0001(单容器 + SQLite)、Dockerfile、compose.yml、.github/workflows/ci.yml、AGENTS.md

## 背景 / 问题
当前部署是 Coolify 拉源码后在部署机上 `docker build`。带来两个问题：
1. 部署机（国内 Coolify 宿主）在构建期既要装 `python:3.12-slim` 依赖，又要起 `node:20-slim` 跑 `npm ci + vite build`，每次部署占大量 CPU / 网络 / 内存。
2. 构建产物只存在于本机，缺少跨机器复用、缺少明确可回滚的版本工件。

GitHub runner 上构建是免费、稳定、和源码就近的。把构建迁过去，部署机只剩 `docker pull`。

## 目标（仅本次第一阶段）
- 仓库根目录新增 `.github/workflows/deploy.yml`：push `main` → 跑 pytest 卡口 → 构建多阶段 Docker 镜像 → 推送到 `ghcr.io/tranfu-labs/tranfu-agents-app`，tag 含 `latest` + commit SHA。
- 首次成功后把 GHCR package 改成 **public**（已与维护者确认可公开，且不可逆）。
- 复核 `Dockerfile` 和 `.dockerignore`，确认镜像内容不含 `.env` / `tf.db*` / `docs/` / `openspec/` / `tests/`。
- AGENTS.md 加一句指明镜像地址 + 发布机制。

## 非目标（明确切走，留给下一个 change）
- 不修改 `compose.yml`、不动 Coolify 应用、不接 Coolify deploy webhook、不加 `COOLIFY_WEBHOOK` / `COOLIFY_TOKEN` secrets。
- 不改 DEPLOY.md / UPDATE.md 的 Coolify 操作流程——本阶段 Coolify 仍按现状 build 部署，GHCR 镜像作为"备用 + 验证"。
- 不引入 ACR / 镜像中转。部署机走已有 proxy 直拉 GHCR，proxy 不在本仓库范畴。

## 影响
- **运行行为**：零变化。镜像构建链路从"Coolify 本地 build"变成"GitHub runner build → 推 GHCR"，但本阶段 Coolify 仍然走 `compose.yml` 的 `build:` 路径，运行时容器与现状完全一致。
- **CI 资源**：GitHub Actions 公共仓库 + public package 免费；amd64 单平台 build + GHA cache，预计单次 3-6 分钟。
- **对外行为**：仓库 Packages 出现 `tranfu-agents-app` 容器镜像；公开化后任何人可匿名 pull（与仓库源码同等可见性，无新增信息暴露）。
- **未来 change**：第二阶段 `ci-coolify-pull-image`（暂名）会把 Coolify 切到 image: + webhook 自动部署，依赖本阶段镜像稳定可拉。
