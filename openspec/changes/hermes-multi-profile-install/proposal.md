# 变更提案:hermes-multi-profile-install(Hermes 多 profile 一次成功 + 升级时旧节点归档)

- 状态:Proposed(待真机抓 Hermes v0.17 hook 子进程 env + 验证 profile config.yaml 定位逻辑后实现)
- 关联:ADR-0005(shim 自动探测 profile)、ADR-0006(按身份合并卡片)、ADR-0007(从域名分发安装)、
  ADR-0010(本地 hook 安装幂等)、ADR-0017(Hermes 从 `skill_view` 采集);拟新增 ADR-0022(Hermes 多 profile 身份分卡)
- 后续:**有 spec delta**(本变更修改 onboarding 的安装/接入规则,见 `specs/onboarding/spec.md`)

## 背景 / 问题

Hermes v0.17 支持 profile-scoped HOME:每个 profile 在 `<hermes_root>/profiles/<name>/home/` 下有独立的
`$HOME` 与配置(`<hermes_root>/profiles/<name>/config.yaml`),profile 之间互不影响。用户的实际工作模式是
**在哪个 profile 子环境里就装哪个**(切到该 profile 的 shell → 跑 `install.sh`),不存在"一次装多个 profile"
这种事。所以**只要 `install.sh` 把当前 `$HOME` 当成单一真理源,所有路径自然就对**。

但当前 `install.sh` 和文档假设 hook command 可以写 `~/.tranfu/tf-hermes-hook.sh` 这种**字面**写法,
依赖 Hermes 自己对 `command` 字段做 `expanduser` —— 这套写法只在默认 profile 下侥幸跑通(Hermes 主进程 HOME
= 用户主 HOME = `.tranfu/` 实际所在,展开对得上),**任意 profile 子环境装机都失败**:

- `install.sh` 在 profile 子环境跑 → `$HOME` 已是 `<profile>/home`,`.tranfu/` 装在 `<profile>/home/.tranfu/`。
- Hermes 加载该 profile 的 `config.yaml` 时仍以**主进程 HOME**(`/home/hermes`)做 `expanduser`,
  `~/.tranfu/tf-hermes-hook.sh` → `/home/hermes/.tranfu/...`,该路径不存在。
- 日志:`agent.shell_hooks: shell hook failed (event=pre_tool_call command=~/.tranfu/tf-hermes-hook.sh):
  command not found`。

链路其它环节(`tf_hook.py` 识别 `skill_view`、`tf_report.py` 上报、服务端 `skill_uses` 落库)**都是好的**,
就卡在 hook command 引用错位。本变更要顺带一并解决的还有 3 件:

1. **多 profile 身份**:同机不同 profile 跑不同任务,在看板上**应分卡**(default 仍叫 `hermes`,子 profile 叫
   `hermes-<profile>`),不合并(否则违反 ADR-0006 合并语义)。
2. **升级时旧节点归档**(用户特别要求):队友把已装机器从旧写法升到新写法时,旧 `command:` 行、错位的 shim
   残留、旧 wrapper 文件**必须 mv 到归档目录而非 rm**,留反悔余地。
3. **shim 探测路径硬编码**:已知 4 处 `~/.hermes` 硬编码,profile 子环境下漏报已装 skill 清单、IM 集成、memory、
   hook 接线状态(`shims/tf_profile.py:185/238/284`、`shims/wrapper/tf-doctor:156`)。

## 目标

- 任何 profile(default 或子 profile)切到该 profile 子环境后跑 `install.sh` → 跑一次 `skill_view(name)`
  → 远端排行出现该 skill,**全程无需手改任何 yaml**。
- 同机不同 profile 在 `/api/state` **分卡**:default profile 仍叫 `hermes`(向后兼容),子 profile 叫
  `hermes-<profile>`,`operator` 同一身份继承。
