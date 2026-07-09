# tranfu-coolify-ops skill 改造提案（GHCR 镜像模式）

> **状态**：讨论定稿、未动手。  
> **目标 skill**：`~/.claude/skills/tranfu-coolify-ops`  
> **驱动事件**：tranfu-agents-app 在 `dev` 分支引入 4 个 commit（`08614f1` / `9bea87e` / `aa7a9b2` / `06b58d6`），把部署方式从「Coolify 接 GitHub App 自己 build」改为「GitHub Actions build & push GHCR → Coolify Docker Image Application 拉镜像跑 → CI 末尾 curl Coolify deploy API」。本 skill 当前的 onboard 流程是围绕旧路径建的，要按新路径整体重写。  
> **目标 Coolify**：server **4.1.2** + coolify-cli **1.6.2**。所有 CLI / API 引用以这两个版本为准。

---

## 0. 讨论沉淀（背景与判断）

### A/B/C/D 四个判断（已拍板）

| 判断 | 选择 | 说明 |
|---|---|---|
| A：onboard 是新增场景还是替换原场景？ | **替换** | 旧 GitHub App 路径不再保留为可选；`scenarios/onboard-new-app.md` 整体重写。 |
| B：onboard 的成功标准到哪？ | **服务域名可访问** | 在 Coolify 上添加 Docker Image Application、端口/域名/env 都配齐，最终服务域名 `https://${prefix}-app.tranfu.com` 能 `curl -sSI` 拿到 2xx 才算完。 |
| C：`COOLIFY_APP_UUID` 怎么管？ | **是本 skill 的产物** | Coolify 上 create app 后才有 UUID，agent Edit 写进 `.github/workflows/deploy.yml`。TOKEN 是组织级前置，**只校验存在性**，不存在则强制终止要求用户去配。 |
| D：TOKEN 配在 Org 还是 repo？ | **Org 级 secret** | `COOLIFY_API_TOKEN` 是 tranfu-labs 组织 secret，全 `*-app` repo 共用。`COOLIFY_BASE_URL` 是 repo 级 secret（每个 repo 自己配，可能指向不同 Coolify 实例）。 |

### 1/2/3/4 四个拍板点（已拍板）

| 拍板点 | 选择 | 备注 |
|---|---|---|
| 1：`--environment-name` 默认值 | **`production`** | 除非用户在触发语里明说部署到 `dev`，否则 onboard 都落在 `production` environment。 |
| 2：写 env 用 sync 还是 update/create | **`coolify app env sync` + `trap EXIT shred`** | 临时 mktemp 写 KEY=VAL，sync 完用 `shred -u` 覆写删，保证退出路径清理。 |
| 3：敏感字段短 flag | **沿用 `-s`** | conventions.md 既有写法保留；核对 evidence 只验证了长 flag `--show-sensitive` 存在，但用户本机用过 `-s` 没问题。 |
| 4：GHCR 凭证前置怎么处理 | **不软探测，事后兜底** | Coolify 4.1.2 没有 API/CLI 管理 private registry，agent 不前置校验也不创 dummy 探测；首次部署若 GHCR 拉镜像挂掉，Phase 3 Step 11.b 通过 grep Docker 401/403 字串拦截并引到 prereq 文档。Phase 3 Step 11.a 同时用 `gh run watch` 盯 GitHub Actions run，覆盖「webhook 都发不过去」的失败链路。 |

---

## 1. 写时硬约束（先于一切改动）

### 提示词 0 — 全局硬约束

> 任何 `coolify` CLI 命令（命令名、子命令、flag 名、`--format` 输出字段名、API 端点路径、JSON 字段名）**都必须先对照 Coolify 4.1.2 / CLI 1.6.2 的源码或当期 OpenAPI 求证**，禁止凭旧版印象抄。求证渠道按优先级：
>
> 1. WebFetch coolify-cli 仓库 `v1.6.2` tag 的 `cmd/` 目录（Cobra 命令定义）。
> 2. WebFetch coolify 仓库 `v4.1.2` tag 的 `routes/api.php` + `openapi.yaml` + `app/Http/Controllers/Api/*` + `app/Models/Application.php` + `app/Enums/BuildPackTypes.php`。
> 3. 本机能连 Coolify 实例时直接 `curl ${BASE}/api/v1/openapi.json` 拉当期实例的 OpenAPI（**最权威**）。
> 4. CLI 本地求证 `coolify <topic> --help` / `coolify <topic> <verb> --help`。
>
> 任一处文档与实例 OpenAPI 不一致时**以实例 OpenAPI 为准**。求证后在对应 `commands/<topic>.md` 顶部留一行 `# verified against Coolify 4.1.2 OpenAPI @ <date>` 时间戳。

### 提示词 0bis — Server 版本固化

> SKILL.md `## Ownership` 段下方新增小节：
>
> **Server version pinning**：本 skill 当前固化对 **Coolify server 4.1.2** + **CLI 1.6.2** 的组合做验证。命中其它 server 大版本时（`coolify context list` 返回的实例 version 不是 `4.1.x`）→ 终止并提示用户先核对版本差异，**不要**在未验证版本上跑写动作（命令名/参数兼容性无保证）。

---

## 2. Coolify 4.1.2 / CLI 1.6.2 核对结果（动手时直接抄）

> 调研已完成，下面表格的每一格都有源码证据。改文件时**直接抄**，不要再凭印象写。

| # | 关键事实 | 落实位置 |
|---|---|---|
| 1 | CLI 命令是 `coolify app create dockerimage`（连写，**不是** `docker-image`）。`app` 是 `application` 别名。 | `commands/app.md` 新章节、scenario Step 6.1 |
| 2 | `app create dockerimage` 的 **required flags**：`--server-uuid`、`--project-uuid`、`--docker-registry-image-name`、`--ports-exposes`，以及 `--environment-name` 或 `--environment-uuid` 二选一。**`--name` 不 required**，但仍传 `${repo}`。 | `commands/app.md`、scenario Step 6.1 |
| 3 | `--docker-registry-image-tag` 默认 `latest`。dev 阶段**必须显式传 `dev`**。 | scenario 参数表、Step 6.1 |
| 4 | `--domains` 在 create 时直接可设。**不再单独 PATCH `docker_compose_domains`**（那是 dockercompose 专用，dockerimage 切换会被清空）。 | scenario Step 6.5 / Step 6.1 |
| 5 | 域名字段双轨：**写入用 `domains`**（comma-separated 字符串），**读出/DB 列叫 `fqdn`**。校验 GET 时 jq `.fqdn`。 | scenario Step 6.1、Step 11 完成判据 |
| 6 | API 端点 `POST /api/v1/applications/dockerimage` 是创建 Docker Image app 的**专属端点**（不是 `POST /applications` + type）。 | references 文档背景说明 |
| 7 | Coolify 4.1.2 **没有 private registry 的 API/CLI**（`routes/api.php` 零命中；CLI v1.6.2 `cmd/` 无对应子树）。GHCR 凭证只能 UI 手动配。 | Step 0.6 降级为人类前置 + Step 11.b 事后兜底 |
| 8 | `coolify context list --format json` 字段是 `name` / `fqdn` / `token` / `default`。**实例地址叫 `fqdn` 不叫 `url`**；token 默认 redact，需 `--show-sensitive`。 | Step 9.b BASE_URL 推断 |
| 9 | `coolify app deployments list <uuid> --format json` 的部署 UUID 字段叫 **`deployment_uuid`**（不是 `uuid` 也不是 `id`）。`created_at` 仍存在。 | scenario Step 11.b、`commands/app.md` 第 149 行 bug 修复 |
| 10 | `coolify app start --force` 对 dockerimage 应用 **会真的重新 pull tag**（`force=true` 含义是"不走 docker layer 缓存"）。打的端点是 `POST /api/v1/applications/{uuid}/start?force=true`。 | `references/existing-app-redeploy.md` 改写 |
| 11 | `POST /api/v1/deploy?uuid=...&force=...` 是 4.1.2 稳定端点（GET/POST 都接受），query param 名是 `uuid`（单数，支持 comma 批量），还有 `tag`/`pr`/`docker_tag`/`force`。 | scenario 背景说明、Step 11.a 失败分诊 |
| 12 | env 操作推荐用 **`coolify app env sync <app_uuid> --file <path>`**（diff + bulk upsert，幂等）。`--is-literal` 在 create/update/sync 三个动词都仍存在。 | scenario Step 8、SKILL.md 参数表 |
| 13 | dockerimage 应用**没有公开的 `volumes` API 字段**。compose.yml 里的 named volume 在 Coolify 上只能走 `custom_docker_run_options`（自由文本）或**网页 UI 上的 Persistent Storage**。 | scenario Step 6.5 预览面板 + 完成判据 |
| 14 | **`BuildPackTypes` enum 不含 `dockerimage`**。controller 在 `create_dockerimage_application` 里直接赋值绕过 enum。PATCH `/applications/{uuid}` 时**不要**把 `build_pack: "dockerimage"` 写进 body，会被 `Rule::enum` 拒。 | SKILL.md NEVER 段、scenario 背景说明 |

