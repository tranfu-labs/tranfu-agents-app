# 设计:codex-skill-usage-from-rollout

## 已确认的决策(2026-06-12 与需求方逐项确认)

1. **目标**:补上 Codex 的 skill 使用漏报,让排行可信。仅 Codex;Claude Code 现有链路不动。
2. **机制**:钩子唤醒后**解析 rollout 源文件**,不在 hook 内识别 shell 命令(需求方选定)。
3. **口径**:只认 rollout 中 `function_call` 记录、其 `arguments` 读取了已装目录下
   (`.codex/` 或 `.claude/` 点目录前缀)`skills/<名>/SKILL.md` 的——提示词点名、讨论 skill 名、
   工具输出回显、`apply_patch` 改写、skill 作者仓库里散落的 SKILL.md 都不计。宁缺毋错。
4. **回填**:不回填,从上线起算。
5. **隐私**:沿用 `TF_REPORT_SKILLS=0`,不加新开关;PROTOCOL.md 注明 Codex 下会本地读会话文件。

## 为什么是"解析源文件",不是"hook 内识别"

两条路都能拿到信号。需求方选解析源文件,取舍如下:

- hook 内识别(在 `PreToolUse` 看到 Codex 的 shell 命令字符串匹配 `sed … SKILL.md`):改动更小、
  零读盘,但只能看见**当下这条命令**,无法回看一轮里更早的读取,且强依赖 Codex 把 skill 读取
  暴露为可被 hook 拦截的 shell 调用——其公开 hooks 支持范围明确不含非 shell/非 MCP 工具。
- 解析源文件(本方案):rollout 是 Codex 自己落盘的**完整**事实,轮次结束时该读取必已 flush;
  一次扫描覆盖整轮;未来若要从源文件提取更多信号(子代理树、耗时)也走同一入口。代价是依赖
  rollout 的私有格式、脚本要读会话文件、每轮重扫有重复读盘。靠"只解析、失败静默、服务端去重"消化。

## 数据流

```
Codex 触发 Stop / SessionEnd 钩子(已挂 tf_hook.py,见 hooks.json)
→ tf_hook.scan_codex_skills():TF_RUNTIME==codex 且事件∈{Stop,SessionEnd} 且 TF_REPORT_SKILLS≠0
→ tf_rollout_scan.scan_session(sid):
    glob $CODEX_HOME/sessions/**/rollout-*-<sid>.jsonl(通常一个,多个全扫)
    逐行:cheap 子串预过滤 "SKILL.md" → json 解析 → 只取 payload.type=="function_call"
    → 对 arguments 字符串正则提取 .codex|.claude /skills/<名>/SKILL.md → 去重
→ 每个名字:tf_report.py --status done --step "skill: <名>" --session <sid> --skill <名>
→ 既有 ingest 链路:事件带 skill+session_id → INSERT OR IGNORE skill_uses(session_id,skill)
→ (show-skill-usage)读时 GROUP BY 出排行
```

## 改动文件与职责

- `shims/tf_rollout_scan.py`(新)——
  - `find_rollouts(sid, home)`:按文件名锁定该会话的 rollout(`home` 默认 `$CODEX_HOME`/`~/.codex`)。
  - `skills_in_file(path)`:核心口径。只看 `function_call` 行,正则 `SKILL_RE` 提取已装 skill 名;
    名称按 `MAX_SKILL_NAME` 截断(对齐服务端)。`MAX_BYTES` 上限防超大会话拖过 hook 5s 超时。
  - `scan_session(sid)`:并集所有 rollout 的结果,排序返回。
  - `report_skills` / `main`:逐名调 `tf_report.py`;`--print` 供手动验证(只列名不上报)。
  - 约定:任何异常→空结果,绝不抛错。
- `shims/tf_hook.py`——抽出 `_event_name`/`_session_id`/`_run_report` helper;新增 `scan_codex_skills`
  在 `Stop`/`SessionEnd` 且 runtime 为 codex 时拉起扫描。`resolve()` 的 Claude `Skill` 逻辑保留不动。
