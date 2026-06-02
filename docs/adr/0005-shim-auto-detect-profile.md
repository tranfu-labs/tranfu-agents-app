# ADR-0005 shim 自动探测 profile,仅 role/about/tips 手填

- 状态:Accepted
## 背景
要"傻瓜式"接入,使用者不该手填一堆环境信息。
## 决策
`tf_profile.py`(标准库、绝不抛错)自动探测:运行时+版本、终端、位置、集成 IM、MCP、已装技能、集成。
三条路径(tf-run 的 started / Claude Code 与 Codex 钩子的 SessionStart / MCP reporter 首次上报)都附带 profile。
机器推不出来的语义字段 `role/about/tips/models` 通过 `--role/--about/--tips` 或 `TF_*` 手填(可选)。
## 后果
- ✅ 接入只需身份四要素 + 可选角色。
- ⚠️ 非 Claude 技能环境(如纯机器人)自动探测内容少属正常,靠手填角色补充。