### 关键证据链接

- coolify-cli v1.6.2 `app create dockerimage` 源：<https://raw.githubusercontent.com/coollabsio/coolify-cli/v1.6.2/cmd/application/create/dockerimage.go>
- coolify v4.1.2 `routes/api.php`：<https://raw.githubusercontent.com/coollabsio/coolify/v4.1.2/routes/api.php>
- coolify v4.1.2 `ApplicationsController`：<https://raw.githubusercontent.com/coollabsio/coolify/v4.1.2/app/Http/Controllers/Api/ApplicationsController.php>
- coolify v4.1.2 `Application` model：<https://raw.githubusercontent.com/coollabsio/coolify/v4.1.2/app/Models/Application.php>
- coolify v4.1.2 `BuildPackTypes` enum：<https://raw.githubusercontent.com/coollabsio/coolify/v4.1.2/app/Enums/BuildPackTypes.php>
- coolify v4.1.2 `DeployController`：<https://raw.githubusercontent.com/coollabsio/coolify/v4.1.2/app/Http/Controllers/Api/DeployController.php>
- coolify-cli v1.6.2 `context list`：<https://raw.githubusercontent.com/coollabsio/coolify-cli/v1.6.2/cmd/context/list.go>
- coolify-cli v1.6.2 deployment model：<https://raw.githubusercontent.com/coollabsio/coolify-cli/v1.6.2/internal/models/deployment.go>
- coolify-cli v1.6.2 `app env sync`：<https://raw.githubusercontent.com/coollabsio/coolify-cli/v1.6.2/cmd/application/env/sync.go>

---

## 3. 文件一：`SKILL.md` 修改提示词

### 提示词 1.1 — frontmatter（第 2-22 行）

> - `version: 0.3.0` → `0.4.0`
> - `updated_at: 2026-06-24` → `2026-06-26`
> - description 段「GitHub App 路径，首次部署」**改为**「GHCR 镜像模式（GitHub Actions build & push GHCR → Coolify 拉镜像跑）首次接入」
> - 「不要用于」清单删掉「docker image 部署路径」一项（已成为正向流程）。

### 提示词 1.2 — 「这个 skill 不做什么」段（第 49-53 行）

> 删除「`docker image` 部署路径」对应的 NEVER 项；保留「NEVER 写 Dockerfile / compose.yml」。
> 末尾**新增三条 NEVER**：
>
> - **NEVER** 在 GitHub 仓库的 secret/variable 配置 UI 上替用户写入 token；只做存在性校验，缺失就终止并给出 settings URL。
> - **NEVER** 在 PATCH `/api/v1/applications/{uuid}` 时把 `build_pack: "dockerimage"` 写进 body。`BuildPackTypes` enum 不含此值，PATCH 会被 enum 校验拒。`dockerimage` 只能通过专属 create 端点 `POST /api/v1/applications/dockerimage` 写入（controller 直接赋值绕过 enum）。
> - **NEVER** 写 `.github/workflows/deploy.yml` 文件本身（归 `coolify-deploy` skill）。本 skill 只允许 Edit 该文件**单行** `env.COOLIFY_APP_UUID` 的值，且只在 Phase 3 Step 9.a。

### 提示词 1.3 — 场景路由表（第 74-78 行）

> 第一行触发词「用 GitHub App 部署新 app / onboard」**改为**「GHCR 镜像上 Coolify Docker Image Application / onboard」。
> 指向脚本仍是 `scenarios/onboard-new-app.md`（整体替换，不并行保留旧版）。

### 提示词 1.4 — 参数来源分类表（第 118-135 行）

> 整张表按下面**重写**：
>
> | 参数 | 来源 | 默认行为 |
> |---|---|---|
> | `--context` | `coolify context list` 的 default/active | 自动用 default |
> | `--server-uuid` | `coolify server list` 唯一一台 | 自动取；数量 ≠ 1 终止 |
> | `--project-uuid` | repo 名查 / 不存在则建（project 名 == repo 名） | 自动 |
> | `--environment-name` | 固定 `production` | **拍板 1**：除非用户触发语明说 `dev`，默认 `production` |
> | `--name` | 等于 repo 名 | 自动（不 required，但仍传） |
> | `--build-pack` | **隐式 `dockerimage`**（由 `app create dockerimage` 子命令决定，不显式传 flag） | 不传 |
> | `--docker-registry-image-name` | `ghcr.io/tranfu-labs/${repo}` | 自动 |
> | `--docker-registry-image-tag` | dev 阶段 `dev`、prod 阶段 `latest` | dev 阶段**必须显式传**（CLI 默认 `latest`） |
> | `--ports-exposes` | 从仓库 `compose.yml` 解析（**真生效**，不是占位） | 自动 |
> | `--domains` | 按 `${prefix}-app.tranfu.com:${PORT}` 模板推默认 | 自动出预览；用户预检阶段可改 |
> | compose.yml 内容来源 | agent 直接在 working dir 用 Read 读仓库根 `compose.yml`（**不再轮询 `docker_compose_raw`**） | 自动 |
> | env 值 | 用户触发时贴 `.env` 或 Step 6.6 循环索要；写入用 `app env sync` + `trap EXIT shred` 临时文件 | 自动 |
> | **Org 级 GitHub Actions 配置** `COOLIFY_API_TOKEN` (secret) | tranfu-labs Org secret | Step 0.5 校验**存在性**（agent 不写）；不存在则终止 |
> | **repo 级 GitHub Actions 配置** `COOLIFY_BASE_URL` (secret) | repo secret，值应等于 `coolify context list` 返回的 `.fqdn` | Step 9.b 校验**存在性**（agent 不写）；不存在则终止并给 `EXPECTED_BASE` 让用户自填 |
> | `.github/workflows/deploy.yml` 的 `env.COOLIFY_APP_UUID` | Phase 2 create app 的产物 | Phase 3 Step 9.a agent Edit 写入（**单行值修改**，非生成文件） |

### 提示词 1.5 — 「Agent 接触 GitHub 凭证」守则（第 140-143 行）

> 整段**重写**为：
>
> agent 在 onboard 流程内需要 `gh` 全程可用（必须 `gh auth status` 通过），用途**仅限**：
>
> 1. Step 0.5：Org 级 `COOLIFY_API_TOKEN` 存在性校验（`gh api orgs/tranfu-labs/actions/secrets/<NAME>`，端点只返回元数据不返回 value）
> 2. Step 9.b：repo 级 `COOLIFY_BASE_URL` 存在性校验（同上，repo 端点）
> 3. Step 11.a：盯 GitHub Actions run 结果 + 读失败 step 日志（`gh run watch --exit-status` + `gh run view --log-failed`）
>
> 仍然 **NEVER**：用 `gh` / `git clone` 读仓库源码（compose.yml 直接 Read 当前 working dir 即可，不走 GitHub）、写任何 secret、改任何 workflow 文件结构。
>
> ⚠️ `gh api ... actions/secrets/<NAME> --silent` 只能验证 secret **存在**——不能验证 value 非空、token 没过期/被 revoke、scope 够 deploy 权限、BASE_URL 真能联到。这些只能在 Step 11.a 真正 curl /deploy 时**才**暴露。Step 0.5 / 9.b 的价值是「早死」——值压根没配的 case 直接拦住，省一次 push dev → CI 半天才发现的来回。

