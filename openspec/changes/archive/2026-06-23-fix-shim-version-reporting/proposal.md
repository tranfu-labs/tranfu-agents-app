# 变更提案:fix-shim-version-reporting(shim 版本上报与看板三态)

- 状态:Proposed
- 关联:specs/ingest、specs/board、`self-update-shims` (前置 change)

## 背景 / 问题

`self-update-shims` 引入了 `shim_version` 字段、本地 manifest 基线和服务端 `/shims/manifest`,
看板可以标记"过期客户端"。实际线上观察到一个让看板长期不可信的协议盲点:

1. **客户端**:`tf_hook.py` 的事件映射表 `MAP` 只在 `SessionStart` / `on_session_start` 这两个事件
   `attach_profile=True`,即只有"会话开始"那一刻才调用 `tf_profile.collect()` 把 `shim_version` 塞进 payload。
   后续 `PreToolUse / UserPromptSubmit / Stop / SessionEnd` 心跳一律不带这个字段。
2. **服务端**:`/v1/events` 接收 profile 时是**全量替换**(`INSERT OR REPLACE` 整张 profile JSON)。
   PROFILE_KEYS 包含 `shim_version`,但只要某次上报 profile 里没这个字段,**整张 profile 替换后该字段就丢了**。
3. **前端**:`isOldShim = Boolean(latest && agent.shim_version !== latest)` 把"字段缺失"误判为"旧版"。
4. **OpenClaw 适配层**:`shims/openclaw/reporter.mjs` 自拼 payload,**完全不接 `tf_profile`**,
   导致 OpenClaw 上报永远不带 `shim_version`。

三层缺陷叠加的真实后果:
**活跃 agent 在升级了 shim 后,看板仍长期显示"旧 shim"**——只要会话不重启、PreToolUse 不断刷新最新事件,
profile 替换就会把刚装的新 `shim_version` 抹掉。这次的现场样例是 `操作员=Wing / agent=美羊羊` 的 Claude Code 会话,
本地 manifest 已是 `24116eef7dbf`,但 `/api/state` 返回的对应 card 完全没有 `shim_version` 字段。

## 目标(MUST)

- **协议层**:`shim_version` 从"profile 子字段"升格为**事件可选顶层字段**;客户端 SHOULD 在每次心跳都附带。
- **服务端**:`shim_version` 不再走 profile 全量替换;改为独立 sticky 表,**只在收到非空值时更新,缺失则保留旧值**。
- **看板三态**:`agent.shim_version` 缺失 → `unknown`(灰,"等待客户端心跳");等于服务端 manifest → `current`(常态);
  不等 → `outdated`(橙,"旧 shim")。不再把"未知"误标为"旧"。
- **OpenClaw 修复**:`reporter.mjs` 启动时读一次 `~/.tranfu/manifest.json` 缓存 `shimVersion`,每次 POST 注入。

## 非目标

- 不动 `install.sh` / `tf_selfupdate.py` 的下载与原子替换协议。
- 不改 profile 全量替换语义本身(这是另一个口子,与本 bug 无关)。
- 不引入"shim 版本号比较语义"(不做 semver 大小判断,继续用字符串等价)。
- 不为前端搭测试基础设施;`shimState()` 三态判定走 AI 验证流程(demo 三态截图)。

## 影响

- **specs/ingest**:`shim_version` 字段位置与语义升级 —— 由"profile 字段"改为"事件顶层可选字段";
  服务端按身份独立 sticky,profile 全量替换不再覆盖。
- **specs/board**:`/api/state` 中 agent card 的 `shim_version` 来源改为"该 agent 最近一次非空上报值";
  看板状态由二态扩为三态。
- 不影响 `specs/onboarding`。
