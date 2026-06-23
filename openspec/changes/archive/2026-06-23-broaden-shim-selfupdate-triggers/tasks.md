# tasks:broaden-shim-selfupdate-triggers

部署顺序与依赖:本 change **只动客户端**(`shims/`),服务端 `/shims/manifest` 协议未变。所以
任意顺序部署都安全;客户端拉新文件即生效。

## 客户端

- [x] 1. `shims/tf_hook.py`:`SELFUPDATE_EVENTS` 从 `("SessionStart", "on_session_start")`
       扩展为 `("SessionStart", "on_session_start", "UserPromptSubmit", "Stop", "SessionEnd")`,
       并附注释说明节流共享、`PreToolUse` 故意排除。
- [x] 2. `shims/openclaw/reporter.mjs`:`import { spawn } from "node:child_process"`,
       新增 `DEFAULT_SELFUPDATE_PATH = ~/.tranfu/tf_selfupdate.py`,在 `createOpenClawSkillReporter`
       的 deps 上接受 `selfupdatePath` / `spawn` 注入。
- [x] 3. `shims/openclaw/reporter.mjs`:新增 `spawnSelfUpdate()` 内部函数 ——
       `env.TF_AUTO_UPDATE === "0"` 直接 return;否则 `spawn('python3', [selfupdatePath], {detached, stdio:'ignore', env})`,
       `.unref()`,监听 `error` 静默吞错;外层 `try/catch` 吞所有异常。
- [x] 4. `shims/openclaw/reporter.mjs`:在现有 `sessionStart` 函数里调用 `spawnSelfUpdate()`(只此一处)。

## 测试(待补)

- [ ] T1. `tests/test_hook.py`:加 case ——
        喂 `UserPromptSubmit` / `Stop` / `SessionEnd` 三个 event,断言 `_spawn_selfupdate` 真的 spawn 了进程
        (通过 mock `subprocess.Popen` 或检查计数器);并断言 `PreToolUse` 不触发。
- [ ] T2. `tests/test_openclaw_skill_reporter.mjs`:加 case ——
        注入假 `spawn`,sessionStart 触发后断言被调用了一次;`env.TF_AUTO_UPDATE='0'` 时断言不调用;
        假 `spawn` 抛错时断言 `sessionStart` 不抛、不打印。

## AI 验证流程(实施完跑一遍)

- [x] V1. `python3 -m pytest tests/` 全套 → 147 passed,无回归。
- [x] V2. `node --test tests/*.mjs` 全套 → 10 passed,无回归。
- [ ] V3. **线上回放**:推送到 main,等 Coolify 自动构建部署完;在客户端机器删除 `~/.tranfu/.selfupdate.json`
        绕过节流,让 Wing/NEZHA/小北 的某个长会话发一次 prompt;之后 `curl /api/state` 看那条 agent 的
        `shim_version` 从 `24116eef…` 翻到当前 manifest 的 hash。
- [ ] V4. **OpenClaw 验证**:阿萌 / 小北 的 OpenClaw 会话各开一次,等 1h 后或手动 `rm .selfupdate.json`,
        看 `/api/state` 该 OpenClaw 卡 `shim_version` 从 `None` 变为非空。

## 文档

- [ ] D1. `AGENTS.md`:`shims/` 注释里关于 `tf_hook.py(Claude Code 钩子分发)` 一行,
        加一句"自更新触发面包含 SessionStart/UserPromptSubmit/Stop/SessionEnd"(可选,仅一行说明);
        OpenClaw 同样在描述里注明"sessionStart 触发自更新"。视 AGENTS.md 现有粒度决定是否更新。

## 完成状态

- [x] 代码改动(任务 1-4)已落地并通过现有测试。
- [ ] 回归测试(T1/T2)、线上验证(V3/V4)、文档(D1) **未做**,留给后续补齐 / 上线确认。
- [x] 本 tasks 文件状态:可归档(代码已上、协议未破)。
