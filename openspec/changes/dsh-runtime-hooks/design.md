# 设计:dsh-runtime-hooks

## 1. 数据流

```
DSH 进程内事件 ──(ctx.on)──▶ 薄壳 bundle(index.js)
                              │ detached spawn,JSON 走 stdin,永不 await、永不抛错
                              ▼
              ~/.tranfu/tf_dsh_event.py   (事件映射 + Skill 识别,随自更新升级)
                              │ 构造 Claude 风格 payload
                              ▼
                    tf_hook.py 既有分发(resolve → tf_report.py)
```

壳每个监听器都**只观察**:`tools/pre-execute` 等 waterfall 事件先 `return next()` 再异步 spawn,
不改写决策、不阻塞(见 DSH practices:不负责决策的 waterfall 监听器必须 `next()`)。

## 2. 事件映射(以真机核对结果为准,tasks 0)

| DSH 事件 | → hook_event_name | 状态 |
|---|---|---|
| `session/created` | `SessionStart` | started(带 profile) |
| `session/event` type=`turn/start` | `UserPromptSubmit` | running,拉起心跳 |
| `tools/pre-execute` | `PreToolUse`(`tool_name`=`name`) | running |
| `tools/result` | `PostToolUse` | running |
| `session/event` type=`turn/end` | `Stop` | done,收尾心跳 |
| `session/disposed` | `SessionEnd` | done |
| `agent/error` / `agent/turn-stopping` | `Stop` | done(防孤儿 running 段) |

- session id:`agent.session.id` 或 `session.id`,从事件对象取,不依赖环境变量(ADR-0009)。
- 观察最终工具结果用 `tools/result`,不用 `tools/post-execute`(后者只用于转换结果)。
- 在 `agent/created` 里拿 `agent.ctx` 注册 per-agent 监听,并在插件自己的 effect 里保存 disposer(DSH practices)。
- Skill:`PreToolUse` 且 tool 名属 `SKILL_TOOLS`(`skill` / `skill_view`)才取名,复用 `_skill_name`;
  `TF_REPORT_SKILLS=0` 关闭。具体 tool 名待真机核对,未命中则不采,不猜测。

## 3. 为什么「壳 + Python」

DSH 官方:新装 bundle 可 HMR 生效,**替换已装包需重启**才加载新 JS 模块。若把映射写在 JS,
每次升级都要用户重启 DSH。把易变逻辑放 Python 脚本,走现有 `tf_selfupdate.py`(manifest + sha256 + staging + 回滚),
下一次事件即用新逻辑。壳只在「订阅事件集合」变化时才需重装,届时 bump `protocol`。

壳向 Python 传 `{"protocol":1,"event":"<dsh 事件名>","session_id":...,"tool":...,"type":...}`;
Python 对未知 `protocol` / 未知事件静默 `exit 0`;高 protocol 的壳 + 旧 Python 同样静默(不上报,不报错)。

## 4. 安装与更新(全自动)

`shims/tf_dsh_plugin.py`(标准库,绝不抛错):

1. **检测**:`DSH_HOME`(默认 `~/.dsh`)下存在 `profiles/` 即认为已装 DSH;否则静默返回。
2. **定位 CLI**:`shutil.which("dsh")` → macOS `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`
   → 其它平台常见路径(后续补);找不到则静默返回。
3. **枚举 profile**:`$DSH_HOME/profiles/*/package.json` 且含 `dsh.profile`。
4. **幂等安装**:profile `package.json` 的 `dependencies` 已含 `@local/tranfu-agents` 且 link 指向当前
   `~/.tranfu/dsh` → 跳过;否则 `DSH_HOME=... dsh plugin --profile <name> add link:<~/.tranfu/dsh>`,
   超时 60s,子进程输出丢弃。
5. **壳升级**:`~/.tranfu/dsh/package.json` 的 `version` 与 profile 记录的不一致时重跑 `add`(幂等)。
   因为是 `link:`,文件同步后目录内容即最新,重启 DSH 后加载新壳。
6. **开关**:`TF_DSH_PLUGIN=0` 关闭安装与升级;`TF_AUTO_UPDATE=0` 关闭文件更新(沿用)。

调用点:
- `install.sh`:检测到 DSH 家目录 → 自动写 `tf_env.dsh.sh` 并调用 `tf_dsh_plugin.py install`;
  显式 `--runtime dsh` 也走同一路径。
- `tf_selfupdate.py`:新增 `_ensure_dsh_plugin()`,与 `_ensure_codex_hook_guard` / `_ensure_skill_update_schedule`
  同级,在 `main()` 中节流前执行,不受 1 小时 manifest 节流限制。

自更新的触发源:DSH 插件每次事件都会 spawn `tf_dsh_event.py`;它在 `session/created` 对应的 `SessionStart`
等 `SELFUPDATE_EVENTS` 上沿用既有 detached 拉起 `tf_selfupdate.py` 的逻辑(与 `tf_hook.py` 一致)。

## 5. 身份与环境

- `tf_env.dsh.sh` 与其它 runtime 一致,由 `install.sh` 生成(`TF_SERVER/TF_KEY/TF_OPERATOR/TF_RUNTIME=dsh/TF_AGENT…`)。
- `tf_dsh_event.py` 自己 source 该文件等价逻辑:解析 `tf_env.dsh.sh` 的 `export` 行注入子进程环境
  (不依赖 shell),避免 DSH 进程环境缺失导致身份丢失。
- 不读取 `tf_env.sh`(共享文件,会被其它 agent 覆盖)。

## 6. 边界与安全

- 全链路静默:壳 `try/catch` 吞一切、`child.unref()`;Python 异常 `exit 0`。
- 壳只发事件名/tool 名/session id/skill 名;不发 `arguments`、messages、输出。
- manifest 路径检查沿用 `_safe_parts` / `_inside`,`dsh/` 子目录不越界。
- 不手改 profile 文件,只调官方 CLI。

## 7. 备选方案(已否决)

- 手写 profile `package.json`/`cordis.patch.yml`:违反官方「不要手写」指引,且易与 lockfile 不一致。
- 通过 DSH 内 `plugin_manager install_bundle` 安装:需审批,不可无人值守。
- 轮询 `~/.dsh/sessions` 日志补采(类 Codex rollout):实时性差,活跃时长无法准确。
- 逻辑全放 JS:升级需重启 DSH。