### 提示词 1.6 — 引用文件列表（第 147-180 行）

> **新增**三条 reference 描述行：
>
> - `references/github-actions-coolify-org-token-precheck.md`：tranfu-labs Org 级 Actions secret `COOLIFY_API_TOKEN` 存在性校验流程；缺失终止文案与 GitHub settings URL。明文说明「存在 ≠ 有效」的边界。
> - `references/coolify-ghcr-registry-prereq.md`：**事后兜底文档**——Phase 3 Step 11.b grep 到 Docker `unauthorized` / `pull access denied` 时引到这里。Coolify 4.1.2 无 API/CLI 管理 private registry，配置只能走网页 UI；含 PAT scope（`read:packages`）+ 共享账户建议 + 配完后**不重做 onboard** 的 redeploy 命令。
> - `references/github-actions-run-watch-and-diagnose.md`：Step 11.a 用 `gh run watch --exit-status` 盯 CI run，按失败 step 名分诊（前置检查 / 测试 / build / 触发 Coolify 部署），每个 step 的兜底文案 + 引回路径。
>
> 已有 `scenarios/onboard-new-app.md` 的副本描述改为「GHCR 镜像模式 11 步流程：Org secret 校验 + 命名 + project + create dockerimage app（含域名 + ports）+ env sync + 写 workflow UUID + push dev + CI 兜底 + Coolify deployment 兜底」。

### 提示词 1.7 — example / bad-example（第 182-206 行）

> example 保留对 `scenarios/onboard-new-app.md` 的指向，不内嵌命令。
> bad-example：
>
> - 「错误做法 2」（agent 自己 `git clone` / `gh api 读源码`）**改写为**：「读 GitHub repo 源码内容仍禁止；用 `gh api` 做 Org/repo secret 存在性校验、用 `gh run watch` 盯 CI run 是允许的」。
> - **新增错误做法 5**：「agent 替用户 `git commit && git push origin dev`」——远端推送是用户专属的破坏性动作，必须留给用户。
> - **新增错误做法 6**：「agent 跑 `gh secret set COOLIFY_API_TOKEN ...` 帮用户写 Org secret」——凭证写入是组织级破坏性动作，必须用户在 GitHub UI 完成。
> - **新增错误做法 7**：「agent 创建 dummy app 探测 GHCR 凭证」——违反「先断言再动作」全局守则。

---

## 4. 文件二：`scenarios/onboard-new-app.md` 整体重写提示词

### 提示词 2.1 — 标题与开篇（第 1-14 行）

> 副标题改为「GHCR 镜像模式：tranfu-labs GitHub Actions 推 GHCR → Coolify Docker Image Application 拉镜像跑」。
> Phase 划分：
>
> - **Phase 1 · 前置校验与讨论**：context/server → Org TOKEN 校验（gh）→ 主机 GHCR 凭证（人类前置告知）→ URL/命名 → 同名 app → project → 读本地 compose.yml → 出预览 → 收 env → 等确认。
> - **Phase 2 · 写配置**：在 Coolify 上 create dockerimage application（带域名、ports；不部署）→ env sync。
> - **Phase 3 · 触发首次部署 + 双段兜底**：Edit `deploy.yml` 的 `COOLIFY_APP_UUID` → repo 级 BASE_URL secret 校验 → 提示用户 commit & push dev（agent 不推）→ Step 11.a `gh run watch` 盯 CI → Step 11.b 跟 Coolify deployment logs + grep 401/403。

### 提示词 2.2 — 触发 / 不触发 / 输入 / 输出（第 16-35 行）

> 「触发」段保留 GitHub URL，措辞「GitHub App 部署」改成「上 Coolify GHCR 镜像模式」。
> 「不触发」段删掉「用户想用 public 仓库 / deploy-key / Dockerfile / docker image 路径部署」（docker image 已是正向）。
> 「输入」新增：**用户当前 cwd 必须就是该仓库 working tree**（agent 要 Read `compose.yml` 和 Edit `deploy.yml`）。
> 「输出」新增 `${COOLIFY_APP_UUID-edited-in-workflow}`（已写入 deploy.yml 的事实），删除 `docker_compose_raw` 相关。

### 提示词 2.3 — 「设计动机」段（第 37-45 行）

> 整段**重写**为：
>
> agent 已经在仓库 working dir 里 → `compose.yml` 直接 Read，**不再**让 Coolify 替我们 git fetch、**不再**轮询 `docker_compose_raw`。
>
> 新流程依赖 4 条「不能错」的链路前置，按谁能自动校验分两类：
>
> **可前置自动校验（早死）**：
>
> 1. Org `COOLIFY_API_TOKEN` 存在 → Step 0.5 用 `gh api` 校验
> 2. repo `COOLIFY_BASE_URL` 存在 → Step 9.b 用 `gh api` 校验
> 3. `.github/workflows/deploy.yml` 的 `COOLIFY_APP_UUID` 行 → Step 9.a 由 agent Edit 写入
>
> **无法前置自动校验（事后兜底）**：
>
> 4. Coolify 主机加 ghcr.io private registry → Step 0.6 只「告知 + 不校验」，Step 11.b 通过 grep Docker 401/403 字串拦截
>
> **TOKEN/BASE_URL 存在 ≠ 有效**——Step 0.5/9.b 只能验存在性；token 过期/scope 错/BASE_URL 写错的情况只在 Step 11.a `gh run watch` 真正 curl /deploy 时**才**暴露。所以 Phase 3 不能只盯 Coolify logs，**必须** 11.a 先盯 CI run 再 11.b 跟 Coolify。

### 提示词 2.4 — Step 0.5（Org TOKEN 校验）

> 章节标题：`#### Step 0.5 — 校验 tranfu-labs Org 级 Coolify API token`
>
> ```bash
> gh auth status -h github.com >/dev/null
> gh api -X GET orgs/tranfu-labs/actions/secrets/COOLIFY_API_TOKEN --silent
> ```
>
> 404 / 失败终止文案：
>
> > tranfu-labs 缺 Org 级 secret `COOLIFY_API_TOKEN`。这是所有 `*-app` repo 共用的 deploy token，缺了首次 CI 一开始就 fail。
> > 去 <https://github.com/organizations/tranfu-labs/settings/secrets/actions> 配齐后再跑本流程（**Org 级一次性配置**，不要给本 repo 单独写 repo secret）。
>
> `gh` 不可用 / 未 `gh auth login` 的终止文案：要求用户先 `gh auth login`，**agent 不替用户登录**。
>
> ⚠️ 末尾加 disclaimer：`gh api --silent` 只验存在性。token value 不为空、未过期、未 revoke、scope 真够 deploy——只有 Step 11.a 真 curl /deploy 时才暴露。Step 0.5 的价值是早死，不是闭环验证。

### 提示词 2.5 — Step 0.6（GHCR 凭证人类前置）

