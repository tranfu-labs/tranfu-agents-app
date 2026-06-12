# AGENTS.md — TRANFU//AGENTS 项目操作手册(给 AI / 协作者)

TRANFU//AGENTS 是一个**自托管、厂商中立的团队 AI Agent 可观测看板**:每个人的 agent 上报
极简状态事件到中心 collector,看板实时展示「谁在跑、用哪个 agent、当前哪一步、状态、活跃时长」,
展示每个 agent 的治理详情(版本/终端/IM/MCP/技能等),并提供独立 SKILLS 统计页。MIT 许可。

> 改动本项目前,先读这份 + `docs/architecture/module-map.md`(模块边界)+ `docs/adr/`(已定下的约束)。
> 业务规则的事实来源是 `openspec/specs/<domain>/spec.md`;要做需求/变更,先在
> `openspec/changes/<change-id>/` 写 proposal/design/tasks 再实现。

## 项目结构(根目录)
- `server/app.py` — FastAPI collector + 看板服务端(单进程,既收事件又发页面与 API)。
- `Dockerfile`、`compose.yml`、`.env.example`、`server/requirements.txt` — 部署。
- `dashboard/index.html` — 单文件看板前端(SEO head + 内联 CSS/JS),由服务端在 `/` 提供。
- `shims/` — 各客户端上报工具:
  - `tf_profile.py` 自动探测器、`tf_report.py` 统一发射器、`tf_client.sh`/`wrapper/tf-run` bash 封装、
    `tf_hook.py` Claude Code 钩子分发器、`tf_selfupdate.py` manifest 自更新器、`tf_client.py` python 客户端、
    `claude-code/`(hooks.settings.json + README)、`mcp/`(MCP reporter server.py)。
- `install.sh` — 一键安装:按 `$SERVER/shims/manifest` 全量拉客户端到 `~/.tranfu`,写 shell rc,装完自动注册一次。
- 文档:`README.md`、`QUICKSTART.md`(队友 5 分钟接入)、`USAGE.md`(自然语言接入)、
  `DEPLOY.md`(部署)、`UPDATE.md`(更新现有部署)、`DEV-SETUP.md`(开发从零部署)、
  `PROTOCOL.md`(TATP 事件协议)、`SKILL.md`(给 agent 读的自助安装说明)、`llms.txt`/`robots.txt`。

## 常用命令
```bash
# 本地起服务端(看板 + API)
pip install -r server/requirements.txt
TF_KEY=devkey python -m uvicorn server.app:app --host 0.0.0.0 --port 8788

# Coolify 部署
# 使用根目录 compose.yml;给 server service 配 Domain: https://你的域名:8788

# 本地裸 Python 健康/接口自检
curl http://localhost:8788/healthz          # ok
curl http://localhost:8788/api/state | head # JSON
curl 'http://localhost:8788/api/skills?days=30' | head # SKILLS 总览 JSON
curl http://localhost:8788/shims/manifest | head # shim 版本清单

# 发一条测试事件
curl -s -XPOST http://localhost:8788/v1/events -H 'content-type: application/json' \
  -H 'X-TF-Key: devkey' -d '{"operator":"t","runtime":"claude-code","session_id":"s1","status":"running","task":"x","current_step":"y"}'
```

## 编码规范 / 约定
- **服务端只用标准库 + FastAPI/uvicorn**;数据库是单文件 SQLite(`$TF_DB`,默认 `tf.db`),不引入外部 DB/中间件。
- **shim(`tf_profile.py`/`tf_report.py`/`tf_hook.py`/`tf_selfupdate.py`)只用 Python 标准库,且绝不抛错**——上报/更新失败必须静默,
  不能影响使用者的 agent 运行。
- Skill 使用统计口径:事件可选 `skill` 字段只记录 Skill 名,可选 `skill_mode ∈ {used,equipped}`;
  服务端写 `skill_uses`(一行=会话×Skill×mode,`(session_id, skill, mode)` 幂等,长期保留)。
  `/api/state.skills` 保留兼容排行;SKILLS 页读取 `/api/skills`(总览只统计 `used`)与
  `/api/skill/{name}`(used/equipped 分列详情)。默认上报,本机 `TF_REPORT_SKILLS=0` 关闭;
  不得上报 Skill 参数、prompt、代码或输出。
- 前端是**单文件**(`dashboard/index.html`):CSS/JS 内联;改动后用 `node --check` 校验抽出的 `<script>`。
  暗/亮双主题用 CSS 变量 + `body.light` 覆盖;品牌红 `--brand`(占位 `#ec1c2b`,待换精确值);logo 为内联红色 symbol。
- 时间统一 **UTC**(活跃时长按 UTC 日/周;90 天窗口)。
- 不追踪 token / 成本(已彻底移除);写凭证只有 `TF_KEY`,请求头 `X-TF-Key`。
- 仓库 owner/库名统一 `tranfu-labs/tranfu-agents-app`;raw/clone/install 链接都指它。

## 修改前检查
1. 读 `docs/architecture/module-map.md` 确认你改的模块边界与**禁止依赖**。
2. 读相关 `openspec/specs/<domain>/spec.md`,确认不违反既有业务规则;若要改规则,走 `openspec/changes/`。
3. 读 `docs/adr/` 看是否触碰已决约束(如:无 token 追踪、单容器、按身份合并卡片)。

## 修改后检查
1. 服务端:`python -m py_compile server/app.py`;关键路径用 TestClient 自测
   (`/v1/events` 去重、`/api/state` 返回结构与卡片合并、`/api/skills` 与 `/api/skill/{name}` 聚合口径、
   `/install.sh`、`/shims/manifest` 与 `/shims/<f>` 可取、目录穿越被拒)。
   协议契约测试固化在 `tests/`(`pytest tests/`),CI(`.github/workflows/ci.yml`)会在 PR 上自动跑;
   改协议行为时同步加/改用例。
2. 前端:抽出 `<script>` 跑 `node --check`;暗/亮主题与手机窄屏(≤600px)各看一眼。
3. shim:对 fake 环境跑 `tf_profile.py` / `tf_report.py --print` 验证 payload;`bash -n` 校验 sh。
4. 文档:涉及端口/链接/字段时,同步 `DEPLOY/UPDATE/QUICKSTART/USAGE/PROTOCOL`、`docs/architecture/module-map.md`
   与本文件;若影响 agent 自助安装,同步 `SKILL.md`。

## 禁止事项(硬约束)
- ❌ 不得加入 token/费用统计,或把"成本"概念带回数据模型/协议/UI。
- ❌ 不得让 shim 在探测/上报失败时抛错或阻塞使用者 agent;不得默认上报 prompt/代码/输出/记忆(均为 opt-in)。
- ❌ 不得在 Claude Code 钩子里依赖 `$CLAUDE_SESSION_ID` 等环境变量取上下文——必须从 stdin 的事件 JSON 解析(见 ADR-0009)。
- ❌ 不得为看板引入外部数据库/消息队列/独立前端构建步骤(保持单容器 + 单文件前端)。
- ❌ 不得把密钥写进仓库或文档正文(`TF_KEY` 仅存部署机 `.env` / 使用者 shell rc)。
- ❌ 不得绕过"按身份(operator + agent||runtime)合并卡片"的模型去按 session 散开展示。
