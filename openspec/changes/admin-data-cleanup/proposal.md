# 变更提案:admin-data-cleanup(后台数据清理台)

- 状态:Proposed(待实现)
- 关联:**ADR-0020(硬删+回收站+审计;鉴权隔离,本变更新增)**、ADR-0001(单容器/单文件 SQLite)、ADR-0002(写侧 TF_KEY)、ADR-0011(per-operator 令牌)、ADR-0014(保留期裁剪)、specs/ingest、specs/board、`DELETE /v1/events`(现有)、`compose.yml`、`DEPLOY.md`、`docs/wireframes/pages/admin.md`

## 背景 / 问题
生产看板里会混入两类脏数据:接入联调留下的测试数据、同事配置错误上传的数据(填错 operator、填错 skill 名等)。它们污染 Pods 看板卡片、operator 列表和 SKILLS 排行,需要一个能在生产**安全删除**这些数据、保持页面干净整洁的后台。

现状只有一个 `DELETE /v1/events`,有三个不够用的地方:
1. **删不干净**:只动 `events`(可选 `profiles`),不清 `skill_uses` / `skills_seen` / `identities`,SKILLS 页与 operator 列表里那条脏数据还在。
2. **鉴权太宽**:它用的 `TF_KEY` 被 `install.sh` 写进了每个同事的 shell rc,等于全队都有删库权限。
3. **没 UI、不可逆、无留痕**:只能 curl,删前看不到影响面,删错无法恢复,也无审计。

## 目标
- 提供一个受保护的后台页面 `/admin`,按 operator / 身份 / 会话 / skill 四个维度浏览并删除脏数据。
- 删除**全表级联**,删完页面立即干净(含 SKILLS 排行与 operator 列表)。
- 删除**可逆 + 可审计**:硬删 + 回收站(留底可恢复)+ 审计日志。
- 鉴权与全队分发的 `TF_KEY` **隔离**:新增 `TF_ADMIN_KEY`,由 Coolify Magic 变量自动生成。

## 非目标
- 不引入软删(派生视图查询多、与自然键幂等冲突、与保留期裁剪/有界存储相悖,详见 design 权衡)。
- 不引入外部数据库/账号体系/RBAC(与 ADR-0001 单容器一致);一把 `TF_ADMIN_KEY` 即可,不做按人授权。
- 不做磁盘空间回收(`VACUUM` 属独立在线运维动作,会锁库,不进清理台)。
- 不负责"让对方停止上报":删除只清历史,源头仍在上报的会重现,工具侧只提示、不接管对方配置。

## 方案概述(详见 design.md)
- 新增 `TF_ADMIN_KEY` + `check_admin`,未配置时管理接口一律 403(生产安全默认关)。
- 抽一个 `_purge()` 全表级联函数,所有删除入口(含改造后的 `DELETE /v1/events`)都走它。
- 新增两张表 `admin_trash`(回收站,存源头行原文供恢复)、`admin_audit`(append-only 审计)。
- 新增 5 个管理端点:`GET /api/admin/inventory`、`POST /api/admin/preview`、`DELETE /api/admin/data`、`GET /api/admin/trash`、`POST /api/admin/restore`。
- 前端新增受保护路由 `/admin`(不进顶栏导航):清单 / 预览 / 二次确认 / 回收站。
- `TF_ADMIN_KEY` 在 `compose.yml` 用 `${SERVICE_PASSWORD_64_ADMIN}` 由 Coolify 自动生成,后台 Environment Variables 复制后粘进 `/admin` 钥匙框。

## 影响
- **新增 spec 域 `admin`**(本 change 的 spec-delta):删除/级联/回收站/审计/鉴权规则。
- specs/ingest:`skills_seen.first_day` 由"首次出现记录"补充为"删除/恢复时重算"的不变量。
- `server/app.py`:新增表、`check_admin`、`_purge`、5 个端点;改造 `DELETE /v1/events` 内部走 `_purge`。
- `frontend/`:新增 `views/Admin.tsx` 与路由、`lib/api.ts` 调用。
- 配置/文档:`compose.yml`、`.env.example`、`DEPLOY.md`、`PROTOCOL.md`、`docs/wireframes/pages/admin.md` + `flow.md`。