> 章节标题：`#### Step 0.6 — 主机级 GHCR 凭证（一次性人类前置）`
>
> ⚠️ Coolify 4.1.2 不暴露 private registry 的 API/CLI，agent 没有可靠手段断言 ghcr.io 凭证存在。
> **本步骤不跑任何命令、不问用户「配了没」**，只做事实告知：
>
> > 首次 onboard 任何 tranfu-labs `*-app` 之前，运维同学必须手动到 Coolify 网页 UI 配一份 ghcr.io registry：
> >
> > - URL: `ghcr.io`
> > - Username: `tranfu-labs`（或共享 PAT 账户名）
> > - Token: GitHub PAT，scope = `read:packages`
> >
> > 之后所有 tranfu-labs `*-app` 共用，**本步骤跳过即可**。
> >
> > 本 skill 不会问、不会探测——问了无法验证是无效仪式，探测要真创资源违反全局守则。
> > 没配过的 case 会在 **Phase 3 Step 11.b** 通过 grep Docker registry 401/403 字串自动拦截，并引到 `references/coolify-ghcr-registry-prereq.md`。

### 提示词 2.6 — 旧 Step 4（GitHub App 选择）和旧 Step 5（仓库可见性）整段删除

> 删除范围：旧 `scenarios/onboard-new-app.md` 第 102-141 行。
> 理由：GHCR 模式下 Coolify 不再 fetch GitHub 源码，GitHub App 集成对本流程无效。

### 提示词 2.7 — Step 6 重写（create dockerimage + 读本地 compose + 出预览 + 收 env）

> **Step 6.1 — 在 Coolify 上 create Docker Image application（不部署）**
>
> ```bash
> coolify app create dockerimage \
>   --context="${context}" \
>   --name "${repo}" \
>   --project-uuid "${PROJECT_UUID}" \
>   --server-uuid "${SERVER_UUID}" \
>   --environment-name "${ENV_NAME:-production}" \
>   --docker-registry-image-name "ghcr.io/tranfu-labs/${repo}" \
>   --docker-registry-image-tag "${IMAGE_TAG:-dev}" \
>   --ports-exposes "${EXPOSE_PORT}" \
>   --domains "${DOMAINS_CSV}"
> ```
>
> 固定坑：
>
> - **`--ports-exposes` 仍 required 但 dockerimage 模式下真生效**（不是占位），从 compose.yml 解析得 `${EXPOSE_PORT}`，例 `8788`。
> - **`--docker-registry-image-tag` 必须显式传 `dev`**（CLI 默认 `latest`，dev 阶段用 `:dev` tag）。
> - **`--environment-name` 默认 `production`**（拍板 1），用户在触发语明说 `dev` 才覆盖。
> - **`--domains` 在 create 时一次设好**（CSV，例 `"https://order-mgmt-app.tranfu.com"`）；旧版的「Phase 2 PATCH `docker_compose_domains`」**整段删除**。
> - **`--instant-deploy` 不传**（不部署，留给 Phase 3 推 CI）。
> - **不传 `--build-pack`**（`dockerimage` 子命令隐式确定 build_pack；显式传会冲突）。
>
> **Step 6.2 — 拿 `APP_UUID`**：同旧版。
>
> **Step 6.3 — 验证 create 没意外触发部署**：同旧版（DEP_COUNT == 0 通过；> 0 cancel 最新）。
>
> **Step 6.4 — 读本地 `compose.yml`**（**整段重写**，旧版的轮询 `docker_compose_raw` 删除）：
>
> ```
> agent 在当前 working dir Read `compose.yml`，解析：
> - services 列表
> - server (或 web/api) service 的 expose 端口 → ${EXPOSE_PORT}
> - image 字段必须 == ghcr.io/tranfu-labs/${repo}:${IMAGE_TAG}
>   不一致 → 终止，引到 coolify-deploy skill 让用户先把 compose 切到 GHCR 模式
> - environment 段的 ${VAR_NAME} 引用 → 去重得 ENV_NAME_LIST
> - volumes 段（dockerimage 应用无公开 API 字段承载 volumes，预览要展示）
> - healthcheck 段（如有 → 告知用户 Dockerfile HEALTHCHECK 优先级，Coolify UI 可覆盖）
> ```
>
> **Step 6.5 — 出「部署预览」**：
>
> ```
> 准备在 context=${context} 上 onboard tranfu-labs/${repo}（GHCR 镜像模式）：
>
> 【自动准备的参数】
> - context / server-uuid / project / name      ：同旧版
> - build-pack                                  ：dockerimage（隐式）
> - environment                                 ：${ENV_NAME:-production}
> - image                                       ：ghcr.io/tranfu-labs/${repo}:${IMAGE_TAG:-dev}
> - ports-exposes                               ：${EXPOSE_PORT}
> - 已在 Coolify 上创建 app（未部署）            ：APP_UUID=${APP_UUID}
>
> 【从仓库 compose.yml 解析】（agent 直接 Read 本地 working dir）
> - services        : …
> - 端口            : ${EXPOSE_PORT}
> - volumes         : …（⚠️ dockerimage 应用无公开 API 设置 volumes，首次部署后到 Coolify UI 的 Persistent Storage 标签手动加挂载点）
> - env 名          : …
> - healthcheck     : Dockerfile 自带 / compose 覆盖
>
> 【默认域名（可改）】
> - server → https://${prefix}-app.tranfu.com
>
> 【onboard 完成后要落到仓库】
> - .github/workflows/deploy.yml 的 env.COOLIFY_APP_UUID 会从原值改为 ${APP_UUID}
> - 该改动由 agent 用 Edit 写进 working dir；commit & push dev 由你执行（agent 不替你推）
>
> 【需要你提供】
> - <列出 ENV_NAME_LIST 每个变量，等号留空>
> ```
>
> **Step 6.6 — 收 env 值**：用户贴 `.env` 直接用，没贴循环索要（保留旧版做法）。
>
> **Step 6.7 — 等用户确认**：反悔的终止文案保留「不替用户删 app」。

### 提示词 2.8 — Phase 2 简化为一步：Step 8 写 env

> 旧 Step 7（PATCH `docker_compose_domains`）**整段删除**（域名已在 Step 6.1 一次设好）。
>
> **Step 8 — `app env sync` + `trap EXIT shred`**（拍板 2）：
>
> ```bash
> ENV_TMP=$(mktemp)
> trap 'shred -u "$ENV_TMP" 2>/dev/null || rm -f "$ENV_TMP"' EXIT
>
> # 把收集到的 KEY=VAL 写入 $ENV_TMP（agent 内存中遍历 ENV_VALS 写）
> for KEY in "${!ENV_VALS[@]}"; do
>   printf '%s=%s\n' "$KEY" "${ENV_VALS[$KEY]}" >> "$ENV_TMP"
> done
>
> coolify app env sync --context="${context}" "${APP_UUID}" \
>   --file "${ENV_TMP}" --is-literal
> ```
>
> 验证（只显示 key 名和长度）：
>
> ```bash
> coolify app env list --context="${context}" "${APP_UUID}" --format json -s \
>   | jq 'map({key:(.key // .name // .variable),
>              is_literal,
>              value_len:((.value // .real_value // "")|tostring|length)})'
> ```
>
> ⚠️ `trap EXIT` 必须在 mktemp 后立刻挂上，覆盖所有退出路径（包括 agent 异常退出）。**优先用 `shred -u` 覆写**；macOS 没 shred 时 fallback `rm -f`（已用 `||` 兜）。

### 提示词 2.9 — Phase 3 触发部署（含双段兜底）