- `install.sh`——分发列表加入 `tf_rollout_scan.py`(队友重跑后才下发到本机 `~/.tranfu`)。
- `PROTOCOL.md` §5 / `UPDATE.md` §6 / `docs/adr/0016-*` ——见 proposal「影响」。

## 口径细节:什么算"用过一个 skill"

`SKILL_RE = [/\\]\.(?:codex|claude)[/\\]skills[/\\]([^/\\]+)[/\\]SKILL\.md`,且仅作用于
`function_call` 行的 `arguments`。逐条对照真实 thread 验证:

| 记录 | 是否计入 | 原因 |
|---|---|---|
| `function_call` `sed … /repo/.codex/skills/web-product-craft/SKILL.md` | ✅ | 强信号:真读了已装 skill |
| `function_call` `head … ~/.claude/skills/credibility-review/SKILL.md` | ✅ | `.claude` 点目录同样算 |
| developer message 列出的技能目录(含多个 SKILL.md 路径) | ❌ | 是 message,不是 function_call |
| 用户提示词 "用 web-product-craft 审核…" | ❌ | 点名,非读取 |
| `function_call_output` 回显 SKILL.md 内容(含 `name:` 与别的路径) | ❌ | 是输出回显,不是读取动作 |
| `apply_patch` 改写 `.codex/skills/x/SKILL.md` | ❌ | 是 `custom_tool_call`,非 `function_call` |
| `cat /repo/docs/skills/streamlit/SKILL.md`(无点目录) | ❌ | 非已装 skill,作者仓库散落文件 |

## 已知边界(默认决策,可推翻)

- **rollout 是 Codex 私有格式**(本次锚定 CLI `0.137.0-alpha.4`)。升级可能破解析——靠键名/类型
  宽容 + 单测锁定 + 失败静默,坏掉的表现是"该 runtime 无数据",不是会话被打断。
- **首轮必读、后续从上下文复用不再读 SKILL.md** 的场景:口径是"一会话一次",首次使用必读一次,恰好覆盖。
- **agent 出于调试读已装 SKILL.md** 会被计入——接受,罕见且内容确实进了上下文。
- **arguments 里提到路径但非 shell 读取**(如把 SKILL.md 路径写进子代理派发消息)会被计入——
  接受:这类几乎总是该 skill 正被编排使用;且按会话去重,重复提到同名不放大。
- **子代理独立 session_id** → 其 skill 在子代理 rollout 里单独计数;与 ADR-0015 一致,未来读侧按 parent 归并。
- **每轮重扫整文件**:有重复读盘开销,但服务端 `(session_id, skill)` 唯一键保证不重复计数。

## 分发线:上线后数据何时开始产生

与 track-skill-usage 同一条线:`install.sh` 从 `$SERVER/shims` 拉文件,故需先把 `tf_rollout_scan.py`
与新版 `tf_hook.py` 部署到**服务端** `shims/`,队友重跑 `install.sh` 后其 Codex 会话才开始产生数据。
兼容性两个方向都成立:旧 hook(无扫描)+ 新服务端 = 与现状一致;新 hook + 旧服务端 = 多发几个带
`skill` 字段的普通事件,旧服务端按既有规则处理(有表则落库,无表的更早版本忽略未知字段)。

## 验证结果(2026-06-12)

- 单测:`tests/test_rollout_scan.py` 11 项全过(口径表逐行、幂等、截断、开关、hook 入口契约);
  全量 60 项全过,Claude 既有链路未回归。
- 解析层手验:`tf_rollout_scan.py --session 019eb6e9-… --print` → `["web-product-craft"]`,
  developer 技能目录未污染结果(真实数据上证明"只认 function_call"成立)。
- 端到端手验:新 Codex 会话 `019eb99d-…` 真执行 `web-product-craft` 后,
  远端 `/api/state` 排行出现该 skill(`sessions_total=1, users_30d=1`),
  且该会话 `current_step == "skill: web-product-craft"`——确认数据经本变更新链路上报,非他途。
