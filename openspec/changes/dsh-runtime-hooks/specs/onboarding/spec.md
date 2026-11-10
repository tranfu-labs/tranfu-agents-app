# spec delta:onboarding(dsh-runtime-hooks 新增的规则)

> 合入后并入 `openspec/specs/onboarding/spec.md`。

## 新增规则(MUST)
- 支持 `runtime=dsh`(DeepSeek Harness)。DSH 以进程内插件而非 stdin hook 接入:`shims/dsh/` 的薄壳 bundle
  只订阅事件并 detached 调用 `~/.tranfu/tf_dsh_event.py`,事件映射与 Skill 识别必须位于 Python 分发器,
  不得写在需重启才生效的 JS 壳内。
- 壳与分发器全程静默:不得抛错、不得阻塞 DSH、不得改写 DSH 的工具/请求决策;waterfall 监听器必须 `next()`。
- session id 必须取自事件对象(`agent.session.id` / `session.id`),不得依赖环境变量。
- 壳只传递事件名、tool 名、session id、skill 名;不得传 prompt、messages、工具参数或输出。
- 检测到 DSH 家目录(`$DSH_HOME` 或 `~/.dsh` 下存在 `profiles/`)时,安装与自更新必须默认自动安装插件壳,无需用户确认。
- 安装必须且只能通过官方 CLI `dsh plugin --profile <name> add link:<~/.tranfu/dsh-plugin>`,
  不得手写 profile 的 `package.json`、`cordis.patch.yml` 或 lockfile;重复执行必须幂等。
- 找不到 DSH 家目录、`dsh` 可执行文件、可用 profile,或 CLI 失败时必须静默跳过,不影响 install.sh 其余步骤、hook 与上报。
- `TF_DSH_PLUGIN=0` 必须关闭 DSH 插件的安装与升级;`TF_AUTO_UPDATE=0` 必须关闭文件自更新(沿用)。
- DSH 壳或分发器随 `/shims/manifest` 更新:Python 分发器更新在下一次事件生效;壳 JS 更新需重启 DSH 生效。
- 壳与分发器通过 `protocol` 版本协商:未知 protocol 或未知事件必须静默忽略。
- 身份使用 `tf_env.dsh.sh`,不得读取共享 `tf_env.sh`。

## 可验证行为(新增)
- 无 DSH 家目录 → 安装/ensure 不调用任何子进程,退出码 0。
- 有 DSH 家目录、profile 未装插件 → 调用一次 `dsh plugin --profile <name> add link:...`。
- profile 已装且壳版本一致 → 不调用 CLI。
- `dsh` 找不到或 CLI 非零退出 → 静默,不抛错。
- `session/created` → `started`;`turn/start` → `running`;`turn/end` → `done`;`session/disposed` → `done`。
- tool 名属 `skill` / `skill_view` 的 `tools/pre-execute` → 上报 `--skill <名>`;`TF_REPORT_SKILLS=0` 时不上报。
- 未知 protocol / 未知事件 → 不上报,退出码 0。
- 服务端 manifest 含 `dsh/*` 条目且 `target` 不越界;修改 `tf_dsh_event.py` 后本机在下一次事件前自动更新。