> **Step 9.a — Edit `.github/workflows/deploy.yml` 的 `COOLIFY_APP_UUID`**：
>
> agent 用 Edit 把 `env.COOLIFY_APP_UUID` 行的旧值替换为本次 `${APP_UUID}`。
> 文件不存在 / 格式与预期不符 → 终止，引到 `coolify-deploy` skill 让用户先生成 deploy.yml 模板。
>
> **Step 9.b — 校验 repo 级 `COOLIFY_BASE_URL` 是否已配**：
>
> ```bash
> EXPECTED_BASE=$(coolify context list --format json \
>   | jq -r --arg name "${context}" '.[] | select(.name==$name) | .fqdn')
> gh api -X GET repos/tranfu-labs/${repo}/actions/secrets/COOLIFY_BASE_URL --silent
> ```
>
> 404 / 失败终止文案：
>
> > 本 repo 还差一项 repo secret `COOLIFY_BASE_URL`，按本次选的 context (`${context}`) 它应该是：
> >   `${EXPECTED_BASE}`
> > 去 <https://github.com/tranfu-labs/${repo}/settings/secrets/actions/new> 把它加进去，回来告诉我「已配」我们继续。
> > （为什么不是 Org variable：BASE_URL 跟实例绑定，未来不同 repo 可能落到不同 Coolify 实例上，按 repo 配避免错配。Token 才是真正可全组共用的。）
> >
> > ⚠️ 注意：本校验只验存在性。值是否等于 `${EXPECTED_BASE}` 你**自查**——GitHub 故意不暴露 secret value；写错的 case 会在 Step 11.a `gh run watch` 失败时通过 `触发 Coolify 部署` step 的 curl DNS/connect 错误暴露。
>
> **Step 10 — 提示用户 commit & push dev**（agent 不推）：
>
> 固定文案：
>
> > 已把 COOLIFY_APP_UUID=${APP_UUID} 写进 .github/workflows/deploy.yml。
> > 请你自己跑：
> >
> > ```
> > git add .github/workflows/deploy.yml
> > git commit -m "ci(deploy): 接 Coolify ${ENV_NAME:-production} 应用 ${APP_UUID}"
> > git push origin dev
> > ```
> >
> > 推上去后 GitHub Actions 会跑测试 → 推 GHCR → curl Coolify deploy API 触发部署。
> > 我不替你 commit/push（远端可见，破坏性）。
> > 推完告诉我「已推」，我接管 Step 11 的双段兜底。
>
> **Step 11.a — 盯 GitHub Actions run（CI 一侧兜底）**：
>
> 用户说「已推」后：
>
> ```bash
> # 拿当前分支最新 run
> RUN_ID=$(gh run list --repo "tranfu-labs/${repo}" --branch dev --limit 1 \
>   --json databaseId,headSha,createdAt \
>   | jq -r 'sort_by(.createdAt) | last | .databaseId')
>
> # --exit-status 让 watch 在 CI fail 时返回非 0
> gh run watch "${RUN_ID}" --repo "tranfu-labs/${repo}" --exit-status
> ```
>
> 失败分诊：
>
> ```bash
> gh run view "${RUN_ID}" --repo "tranfu-labs/${repo}" --log-failed
> ```
>
> 按失败的 step 名分流：
>
> | 失败 step | 兜底 |
> |---|---|
> | `前置检查（Coolify 部署所需配置）` | secret/variable **值为空** 或刚被 admin revoke 或 Org→repo 可见性配错。回 Step 0.5 / 9.b 重查，重点检查 value 是否非空（gh 看不到 value，必要时让用户去 GitHub UI 手动核对） |
> | `协议契约测试` | 应用层测试问题，**不在本 skill 范围**，交回开发 |
> | `构建并推送镜像` | build / GHCR push 问题（image name 拼错、`packages: write` 权限缺、首次推 visibility 默认不对）→ 引到 `coolify-deploy` skill |
> | `触发 Coolify 部署` | **关键失败 — webhook 发不过去**。看 curl 输出的 HTTP code：<br>• `401 Unauthorized` → token 存在但无效（过期/被 revoke/scope 错）<br>• `404 Not Found` → `COOLIFY_APP_UUID` 错（Step 9.a edit 时填错）或 Coolify app 已被删<br>• `Could not resolve host` / `Connection refused` / `timeout` → `COOLIFY_BASE_URL` 错（与 `${EXPECTED_BASE}` 不一致）或 Coolify 实例宕<br>• 别的 5xx → Coolify 实例本身问题 |
>
> **Step 11.b — 跟 Coolify deployment logs（Coolify 一侧兜底）**：
>
> 只有 11.a 退出 0 才进入。
>
> ```bash
> sleep 5  # 等 Coolify 收到 deploy API 请求排上队
> DEPLOYMENT_UUID=$(coolify app deployments list --context="${context}" "${APP_UUID}" --format json \
>   | jq -r 'sort_by(.created_at // .id) | last | .deployment_uuid')   # 注意是 .deployment_uuid 不是 .uuid
>
> LOG_FILE=$(mktemp)
> coolify app deployments logs --context="${context}" "${APP_UUID}" "${DEPLOYMENT_UUID}" --follow 2>&1 \
>   | tee "${LOG_FILE}" &
>
> # 边跟边 grep Docker 标准 401/403 字串
> ( tail -F "${LOG_FILE}" \
>     | grep -E -m1 'unauthorized: authentication required|pull access denied' \
>   && echo "GHCR_AUTH_FAIL" ) &
> ```
>
> grep 命中 → 显式打断 follow，文案：
>
> > 首次部署在 Coolify 拉镜像阶段失败：`<匹配到的字串>`。
> > 这是 Coolify 主机**没配** ghcr.io private registry 凭证（或 token scope 不足）的典型表现——见 Step 0.6 的人类前置告知。
> > 去修：见 `references/coolify-ghcr-registry-prereq.md`。
> > 修完后**不需要重做 onboard**——COOLIFY_APP_UUID 已写进 deploy.yml。可二选一：
> >
> > 1. 直接 `coolify app start --context="${context}" "${APP_UUID}" --force` 让 Coolify 重新 pull
> > 2. 推一个空 commit 让 CI 再 curl /deploy
>
> 5 次轮询（~30s）后 deployments list 仍为空 → 终止文案：
>
> > CI 报告完成但 Coolify 30s 内没收到 deployment——通常是 `触发 Coolify 部署` step 实际 fail 但被 `||` / `--fail-with-body` 漏吞了。
> > 回 Step 11.a `gh run view --log <RUN_ID>` 看 `触发 Coolify 部署` 的实际 curl 输出。
>
> **完成判据**（**B 拍板**）：
>
> 1. Coolify app 状态 `running:healthy`：`coolify app get --context="${context}" "${APP_UUID}" --format json | jq '.status'`
> 2. 服务域名 200/2xx：`curl -sSI "https://${prefix}-app.tranfu.com" | head -1` agent 主动跑这一发
>
> 任一不过 → 引到 `references/coolify-compose-deploy-failure-triage.md`（虽然是 dockercompose 命名的，但 deployment 失败排障流程通用）。

### 提示词 2.10 — 验收用例段

> 旧用例表 8/9/10（GitHub App 相关）删除。新增：
>
> | # | 输入 / 状态 | 期望 |
> |---|---|---|
> | 1 | `tranfu-labs/foo-app` + 前置 OK + 仓库 compose.yml 是 GHCR 模式 + env 列表非空 | 走完 Phase 1（预览 + 收 env）→ Phase 2（create dockerimage + env sync）→ Phase 3（edit UUID + push + 11.a CI 跑通 + 11.b Coolify 部署成功 + 域名 2xx） |
> | 2 | `other-org/foo-app` | Step 1 终止 |
> | 3 | `tranfu-labs/Foo_App` | Step 1 终止 |
> | 4 | Coolify 已有同名 app | Step 2 终止 |
> | 5 | Coolify 上没 server / 2 台 server | Step 0 终止 |
> | 6 | Org secret `COOLIFY_API_TOKEN` 不存在 | Step 0.5 终止 |
> | 7 | gh 不可用 / 未 auth | Step 0.5 终止 |
> | 8 | 仓库 compose.yml 仍是 `build:` 模式（未切 GHCR） | Step 6.4 终止，引到 coolify-deploy |
> | 9 | 仓库无 `.github/workflows/deploy.yml` | Step 9.a 终止 |
> | 10 | repo secret `COOLIFY_BASE_URL` 不存在 | Step 9.b 终止，agent 给出 `${EXPECTED_BASE}` |
> | 11 | 用户 push 后 CI 在 `前置检查` 挂（secret value 为空） | Step 11.a 分诊到 secret 配置问题 |
> | 12 | 用户 push 后 CI 在 `触发 Coolify 部署` 挂 401 | Step 11.a 分诊到 token 无效 |
> | 13 | 用户 push 后 CI 在 `触发 Coolify 部署` 挂 404 | Step 11.a 分诊到 UUID/app 错 |
> | 14 | CI 跑通但 Coolify 拉镜像 `unauthorized` | Step 11.b grep 拦截，引到 ghcr prereq |
> | 15 | CI 跑通 + Coolify 部署成功但域名 curl 非 2xx | 完成判据失败，引到 deploy-failure-triage |
> | 16 | 用户在 Step 6.7 反悔 | 终止，给删除命令但**不替用户删** |
> | 17 | compose.yml 有 volume（如 tf-data:/data） | Step 6.5 预览面板明确告知首次部署后 UI 加 Persistent Storage |
> | 18 | 用户触发语指定 `dev` environment | `${ENV_NAME}=dev`，否则默认 `production` |

