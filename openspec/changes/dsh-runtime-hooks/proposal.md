# 变更提案:dsh-runtime-hooks(DSH / DeepSeek Harness 作为新 runtime 接入活跃时长与 Skill 统计)

- 状态:Draft(设计已用官方随包文档与本机 `dsh` CLI 验证;事件名/payload 待真机核对,见 tasks 0)
- 关联:ADR-0009(钩子 stdin)、ADR-0016(Codex 源文件补采)、self-update-shims、hermes-skill-usage-from-skill-view、PROTOCOL.md §5
- 后续:`openspec/specs/onboarding/spec.md` 并入 spec delta;新增 ADR(DSH 插件壳 + Python 分发器)

## 背景 / 问题

Claude Code / Codex / Hermes 已通过 hook → `tf_hook.py` → `tf_report.py` 上报状态、活跃时长与 Skill 使用。
DSH(DeepSeek Harness,桌面/CLI agent 宿主)尚未接入,其会话在看板上不可见。

调研结论(来源:DSH 随包文档 `cordis-plugin-development` 技能与 `dsh` CLI 实测):

- DSH **没有**「配置事件名 → 执行脚本 → stdin JSON」式 hook;扩展方式是进程内插件
  (`export function apply(ctx, config)` + `ctx.on(...)`),以 bundle(npm 包 + YAML patch)形式装入 profile。
- 可观察事件包括 `session/created`、`session/disposed`、`session/event`(含 `turn/start`、`turn/end`)、
  `tools/pre-execute`、`tools/result`、`agent/error`、`agent/turn-stopping` 等;session id 取 `agent.session.id` / `session.id`。
- **可无人值守安装**:`dsh plugin --profile <name> add link:<目录>` 一步写入 profile `package.json` 的
  `dependencies` 与 `dsh.profile.bundles`,重复执行幂等(本机临时 `DSH_HOME` 实测)。
- 已安装插件的 JS 若被替换,需重启 DSH 才加载新模块;因此插件壳必须稳定,逻辑放 Python 随自更新升级。

## 目标

- 让 DSH 会话的 started / running / done 与 turn 内心跳进入既有活跃时长与身份合并模型
  (`operator + agent||runtime`),新增 `runtime=dsh`。
- DSH 工具调用名为 `skill` / `skill_view` 时,复用 `_skill_name` 采集 Skill 使用。
- **安装与更新全自动**:检测到 DSH 家目录即默认安装插件壳;之后随服务端 shim manifest 自动更新。
- 服务端零改动:`server/shim.py` 对 `shims/` 做 `os.walk`,新目录自动进 manifest。

## 非目标

- 不改服务端 ingest、协议字段、活跃时长算法、前端。
- 不上报 prompt / 代码 / 工具参数 / 输出;只传事件名、tool 名、session id、skill 名(同既有 shim 约束)。
- 不追踪 token / 费用(ADR-0002)。
- 不复制 DSH 的 profile 管理逻辑,只调用官方 `dsh plugin ... add`。
- 不在 DSH 内用 `plugin_manager` 工具安装(需要审批、不可无人值守)。

## 方案概述(详见 design.md)

1. `shims/dsh/` 放一个**稳定的薄壳 bundle**:订阅 DSH 事件,把原始事件序列化成 JSON,
   detached spawn `~/.tranfu/tf_dsh_event.py`;壳内带 `protocol` 版本号。
2. `shims/tf_dsh_event.py`(Python 标准库):事件名 → Claude 风格 `hook_event_name` / `tool_name` / `session_id`,
   再交给 `tf_hook.py` 的既有分发(`resolve` 复用),事件映射与 Skill 识别全在这里,随自更新升级。
3. `shims/tf_dsh_plugin.py`:检测 DSH、定位 `dsh` 可执行文件、对每个 profile 幂等 `add link:~/.tranfu/dsh`;
   由 `tf_selfupdate.py` 的 `_ensure_dsh_plugin()` 与 `install.sh` 调用,不受 1 小时节流限制。
4. `install.sh` 支持 `--runtime dsh`,生成 `tf_env.dsh.sh`;检测到 DSH 家目录时自动按 `dsh` 装一份。
5. 文档、openspec spec delta、ADR、测试同步。

## 影响

- 新增 runtime 枚举值 `dsh`(Pods 卡片 runtime 展示、`tf_profile.py` 探测需认识;前端若有 runtime 白名单需核对)。
- manifest 新增 `dsh/*` 文件;老客户端自更新即可拉到,无需重装。
- 自动写入用户 DSH profile 的 `package.json` / lockfile(经官方 CLI),需在文档与开关(`TF_DSH_PLUGIN=0`)中明示。

## 风险

- DSH 事件名/payload 与 README 不一致 → tasks 0 真机核对;Python 分发器对未知事件静默忽略。
- 壳变更需重启 DSH 才生效 → 壳极简、带 `protocol` 版本,Python 侧向后兼容旧壳。
- `dsh` 不在 PATH(桌面版)→ 回退探测应用包内路径;找不到则静默跳过。
- 多 profile(desktop / web …)→ 逐个安装;只对含 `dsh.profile` 的 profile 操作。