- `install.sh` 升级路径:**旧节点归档而非删除**;**幂等**(重跑不重复归档、config.yaml 不残留多份 hook block)。
- shim 探测/doctor 在子 profile 下也能找全当前 profile 的 skill 清单、IM 集成、memory、hook 接线状态。

## 非目标

- 不改 Claude Code / Codex / OpenClaw 既有链路与口径(一行不动)。
- 不改 Hermes skill 采集口径(沿用 ADR-0017,本变更只解决"hook 接得上")。
- 不影响默认 profile 已装机用户的现状:卡片身份仍叫 `hermes`、`/api/state` 数值不变。
- 不引入非标准库依赖(`install.sh` / shim 仍只用 sh + Python 标准库,不引 `ruamel.yaml`)。
- 不尝试"一次安装跨多个 profile":安装总是基于当前 `$HOME` 一个 profile,跨 profile 装多次是用户行为,
  `install.sh` 保证每次都对、互不污染即可。
- 不动用户主 HOME 下自有的 `.tranfu/`(可能是另一个默认 profile 在用),只列警告。
- 不上报 profile 名以外的新字段;`agent` 字段已有,只是命名规则变化。

## 方案概述(详见 design.md)

四件事,核心思路:**`install.sh` 跑时的 `$HOME` 就是这次要装的 profile 真实 home,所有路径都从它推**。

1. **hook command 用绝对路径**:`install.sh` 写 config.yaml 时把 `<$HOME>` 展开,落到 yaml 里是字面绝对路径
   `command: <$HOME_展开后>/.tranfu/tf-hermes-hook.sh`。**不再依赖 Hermes 的 expanduser、不需要 `sh -c`**。
   写入后即与该 profile 绑死,跨 profile 不冲突。
2. **config.yaml 定位**(三优先级,实现简单):
   - `--hermes-config <path>` 显式参数(最高)
   - `$HERMES_CONFIG_FILE` env(若 Hermes 在 shell env 暴露,Task 0 验)
   - 否则从 `$HOME` 推断:
     - `$HOME` 路径形如 `*/.hermes/profiles/<name>/home` → config = `$HOME/../config.yaml`(profile 形态)
     - 否则 → config = `$HOME/.hermes/config.yaml`(default 形态)
3. **多 profile 身份分卡**:`install.sh` 从同一套 `$HOME` 推断逻辑提取 profile 名 —— `*/profiles/<name>/home`
   → 写入 `TF_AGENT=hermes-<name>`;默认 profile 仍写 `TF_AGENT=hermes`。可被 `--agent` 显式覆盖(沿用现有约定)。
4. **升级时旧节点归档**:`install.sh` 在写入 config.yaml 前:
   - hook block 用 marker 注释包夹(`# >>> tranfu-hermes-hook >>>` / `# <<< tranfu-hermes-hook <<<`),
     已存在则整段替换、不重复追加。
   - **marker 外**的旧字面行(匹配 `command:.*tf-hermes-hook.sh`)→ 整行前缀 `# [archived by tranfu install
     <UTC时间戳>]`,保留作为审计痕迹,不删除。
   - 错位的 shim 残留(当前 `$HOME` 与 hermes 主 HOME 不同时,主 HOME 下若发现 `.tranfu/tf-hermes-hook.sh`)
     → **不自动动**,只列警告(可能是另一个 profile / 默认 profile 在用)。
   - 本 profile 内旧版 wrapper 文件(对比 `~/.tranfu/manifest.json` 哈希,不匹配且不在新 manifest 里的孤儿)
     → mv 到 `$HOME/.tranfu/.archive/<UTC时间戳>/`(保留尾部目录便于回滚)。

shim 探测同步采用相同的"以当前 `$HOME` 为真"原则:`tf_profile.py:185/238/284` 三处把 `HOME / ".hermes"` 换成
**与 `install.sh` 同一份 `profile_home_from_env($HOME)` 推断函数**输出的 profile 根目录;`tf-doctor:156`
同样用这个函数定位当前 profile 的 config.yaml(只报当前 profile 状态,不扫"所有 profile",因为 doctor 也总是在
某个 profile 子环境跑)。