### 提示词 2.11 — example / bad-example 重写

> example 写一份新流程的逐步对话（保留 `tranfu-labs/order-mgmt-app` 示例 repo，含 Step 0.5/0.6/6.x/8/9.a/9.b/10/11.a/11.b 全链）。
> bad-example：
>
> - 旧「错误做法 2：agent 自己 `git clone` / `gh api 读源码`」**改写**为：「禁止读源码；允许 `gh api` 校验存在性、`gh run watch` 盯 CI run」。
> - 旧「错误做法 4：传 `--docker-compose-location ""`」**删除**。
> - 旧「错误做法 1：直接带 `--instant-deploy`」**保留**但措辞改为「直接带 `--instant-deploy` 会绕过 env 注入和 deploy.yml 接入，让 CI 路径失效」。
> - **新增错误做法**：agent 替用户 `git commit && git push origin dev`——远端推送是用户专属破坏性动作。
> - **新增错误做法**：agent 跑 `gh secret set` 帮用户写 Org/repo secret——凭证写入必须用户在 GitHub UI 完成。
> - **新增错误做法**：agent 创建 dummy app 探测 GHCR 凭证——违反「先断言再动作」。
> - **新增错误做法**：jq `.uuid` 而不是 `.deployment_uuid` 拿部署单元 UUID——4.1.2 字段名是后者，前者拿到 null 或拿到错的 application_id。

### 提示词 2.12 — 补充：`gh run watch` 不可用时的降级

> Step 11.a 默认用 `gh run watch --exit-status`。如果用户环境 `gh` 不可用（Step 0.5 已经强终止过，正常不应发生）或 GitHub Actions 临时 outage，降级为：
>
> > 你自己去 <https://github.com/tranfu-labs/${repo}/actions> 看最新 run。
> > 跑完告诉我：①是否全绿 ②失败的 step 名 ③`触发 Coolify 部署` step 的 curl 输出最后几行（含 HTTP code）。
> > 我按你给的信息分诊到 Step 11.a 的兜底表。
>
> 不要让 agent 自己 sleep 轮询 Coolify deployments list 假装 CI 跑通——会漏掉 webhook 失败的核心信号。

---

## 5. 文件三：新建 `references/github-actions-coolify-org-token-precheck.md`

### 提示词 3.1 — 内容骨架

> ```markdown
> # GitHub Actions：tranfu-labs Org 级 Coolify API token 存在性校验
>
> 适用：onboard 新 `*-app` 前的早死检查（`scenarios/onboard-new-app.md` Step 0.5）。
>
> ## 校验命令
>
> ```bash
> gh auth status -h github.com >/dev/null    # gh 未 auth 直接终止
> gh api -X GET orgs/tranfu-labs/actions/secrets/COOLIFY_API_TOKEN --silent
> ```
>
> 返回 200 → 通过；404 → 终止。
>
> ## 边界声明（重要）
>
> `gh api .../actions/secrets/<NAME>` 只能验证 secret **存在**，**不能**验证：
>
> - value 不为空字符串
> - token 没过期 / 没被 admin revoke
> - token 的 scope 真够 deploy 权限
>
> 这些只能在 Phase 3 Step 11.a `gh run watch` 真跑一次 curl /deploy 时**才**暴露。
> 本校验的价值是**早死**——压根没配的 case 直接拦住，省一次 push dev → CI 半天才发现的来回。
>
> ## 终止文案模板
>
> > tranfu-labs 缺 Org 级 secret `COOLIFY_API_TOKEN`。
> > 去 <https://github.com/organizations/tranfu-labs/settings/secrets/actions> 配齐。
> > **不要**给本 repo 单独写 repo secret——Org 级是全 `*-app` 共用的设计。
>
> ## 失败兜底
>
> - `gh` 不可用 / 未 `gh auth login` → 要求用户先 `gh auth login`，agent **不替用户登录**。
> - 用户希望临时改走 repo 级 secret 而非 Org 级 → **不支持**，直接终止并解释（保持 D 拍板的 Org 级默认，避免凭证散落）。
> ```

---

## 6. 文件四：新建 `references/coolify-ghcr-registry-prereq.md`（事后兜底文档）

### 提示词 4.1 — 内容骨架

> ```markdown
> # Coolify 主机 GHCR 私有镜像 pull 凭证（事后兜底配置）
>
> 适用：当 `scenarios/onboard-new-app.md` Phase 3 Step 11.b grep 到 `unauthorized: authentication required` 或 `pull access denied` 时，从这里照配。
>
> ## 为什么是"事后兜底"
>
> Coolify 4.1.2 没有任何 API/CLI 让 agent 在 onboard 前置阶段断言 ghcr.io registry 凭证存在。
> 本 skill 选择**不前置探测**（探测要真创资源、依赖未文档化错误字串），改为：
>
> - Step 0.6 只做事实告知
> - Step 11.b 通过 grep Docker daemon 标准 401/403 字串拦截
>
> 一旦命中拦截，按本文档照配；配完后**不需要重做 onboard**。
>
> ## 配置步骤
>
> 1. 登录 Coolify 实例网页 UI。
> 2. Settings → Private Registries（或当期 UI 对应路径，4.1.2 起在 Servers 标签下）。
> 3. 添加：
>    - URL: `ghcr.io`
>    - Username: `tranfu-labs` 或一个**共享 PAT 账户名**（建议不绑定个人）
>    - Token: GitHub PAT，scope **仅** `read:packages`（不要给写权限）
> 4. 把 registry 关联到部署 `*-app` 的 server 上。
>
> ## 配完后如何恢复（不重做 onboard）
>
> 二选一：
>
> 1. CLI 直接 redeploy：
>    ```bash
>    coolify app start --context="${context}" "${APP_UUID}" --force
>    ```
>    （`--force` 在 dockerimage 下含义是「不走 docker layer 缓存」，会重新 pull tag。）
>
> 2. 推一个空 commit 让 CI 走一遍：
>    ```bash
>    git commit --allow-empty -m "ci: retrigger after GHCR registry config"
>    git push origin dev
>    ```
>
> ## 复盘
>
> tranfu-labs 团队的 ops runbook 应该把「Coolify 实例已配 ghcr.io registry」作为一次性勾选项落到文档，避免每个新人 onboard 第一次都踩同一遍。
> ```

---

## 7. 文件五：新建 `references/github-actions-run-watch-and-diagnose.md`

### 提示词 5.1 — 内容骨架

