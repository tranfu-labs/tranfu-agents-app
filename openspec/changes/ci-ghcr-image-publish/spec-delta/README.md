# spec-delta（本变更无业务规则增删）

本变更属于"运维基础设施 / CI 发布链路"，不修改任何业务域（`admin` / `board` / `ingest` / `onboarding`）的事实规格。归档时**不需要**向 `openspec/specs/` 合并 delta，只移动 change 目录到 `archive/`。

仅在 AGENTS.md 加一行指明镜像发布机制（已写进 tasks.md）。

参考先例：`openspec/changes/archive/2026-06-11-root-docker-entrypoint/` 同样无 `spec-delta/` 内容（该归档目录直接没有这个子目录）。
