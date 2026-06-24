# 任务：ci-ghcr-image-publish

## 实施
- [ ] 新增 `.github/workflows/deploy.yml`：`on: push.main + workflow_dispatch`；权限 `contents: read, packages: write`；步骤 = checkout → setup-python/node → install deps → pytest → setup-buildx → login GHCR(GITHUB_TOKEN) → build-push-action 推 `:latest` + `:${{ github.sha }}`、`platforms: linux/amd64`、`cache: type=gha`。
- [ ] 在 AGENTS.md 的"项目结构"或"常用命令"节加一行：镜像由 `.github/workflows/deploy.yml` 推送到 `ghcr.io/tranfu-labs/tranfu-agents-app:latest`，回滚见 `:${{ github.sha }}` tag。

## 验证（AI 验证流程）
- [ ] commit + push main，Actions 页面 `Build and Publish to GHCR` workflow 跑绿（pytest 通过、镜像推送成功）。
- [ ] 仓库右侧 Packages 出现 `tranfu-agents-app` container 包（首次为 private）。
- [ ] 抽查镜像内容：`docker run --rm --entrypoint sh ghcr.io/tranfu-labs/tranfu-agents-app:latest -c 'ls -la /app && echo --- && ls -la /app/server /app/frontend/dist /app/shims | head -60 && echo --- && find /app -name ".env*" -o -name "*.db" -o -name "tf.db*" 2>/dev/null'`——必须看到 server/、frontend/dist/、shims/，必须**不**出现 `.env*` / `*.db` 任何匹配。
- [ ] 抽查通过后，到 GitHub `tranfu-labs` 组织 → Packages → `tranfu-agents-app` → Package settings → Danger Zone → Change visibility → Public。**记录此操作不可逆。**
- [ ] 部署机走 proxy 执行 `docker pull ghcr.io/tranfu-labs/tranfu-agents-app:latest`——成功 = 第一阶段完成。
- [ ] `workflow_dispatch` 在 Actions 页面手动触发一次，确认手动重跑可用（用于将来回滚）。