> ```markdown
> # GitHub Actions run 监控与失败分诊
>
> 适用：`scenarios/onboard-new-app.md` Phase 3 Step 11.a。
>
> ## 监控
>
> ```bash
> RUN_ID=$(gh run list --repo "tranfu-labs/${repo}" --branch dev --limit 1 \
>   --json databaseId,headSha,createdAt \
>   | jq -r 'sort_by(.createdAt) | last | .databaseId')
>
> gh run watch "${RUN_ID}" --repo "tranfu-labs/${repo}" --exit-status
> ```
>
> exit 0 → 进 Step 11.b。exit 非 0 → 取失败日志：
>
> ```bash
> gh run view "${RUN_ID}" --repo "tranfu-labs/${repo}" --log-failed
> ```
>
> ## 按 step 分诊
>
> | 失败 step | 根因 | 兜底 |
> |---|---|---|
> | `前置检查（Coolify 部署所需配置）` | secret/variable 值为空 / Org 与 repo 可见性配错 / 刚被 revoke | 回 Step 0.5 / 9.b 重查；让用户去 GitHub UI 手动核对 value 是否非空 |
> | `协议契约测试` | 应用层测试问题 | **不在本 skill 范围**，交回开发 |
> | `构建并推送镜像` | image name 拼错 / `packages: write` 权限缺 / 首次推 visibility 默认不对 | 引到 `coolify-deploy` skill |
> | `触发 Coolify 部署` | webhook 失败 — 看 curl 输出 HTTP code | 见下表 |
>
> ### `触发 Coolify 部署` step 的 curl HTTP code 分诊
>
> | HTTP code / 错误 | 根因 | 处理 |
> |---|---|---|
> | `401 Unauthorized` | `COOLIFY_API_TOKEN` 值过期 / 被 revoke / scope 错 | 让用户去 Coolify 实例重新生成 deploy token，更新 Org secret |
> | `404 Not Found` | `COOLIFY_APP_UUID` 错（Step 9.a 填错）或 Coolify 上 app 已被删 | 回 Step 9.a 用本次 `${APP_UUID}` 重 Edit；或检查 `coolify app get` 是否仍在 |
> | `Could not resolve host` / `Connection refused` / `timeout` | `COOLIFY_BASE_URL` 写错（与 `${EXPECTED_BASE}` 不一致）或 Coolify 实例宕 | 让用户到 repo secret UI 比对 BASE_URL 值；或 `curl -sSI ${EXPECTED_BASE}/api/v1/health` 验证实例可达 |
> | 别的 5xx | Coolify 实例自身问题 | 让用户看 Coolify 实例 status 页 / 容器日志 |
>
> ## 降级（gh 不可用）
>
> 让用户去 <https://github.com/tranfu-labs/${repo}/actions> 自己看，回报：① 是否全绿 ② 失败 step 名 ③ `触发 Coolify 部署` step 的 curl 输出末尾（含 HTTP code）。**不要** agent 自己 sleep 轮询 Coolify deployments 假装 CI 跑通。
> ```

---

## 8. 文件六：调整 `references/existing-app-redeploy.md`

### 提示词 6.1 — 重写 redeploy 语义段

> 在文档开头加一节「redeploy 的两种语义」：
>
> > Coolify 4.1.2 + dockerimage 应用的 redeploy 路径有两条独立入口，但**语义等价**——都进 `queue_application_deployment`，都会**按当前 `image:tag` 重新 pull**：
> >
> > 1. **CLI 路径**：`coolify app start --context="${context}" "${APP_UUID}" --force`
> >    打的端点是 `POST /api/v1/applications/{uuid}/start?force=true`。
> > 2. **CI 路径（webhook）**：GitHub Actions 末尾 `curl POST ${BASE}/api/v1/deploy?uuid=${APP_UUID}&force=false`。
> >    支持 comma-separated 多个 UUID 批量。
> >
> > `force=true` 在 dockerimage 类型下的含义是 **不走 docker layer 缓存**——拉的还是同一个 tag，但跳过缓存。
> > **不存在「只重启容器、不重新 pull」的纯 restart 语义**。如果用户希望"不重新 pull 只重启"，需要走 docker 层（`docker restart`）而非 Coolify API。
> >
> > 想换 image 内容（拉新代码）：
> >
> > - tag 是 `latest`/`dev` 这种 mutable tag → push GHCR 新镜像 + redeploy（任一条入口）即可
> > - tag 是 immutable sha → 需要先在 Coolify 上 PATCH `docker_registry_image_tag` 改 tag，再 redeploy（PATCH 时**不要**改 `build_pack`）

### 提示词 6.2 — 同步去掉对 `app start --force` "只重启容器" 的旧描述

> 全文 grep `重启容器` / `restart only` / 类似措辞，按提示词 6.1 重写。原 skill 任何「`--force` 不会拉新镜像」的暗示都删除。

---

## 9. 文件七：调整 `commands/app.md`

### 提示词 7.1 — 修第 149 行 bug

> 旧版第 149 行：
>
> ```bash
> | jq -r 'sort_by(.created_at // .id) | last | .uuid'
> ```
>
> 改为：
>
> ```bash
> | jq -r 'sort_by(.created_at // .id) | last | .deployment_uuid'
> ```
>
> 4.1.2 部署单元的字段名是 `deployment_uuid`，不是 `uuid`（`uuid` 在 deployment model 上不存在；`id` 是另一个 int 主键）。旧版用 `.uuid` 拿到 null 或拿到错的字段，靠 `coolify app deployments logs` 位置参数也接受 id 才"看起来对"。

### 提示词 7.2 — 新增 `## coolify app create dockerimage` 章节

> 在「## coolify app create github」章节之后插入完整章节，参数表按核对结果填：
>
> ```markdown
> ## `coolify app create dockerimage`
>
> 从已推送到 image registry 的镜像直接创建一个应用。**新版 onboard 场景（GHCR 镜像模式）Step 6.1 主命令**。
>
> 参数表：
>
> | 参数 | 类型 | 必填 | 默认 | 说明 |
> |---|---|---|---|---|
> | `--server-uuid` | string | **是** | — | server UUID |
> | `--project-uuid` | string | **是** | — | project UUID |
> | `--environment-name` | string | **二选一** | — | environment 名（与 `--environment-uuid` 二选一） |
> | `--environment-uuid` | string | **二选一** | — | environment UUID |
> | `--docker-registry-image-name` | string | **是** | — | 镜像全名，例 `ghcr.io/tranfu-labs/foo-app` |
> | `--docker-registry-image-tag` | string | 否 | `latest` | 镜像 tag。**dev 阶段必须显式传 `dev`** |
> | `--ports-exposes` | string | **是** | — | 暴露端口（dockerimage 模式下真生效，不是占位） |
> | `--name` | string | 否 | — | 应用名 |
> | `--domains` | string | 否 | — | 域名 CSV，例 `"https://foo-app.tranfu.com"` |
> | `--description` | string | 否 | — | 应用描述 |
> | `--destination-uuid` | string | 否 | — | 多 destination 时指定 |
> | `--ports-mappings` | string | 否 | — | `host:container` |
> | `--limits-cpus` | string | 否 | — | CPU 配额 |
> | `--limits-memory` | string | 否 | — | 内存配额 |
> | `--health-check-enabled` | bool | 否 | `false` | 启用健康检查 |
> | `--health-check-path` | string | 否 | — | 健康检查路径 |
> | `--instant-deploy` | bool | 否 | `false` | 创建后立即部署。**onboard 场景不传**，部署留给 CI |
>
> 证据：<https://raw.githubusercontent.com/coollabsio/coolify-cli/v1.6.2/cmd/application/create/dockerimage.go>
>
> **onboard 场景用法**：见 `scenarios/onboard-new-app.md` Step 6.1。
>
> 已知坑：
>
> - **`build_pack` 隐式设为 `dockerimage`**：controller 在 `create_dockerimage_application` 里直接赋值。**NEVER** 通过 PATCH `/applications/{uuid}` 修改 `build_pack: "dockerimage"`——`BuildPackTypes` enum 不含此值，PATCH 会被拒。
> - **域名字段双轨**：写入用 `domains`（comma-separated 字符串），读出/DB 列叫 `fqdn`。GET 校验时 jq `.fqdn`。
> - **dockerimage 应用没有公开 volumes API 字段**。compose.yml 里的 named volume 只能在网页 UI 的 Persistent Storage 标签手动加。
> ```