## 影响

- **`install.sh`**:接入 `profile_home_from_env($HOME)` 推断、config.yaml 定位三优先级、marker block
  写入/替换、旧节点归档(mv 不 rm)、profile 名 → `TF_AGENT` 推断、幂等;
  **保留对默认 profile 的兼容**(`$HOME` 不含 `profiles/<x>/home` 形态 → 走 default 流程,`agent` 仍写 `hermes`,
  数据完全不变)。
- **`shims/wrapper/tf-hermes-hook.sh:7-12`** 注释里示例 yaml 改成绝对路径范例(并加一句"由 `install.sh` 写入时
  展开,不要手工 copy"),从源头杜绝复发。
- **`shims/tf_profile.py:185`(skill 探测)** / **`:238`(IM `secrets.env`)** / **`:284`(memory)**:
  三处 `HOME / ".hermes"` 改成调用同一个 `profile_home_from_env($HOME)` 函数得到的 `.hermes` 根。
- **`shims/wrapper/tf-doctor:156`**:同上 — 用 `profile_home_from_env($HOME)` 推断当前 profile 的
  config.yaml 路径;只报当前 profile 的 hook 接线状态(不跨 profile 扫描)。
- **`shims/manifest`**:加 `namespace`(标识 tranfu 拥有的文件名集合),供升级时识别孤儿 wrapper;
  服务端 `/shims/manifest` 返回结构变更,旧客户端读不到 namespace 时按当前文件名硬编码回退。
- **`shims/tf_hooks.py:26`** 注释:更新说明 profile 子环境里 `$HOME` 已隔离,`tf_env.hermes.sh` 在 profile-scoped
  HOME 下自然每 profile 一份,不会撞文件。
- **新增 ADR-0022 `hermes-multi-profile-agent-identity`**:锁住"default = `hermes`、profile = `hermes-<name>`"
  命名规则;登记 `docs/adr/README.md`。
- **文档**:`QUICKSTART.md` / `USAGE.md` / `SKILL.md` 加 Hermes profile 子环境安装步骤(**在 profile 子环境里跑
  install.sh** 是关键);`UPDATE.md` 说明升级会把旧节点归档到 `.archive/`(用户能找回);`DEPLOY.md` 不变。
- **spec delta**:`openspec/specs/onboarding/spec.md` 增加 multi-profile 安装规则与可验证行为
  (见本变更 `specs/onboarding/spec.md`)。
- **架构地图**:`docs/architecture/module-map.md` 标注 `install.sh` 与 `profile_home_from_env` 这个共用推断函数
  的归属(应放 shim 公共层供 `install.sh` / `tf_profile.py` / `tf-doctor` 共用)。

## 待确认(实现前的真机前置)

Task 0 在装了 Hermes v0.17 的 ops profile 上一次性验完:

1. **hook 子进程 `$HOME` 是否就是 profile-scoped HOME**:决定 hook command 写绝对路径是否完全成立(假设是,
   若不是要在 hook env 里再加 `HERMES_*` 变量兜底)。
2. **Hermes 在 hook 子进程 env 里是否注入 `$HERMES_CONFIG_FILE` / `$HERMES_HOME` / `$HERMES_PROFILE`**:决定
   `install.sh` 的 config.yaml 三优先级是否能用第二档,以及 profile 名推断是否能用 env 而不是路径切片。
3. **profile config.yaml 落盘位置**:确认 `<hermes_root>/profiles/<name>/config.yaml` 这一约定;若 Hermes 实际
   走别处(如 `<profile>/home/.hermes/config.yaml`),修正 `profile_home_from_env` 推断。
4. **profile 子环境下 `<profile>/home/.hermes/skills` 是否就是 skill 装载位置**(default 是 `~/.hermes/skills`):
   决定 `tf_profile.py:185` 改造形态。

任一条与本提案假设有出入,实现前**先改方案再写代码**。
