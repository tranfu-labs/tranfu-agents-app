# 设计：ci-ghcr-image-publish

## 方案

### Workflow 结构
新增 `.github/workflows/deploy.yml`，与现有 `.github/workflows/ci.yml` 并存、互不依赖。两个 workflow 职责分工：

| Workflow | 触发 | 职责 |
|---|---|---|
| `ci.yml`（已存在）| PR + push main | 编译检查 + pytest，保护 PR 质量 |
| `deploy.yml`（新增）| push main + `workflow_dispatch` | 内嵌 pytest 卡口 → build → push GHCR |

`deploy.yml` 自带 pytest 卡口（不依赖 ci.yml），目的是"坏代码不会污染 GHCR"。前端 build 天然在 Dockerfile 第一阶段执行，失败则整次 build 失败，无需在 workflow 单独跑一遍。

### Job 步骤
```
checkout
  ↓
setup-python 3.11 + setup-node 20（与 ci.yml 一致）
  ↓
pip install server + tests reqs；npm ci --prefix frontend（前端 install 是为了 lockfile 校验，不构建）
  ↓
pytest tests/ -q   ← 卡口；失败则不进入 build
  ↓
docker/setup-buildx-action@v3
  ↓
docker/login-action@v3 with GITHUB_TOKEN
  ↓
docker/build-push-action@v6
    context: .
    platforms: linux/amd64
    push: true
    tags:
      ghcr.io/${{ github.repository }}:latest
      ghcr.io/${{ github.repository }}:${{ github.sha }}
    cache-from/to: type=gha
```

### 权限与 Secrets
- `permissions: { contents: read, packages: write }`：让 `GITHUB_TOKEN` 推 GHCR，不需要额外 PAT。
- 本阶段**不加** `COOLIFY_WEBHOOK` / `COOLIFY_TOKEN`。

### 镜像内容审计
现有 `Dockerfile`（多阶段）已经只 COPY 运行时必需物：`server/`、`frontend/dist`（从 builder 阶段）、`install.sh`、`shims/`、`llms.txt`、`robots.txt`。
现有 `.dockerignore` 已排除 `.env`、`*.db*`、`docs/`、`openspec/`、`tests/`、`*.md`、`LICENSE` 等。本变更不修改这两个文件，仅在 tasks 中加一项"用 `docker run --entrypoint sh ... -c 'ls -la /app'` 抽查镜像内容、确认无敏感物"作为公开化前关卡。

## 权衡

### 为什么不把 deploy.yml 拆成"test job + build job (needs: test)"
两 job 写法在跨 job artifact / cache 共享上更费手，且仓库已经有独立的 ci.yml 在 PR 阶段强卡测试，main 上 deploy.yml 内嵌的这层 pytest 主要兜底"PR 之间漂移"或"绕过 PR 直推 main"。一个 job 串行更直观。

### 为什么 pytest 之前必须先 `npm --prefix frontend run build`
`tests/test_protocol.py::test_spa_deep_links_do_not_swallow_system_routes` 会请求 `/`、`/agents`、`/agent/...` 等 SPA 深链路由并断言 200。server 实现是把这些深链回退到 `frontend/dist/index.html`——所以 pytest 在 runner 上必须先看到 `frontend/dist` 才能通过。第一版 design 误以为"前端 build 天然在 Dockerfile 第一阶段跑、无需重复"——这只对**镜像构建**成立，对**测试卡口**不成立，pytest 跑在 docker build 之前。ci.yml 同样先 `npm run build` 再 pytest，deploy.yml 沿用这个顺序。

### 为什么用 `:latest` + `:${{ github.sha }}` 两个 tag、不用 short-sha
GitHub 文档示例和 GHCR 工具普遍用完整 SHA；本阶段不接 Coolify 自动部署，回滚 tag 由人查 commit hash 精确指定，full SHA 更明确。短 SHA 留待后续如有需要再加。

### 为什么 amd64 单平台
当前部署机是国内云（阿里云/腾讯云类）大概率 amd64。多平台 buildx 会让单次构建至少翻一倍时间，且阶段一不需要。后续接 ARM 机器再加 `linux/arm64`。

### 为什么这次不接 Coolify webhook
用户明确"先一步一步来"。GHCR 推送链路独立可验证（`docker pull` 即测），先稳定这一段；下一阶段再做 compose 切换 + webhook 自动部署。把切换面缩小，回滚边界清晰。

### 为什么 `checkout` 用 v4 不是 v6
原调研文档写 `actions/checkout@v6`；查 actions/checkout 当前稳定主线是 v4（v6 尚未正式发布）。改用 v4 保险，和现有 ci.yml 一致。

### 为什么 `.dockerignore` 的 `*.md` 通配不调整
`*.md` 会把 `shims/*/README.md`、`shims/mcp/README.md` 等排除出镜像。这些 README 是开发说明，不是 server 在运行时通过 `/shims/<f>` 路由暴露的运行物（路由暴露的是 `tf_*.py` / `tf-run` / `manifest` 等具体文件）。维持现状，公开镜像更干净。

## 风险

| 风险 | 缓解 |
|---|---|
| GHCR 推送失败（首次 package 不存在）| `packages: write` 已配；docker/build-push-action 自动创建 package；首次成功后 owner 手动改 public |
| pytest 在 main 上挂掉、阻断镜像发布 | 这是期望行为：质量门挡住坏镜像。回退路径：手动 `workflow_dispatch` 重跑或先修复测试 |
| 部署机走 proxy 拉 GHCR 不稳 | 不在本阶段处理；阶段一只要"手动 pull 成功一次"即视为通过，proxy 稳定性是基础设施问题 |
| 公开化后镜像内容被外部扫描发现敏感物 | 任务清单中含"docker run 抽查镜像内容"一关，public 切换在抽查通过后执行 |
| GHA cache 跨 workflow 互踩 | ci.yml 没用 docker buildx cache，deploy.yml 独占 `type=gha` 命名空间，无冲突 |
| 后续 change 删除 ci.yml 时漏删 deploy.yml 的 pytest 步骤 | 两边 pytest 步骤独立写出来，不互引；下个 change 自然不受影响 |

## 回滚

只有一个文件需要回滚：删除 `.github/workflows/deploy.yml`，下次 push 不再触发推送。已发布的 GHCR 镜像可留作历史 tag，也可在 Packages 页手动删除版本。AGENTS.md 的小改单独 revert。