### 提示词 7.3 — `app create github` 章节加 deprecation 备注

> 在 `## coolify app create github` 章节开头加一行：
>
> > ⚠️ **tranfu-labs `*-app` 已迁 GHCR 镜像模式（见 `app create dockerimage`）**。本章节作为旧路径文档保留，新 onboard 不再走此路径。

### 提示词 7.4 — 文件顶部加版本时间戳

> 文件第一行加：
>
> ```
> <!-- verified against Coolify 4.1.2 + CLI 1.6.2 @ 2026-06-26 -->
> ```

---

## 10. 文件八：标 deprecated 的旧 references

### 提示词 8.1 — `references/coolify-dockercompose-domains.md`

> 文件顶头加一行：
>
> > ⚠️ **仅用于历史 dockercompose 类型应用（旧 onboard 路径）**。新 GHCR 镜像模式（dockerimage 类型）域名在 create 时通过 `--domains` 一次设好，不再 PATCH `docker_compose_domains` 字段。新流程不引用本文档。

### 提示词 8.2 — `references/coolify-dockercompose-file-detection.md`

> 文件顶头加一行：
>
> > ⚠️ **仅用于历史 dockercompose 类型应用**。新 GHCR 镜像模式不让 Coolify 拉源码、不依赖 compose.yml 检测路径，本文档不再适用 onboard 主路径，保留作旧 dockercompose 应用排障。

### 提示词 8.3 — 其它 references 检查清单

> 改完 SKILL.md 后，grep 一遍所有 references 文件：
>
> ```bash
> grep -lE 'docker_compose_raw|docker_compose_domains|--build-pack dockercompose|coolify app create github' \
>   ~/.claude/skills/tranfu-coolify-ops/references/
> ```
>
> 命中的文件挨个核对是否仍适用 GHCR 路径；不适用就加顶头 deprecation 行（不删，作为旧 dockercompose 应用排障保留）。

---

## 11. 文件九：调整 `commands/conventions.md`

### 提示词 9.1 — `app start` 章节

> 全局守则段第 84 行附近的：
>
> > `app start` 等价于 `app deploy`，可加 `--force`（强制 rebuild）或 `--instant-deploy`（跳过排队）。
>
> 改为：
>
> > `app start` 等价于 `app deploy`，可加 `--force` 或 `--instant-deploy`。
> > **`--force` 在不同 build_pack 下含义不同**：
> >
> > - `dockerfile` / `dockercompose`：强制 rebuild（不走 docker layer 缓存）。
> > - `dockerimage`：按当前 `image:tag` **重新 pull**（不走缓存）。
> >
> > 任何 build_pack 下 `--force` 都**不**等价于"只重启容器"。

### 提示词 9.2 — `--show-sensitive` 短 flag

> 「全局 flag」段（第 9 行附近）保持现写法（`-s` 或 `--show-sensitive`）。**拍板 3** 沿用 `-s`。如改文件时本地求证 `-s` 在 1.6.2 上失效再回头修。

---

## 12. 动手前的执行清单（写时按这个跑）

按这个顺序改，能保证一致性不断裂：

1. **求证 + 时间戳**：按提示词 0 跑一遍 Coolify 4.1.2 + CLI 1.6.2 的命令/端点求证（本提案第 2 节已做完），把时间戳写进 `commands/app.md` 顶头。
2. **改 SKILL.md**：按提示词 1.1–1.7 逐条改 frontmatter / NEVER 段 / 路由表 / 参数表 / 守则 / 引用列表 / example。
3. **新建三份 references**：
   - `references/github-actions-coolify-org-token-precheck.md`（提示词 3.1）
   - `references/coolify-ghcr-registry-prereq.md`（提示词 4.1）
   - `references/github-actions-run-watch-and-diagnose.md`（提示词 5.1）
4. **改 commands/app.md**：bug fix（提示词 7.1）→ 新增 dockerimage 章节（7.2）→ github 章节加 deprecation（7.3）→ 顶头时间戳（7.4）。
5. **改 commands/conventions.md**：app start 章节（9.1）。
6. **改 references/existing-app-redeploy.md**：redeploy 语义段（6.1）+ 全文清旧描述（6.2）。
7. **标 deprecated 旧 references**：8.1 / 8.2 / 8.3 grep 巡检。
8. **改 scenarios/onboard-new-app.md**：按提示词 2.1–2.12 整体重写。**最后改这个**，因为它引用了前面所有新建文件——避免改到一半被前置文件结构卡住。
9. **改完 grep 验证**：
   - `grep -rE 'GitHub App|docker_compose_raw|app create github' ~/.claude/skills/tranfu-coolify-ops/` 命中的位置应都是 deprecated 提示而非主路径。
   - `grep -rE '\.uuid' ~/.claude/skills/tranfu-coolify-ops/commands/app.md` 应只剩 `--server-uuid`/`--project-uuid` 之类 flag，不再有 deployment 单元字段引用错的 `.uuid`。

---

## 13. 拍板确认表（动手前再核一遍）

| # | 拍板项 | 选择 |
|---|---|---|
| A | onboard 是替换还是新增？ | 替换 |
| B | onboard 成功标准 | 服务域名 2xx |
| C | APP_UUID 怎么管 + TOKEN 怎么校验 | UUID 是 skill 产物；TOKEN 只校验存在性 |
| D | TOKEN 配在哪 | Org 级 secret |
| 1 | `--environment-name` 默认 | `production` |
| 2 | env 写入方式 | `app env sync` + `trap EXIT shred` 临时文件 |
| 3 | `-s` vs `--show-sensitive` | 沿用 `-s` |
| 4 | GHCR 凭证怎么管 | 不软探测；Step 0.6 人类前置告知 + Step 11.b grep 401/403 兜底；同时 Step 11.a 用 `gh run watch` 盯 CI 一侧（覆盖 webhook 都发不过去的链路） |

---

## 14. 这份提案没解决的、留给写时再决定的边角问题

1. **dockerimage 应用的 `--health-check-enabled` 默认要不要打开**：旧 dockercompose 路径靠 compose 里的 healthcheck，Coolify 自动认；dockerimage 路径需要在 create 时显式 `--health-check-enabled --health-check-path /healthz`。倾向打开（Dockerfile 自带 HEALTHCHECK 是后备，Coolify 层 health check 直接影响 Traefik 路由），但要先确认 4.1.2 dockerimage 模式下 `--health-check-enabled` 不传时的默认行为。
2. **volumes 在 `custom_docker_run_options` 里写还是只走 UI Persistent Storage**：写 `custom_docker_run_options` 是自由文本，agent 写错就 silent broken。**默认走 UI**，但要写时确认 Coolify 4.1.2 UI 的 Persistent Storage 标签在 dockerimage 应用下确实可用。
3. **`gh run watch` 的 `--exit-status` 在 1.6.2 兼容性**：写时验证 `gh` 版本依赖（GitHub CLI 2.x 起支持）。用户机器若 `gh` 版本低，要给降级提示。
4. **Phase 3 是否要校验 Org 级 `COOLIFY_BASE_URL` 也存在的可能性**：当前设计 BASE_URL 是 repo 级。但如果 tranfu-labs 未来把 BASE_URL 也升到 Org（所有 repo 同实例），9.b 要补一段「先查 Org 再查 repo」的兜底。**当前不做**，等场景出现再加。
5. **本提案默认 `coolify private-registry` 命令 4.1.2 不存在**——这是 evidence 推断（cmd 树零命中 + routes/api.php 零命中）。**写时再 grep 一遍 v4.1.2 tag 的 `app/Http/Controllers/Api/` 全集** 看有没有藏在别处的 controller，万一存在就把 Step 0.6 升级回"可探测"。

---

> **本提案到这里为止**。下次动手时按第 12 节执行清单的顺序跑，跑完一遍 grep 验证就收工。
