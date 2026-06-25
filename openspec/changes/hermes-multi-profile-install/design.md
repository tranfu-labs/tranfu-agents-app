# 设计:hermes-multi-profile-install

## 信源声明

- Hermes v0.17.0 行为:基于用户提供的 ops profile 真机失败日志(`agent.shell_hooks: shell hook failed
  (event=pre_tool_call command=~/.tranfu/tf-hermes-hook.sh): command not found`)+ 队友默认 profile 装机
  成功案例对比。强假设(`expanduser` 用主进程 HOME)由 Task 0 真机最终确认,任何偏差以真机为准。
- profile 目录布局:基于队友诊断 `/home/hermes/.hermes/profiles/ops/config.yaml` 与
  `/home/hermes/.hermes/profiles/ops/home/.tranfu/`。Task 0 须确认 default profile 也走
  `~/.hermes/config.yaml`(而非 `~/.hermes/profiles/default/config.yaml`)。

## 核心原则:`$HOME` 是真理源

**`install.sh` 跑时的当前 shell `$HOME` 就是这次要装的 profile 的真实 home。所有路径都从它推。**

这条原则的来源是用户的工作模式:**切到要装的 profile 子环境再跑 `install.sh`**,从不"一次装多个"。
所以不需要扫描候选目录、不需要枚举所有 profile —— `$HOME` 是什么,这次就装这个。

它直接简化了 4 件事:
- shim 文件位置 = `$HOME/.tranfu/`(原状)。
- config.yaml 位置 = 从 `$HOME` 推出来(见下文 § 推断函数)。
- profile 名 = 从 `$HOME` 切出来(`*/profiles/<name>/home` → `<name>`,否则 `default`)。
- hook command 写到 config.yaml 里 = `<$HOME 展开后绝对值>/.tranfu/tf-hermes-hook.sh`,
  跟 Hermes 怎么 expanduser 无关。

`tf_profile.py` / `tf-doctor` / `install.sh` 共用同一份**纯函数** `profile_home_from_env($HOME)`,
返回 `{hermes_root, profile_name, config_path, skills_dir, im_secrets_path, memory_path}`。
单一推断逻辑、多处复用,避免硬编码飘散。

## 已确认的决策

1. **hook command 写绝对路径**,不用 `~`、不用 `$HOME`、不用 `sh -c`。在 `install.sh` 写 config.yaml 时
   就把 `$HOME` 展开,落入 yaml 是字面绝对值。优点:对 Hermes 的 `expanduser` / `expandvars` 一概不依赖,
   v0.17 已知失败模式直接消失。代价:hook 字符串与 profile 绑死,跨 profile 不可移植 —— 这正是想要的(每个
   profile 自己装、自己绑、互不影响)。
2. **config.yaml 三优先级定位**:`--hermes-config <path>` > `$HERMES_CONFIG_FILE` env > 由 `$HOME` 路径形态推断。
   三档同时实现 ≠ 复杂:`install.sh` 加几行 case + 一个推断函数即可,推断函数与 `tf_profile.py` / `tf-doctor`
   共用。env 档要先 Task 0 验 Hermes 是否真的暴露。
3. **profile 名从 `$HOME` 推**,优先级:`$HERMES_PROFILE` env(若 Task 0 验出来有) > `$HOME` 路径切片
   (`*/profiles/<name>/home` → `<name>`,否则 `default`)。Hermes 的命名通常 ASCII + 下划线,**写入 `TF_AGENT`
   前还要做一次安全化**(`[^a-zA-Z0-9_-]` → `_`),避免 yaml/事件协议被怪字符注入。
4. **agent 命名规则**(对应新增 ADR-0022):
   - `profile_name == "default"`(或路径推不出 profile 名) → `TF_AGENT=hermes`(向后兼容)。
   - 否则 → `TF_AGENT=hermes-<safe_profile_name>`。
   - 用户 `--agent A` 显式覆盖最优先(沿用 onboarding spec 现有规则)。
5. **marker block 注释包夹**:`# >>> tranfu-hermes-hook >>>` ... `# <<< tranfu-hermes-hook <<<`,
   升级时识别整段、整段替换。block 内写绝对路径 hook、可附加管理元信息(写入时间、shim 版本)作为审计行注释。
6. **旧节点归档而非删除**:`mv` 到 `$HOME/.tranfu/.archive/<UTC时间戳>/`,目录结构保留原相对路径
   (便于人肉对照)。重跑 `install.sh` 若无新东西可归档,**不产生空目录**(`.archive/<时间戳>/` 仅在实际有 mv
   时创建);幂等性约束之一。
7. **错位残留不自动动**:当 `$HOME ≠ /home/<user>`(典型 hermes 主用户主 HOME)且主 HOME 下存在
   `.tranfu/tf-hermes-hook.sh` 时,`install.sh` 输出 WARN 列出该路径并提示"可能是另一个 profile 在用,
   如确认无人使用请手动 mv 走"。**不接管主 HOME**。
8. **不扫描所有 profile**:`tf-doctor` 只报当前 `$HOME` 对应 profile 的状态,与 `install.sh` 对称。
   若队友要查"这台机上其它 profile 装没装",切过去再跑 `tf-doctor` —— 与 Hermes 本身的"切 profile 才操作
   该 profile"心智一致。
9. **shim 探测仅看当前 profile**:`tf_profile.py` 上报的 skill 清单 / IM / memory 都是"这个 profile 装了什么",
   不试图汇总跨 profile —— 因为上报本身也按 profile 身份分卡了,跨 profile 汇总反而模糊。

## 推断函数 `profile_home_from_env(HOME)`

纯函数(无副作用、不读文件,只字符串操作),返回结构如下:

```
{
  "hermes_root":      <profile 根目录> | <用户主 HOME 下 ~/.hermes>,
  "profile_name":     <profile 名> | "default",
  "config_path":      <config.yaml 绝对路径>,
  "skills_dir":       <profile 内 skills 目录>,
  "im_secrets_path":  <profile 内 secrets.env 路径>,
  "memory_path":      <profile 内 memory.md 路径>,
  "is_default":       bool
}
```

逻辑(伪代码):

```
m = re.match(r"^(.+/\.hermes)/profiles/([^/]+)/home$", HOME)
if m:
    hermes_root = m.group(1) + "/profiles/" + m.group(2)   # profile 根
    profile_name = m.group(2)
    is_default = False
    config_path = hermes_root + "/config.yaml"             # profile 形态约定:profile 根/config.yaml
else:
    hermes_root = HOME + "/.hermes"                        # default 形态
    profile_name = "default"
    is_default = True
    config_path = hermes_root + "/config.yaml"

skills_dir      = HOME + "/.hermes/skills"   # default 形态约定
im_secrets_path = HOME + "/.hermes/secrets.env"
memory_path     = HOME + "/.hermes/memory.md"
```

> 注意:profile 形态下 skills/secrets/memory 是否仍在 `<HOME>/.hermes/...` 下取决于 Hermes 真机布局
> (Task 0 第 4 条要确认)。**当前实现按 default 形态约定写,profile 形态如果不一样,在 Task 0 后修正这段。**

`--hermes-config <path>` 显式参数提供时,覆盖 `config_path` 字段,其它不变。
`$HERMES_CONFIG_FILE` env 存在时,覆盖 `config_path`(若同时有显式参数,显式优先)。

## 为什么是绝对路径,不是别的路

| 候选 | 失败模式 |
| --- | --- |
| `~/.tranfu/tf-hermes-hook.sh`(现状) | 依赖 Hermes 主进程 HOME 做 `expanduser`,profile 子环境必错 |
| `${HOME}/.tranfu/tf-hermes-hook.sh` | 依赖 Hermes 对 `command` 字段做 `expandvars`,v0.17 是否做未知 |
| `["sh","-c","exec \"$HOME/.tranfu/...\""]` | 多一层 fork,且依赖 hook 子进程 `$HOME` 为 profile-scoped,
                                              v0.17 行为未真机确认。可行但比绝对路径多一个未知 |
| 绝对路径(选定) | install.sh 跑时即知,落字面,Hermes 无须做任何展开 —— 失败模式为零 |

> 选 sh -c 的唯一情况:Task 0 验出 hook 子进程 `$HOME` **不**等于 profile-scoped HOME,且 Hermes 提供 `$HERMES_HOME`
> 等变量 —— 这时 sh -c + Hermes env 变量比绝对路径更鲁棒(profile 改名/搬目录不破)。**但目前没证据支持此假设,默认走绝对路径**。

## 数据流

```
用户切到要装的 profile 子环境(或默认环境)
→ 跑 install.sh
→ install.sh: $HOME → profile_home_from_env($HOME) → {config_path, profile_name, ...}
→ install.sh: 下载 shim manifest、写 ~/.tranfu/、写 shell rc(TF_AGENT 按 profile_name 推)
→ install.sh: 读 config_path
    ├─ 解析 marker block:存在 → 整段提取作为"旧 block"
    ├─ 扫 marker 外字面行:匹配 `command:.*tf-hermes-hook.sh` → 标记为"旧字面行"
    └─ 重写 config.yaml:
       - marker 外旧字面行 → 整行加 `# [archived by tranfu install <ts>]` 前缀
       - 末尾(或合适位置)写新 marker block:
         # >>> tranfu-hermes-hook >>>
         # written by tranfu install <ts>, shim_version=<v>
         hooks:
           pre_tool_call:
             - command: <HOME 绝对值>/.tranfu/tf-hermes-hook.sh
         # <<< tranfu-hermes-hook <<<
→ install.sh: 旧 wrapper 文件孤儿(manifest 比对) → mv 到 $HOME/.tranfu/.archive/<ts>/
→ install.sh: 主 HOME 错位残留检测 → 仅 WARN
→ install.sh: 发 started --profile 事件(身份 = hermes 或 hermes-<profile>)
→ 看板按 (operator, agent) 合并卡片 → default 与子 profile 各自分卡
```

运行期:

```
用户在该 profile 内触发 skill_view
→ Hermes 加载本 profile 的 config.yaml,触发 pre_tool_call hook
→ exec 写死的绝对路径 → ~/<profile_home>/.tranfu/tf-hermes-hook.sh
→ tf-hermes-hook.sh source $HOME/.tranfu/tf_env.hermes.sh(profile-scoped,自然隔离)
→ stdin 喂 tf_hook.py → SKILL_TOOLS = {"skill","skill_view"} 命中 → tf_report.py --skill <name>
→ 服务端 skill_uses (session_id, skill, "used") 落库
→ /api/state.skills 排行出现
```

## 改动文件与职责

### `install.sh`(主要改动)

新增/修改职责:
1. **profile 推断**:实现 `profile_home_from_env`(sh 版本,正则用 `expr` / `case`),输出 6 个变量。
2. **config.yaml 定位**:显式 `--hermes-config <path>` 参数 > `$HERMES_CONFIG_FILE` > 推断 `config_path`。
3. **`TF_AGENT` 推断**:`is_default=true` → `hermes`;否则 `hermes-<safe(profile_name)>`。
   用户 `--agent` 显式覆盖最优先。
4. **marker block 读写**:用 sed/awk 找 `# >>> tranfu-hermes-hook >>>` ... `# <<< tranfu-hermes-hook <<<`,
   提取旧 block(若存在);写新 block 时整段替换,不存在则追加到文件末尾(保留尾部空行)。
5. **旧字面行归档**:对 marker 外的 `command:.*tf-hermes-hook` 行整行加注释前缀。
6. **旧 wrapper 孤儿归档**:对比本地 `~/.tranfu/manifest.json` 中"上一次安装的文件清单"(本变更也要扩
   manifest 含 `namespace`)与新 manifest;不在新里、且属于 tranfu namespace 的文件 → `mv` 到 `.archive/<ts>/`。
7. **主 HOME 错位检测**:`$HOME != /home/$(whoami)` 时,若 `/home/$(whoami)/.tranfu/tf-hermes-hook.sh` 存在,
   输出 WARN(不动)。
8. **幂等保护**:重跑无变化 → 不产生新 archive 目录、config.yaml 不抖动(diff 为空)。

`bash -n` 校验保持过;`install.sh` 仍只依赖 POSIX sh + curl/wget + 标准 awk/sed。

### `shims/wrapper/tf-hermes-hook.sh:7-12` 注释

把当前示例 yaml(用 `~/...`)改成绝对路径示例,并加一句:
> 由 `install.sh` 在写入 config.yaml 时把当前 `$HOME` 展开成绝对路径;**请勿手工 copy 这段 yaml,profile 改了路径会错**。

### `shims/manifest`(扩字段)

新增顶层 `namespace`:声明 tranfu 拥有的 shim 文件名集合(白名单)。`install.sh` / `tf_selfupdate.py` 归档孤儿
时,只动这个集合内的文件,绝不踩用户/队友手工放在 `~/.tranfu/` 的私有文件。

服务端 `/shims/manifest` 同步:
- 返回结构加 `namespace`;旧客户端读不到时按当前文件名硬编码列表回退(`tf_*.py`、`wrapper/tf-*` 等),
  行为不变(不归档孤儿)。
- ADR-0007(从域名分发)与 ADR-0010(本地 hook 安装幂等)不变。

### `shims/tf_profile.py`

抽 `profile_home_from_env` 到 `shims/_hermes_profile.py`(共用纯函数,Python 与 sh 各自实现一份,等价语义)。
- `:185` 改成读 `info.skills_dir`(默认 `<HOME>/.hermes/skills`,Task 0 后 profile 形态可能改 `<profile_root>/skills`)。
- `:238` 改成读 `info.im_secrets_path`。
- `:284` 改成读 `info.memory_path`。
- 探测全程基于当前 `$HOME`,不跨 profile 汇总。

### `shims/wrapper/tf-doctor:156`

改成 `info = profile_home_from_env($HOME)` 后报 `info.config_path` 是否含 marker block。只看当前 profile 的状态。

### `shims/tf_hooks.py:26` 注释

更新:`$HOME` 在 profile 子环境已 profile-scoped,`tf_env.hermes.sh` 自然每 profile 一份,**不会**与 default
profile 撞文件。**前提**是用户按"切到 profile 子环境再跑 install.sh"操作,这一约定要在文档侧明确。

### 新增 `docs/adr/0022-hermes-multi-profile-agent-identity.md`

锁住 agent 命名规则(default = `hermes`、profile = `hermes-<name>`)、为什么分卡(看板可读性 + 多 profile 跑不同
任务流时合并失真)、向后兼容路径(default 用户已有数据完全不变)。登记 `docs/adr/README.md`。

### 文档

- `QUICKSTART.md` / `USAGE.md`:加 "Hermes profile 子环境安装" 小节:**先切到目标 profile 子环境再跑 install.sh**,
  示例命令带 `--profile ops` 的 hermes 启动命令。
- `SKILL.md`:同上,补"Hermes profile" 一节给 agent 自助读。
- `UPDATE.md`:加 "升级旧 Hermes 装机" 小节,说明 `install.sh` 会:
  - 把旧 `command:.*tf-hermes-hook.sh` 字面行加注释前缀(保留)
  - 把旧 wrapper 孤儿 mv 到 `~/.tranfu/.archive/<UTC时间戳>/`(可找回)
  - **不动**主 HOME 下的潜在残留(只 WARN)
- `DEPLOY.md`:不变。

### `docs/architecture/module-map.md`

加 `shims/_hermes_profile.py`(纯函数推断)的边界:`install.sh` / `tf_profile.py` / `tf-doctor` 共用,
不依赖任何运行时状态。

## 升级时的旧节点归档:详细规则

按用户特别要求,**默认归档而非删除**,留反悔余地。

### 三类旧节点

| 类别 | 识别方式 | 处理 | 何时跑 |
| --- | --- | --- | --- |
| **旧 hook 字面行**(`~/.tranfu/...`) | config.yaml marker 外、匹配 `command:.*tf-hermes-hook.sh` | 整行加前缀 `# [archived by tranfu install <UTC ts>] ` | 每次 install.sh |
| **旧 wrapper 孤儿** | 本地 `~/.tranfu/<file>` 在 namespace 集合内、但不在新 manifest 里 | `mv $HOME/.tranfu/<file> $HOME/.tranfu/.archive/<ts>/<file>` | 每次 install.sh |
| **主 HOME 错位残留** | `$HOME != /home/$(whoami)` 且 `/home/$(whoami)/.tranfu/tf-hermes-hook.sh` 存在 | **仅 WARN**,不动 | 每次 install.sh |

### 幂等性

- 重跑 install.sh 无新变化时:不创建新 `.archive/<ts>/` 目录、config.yaml 内容不变、stdout 输出"no changes" 行。
- archive 目录布局:`$HOME/.tranfu/.archive/<UTC时间戳>/<相对原路径>` —— 保留相对路径便于人肉对照与回滚。
- 归档失败(权限/磁盘满)→ install.sh 应失败而非静默吞掉(与"shim 静默失败"约束不同,**install 期是显式动作**,
  失败必须告诉用户)。

### 回滚

用户手动:`mv` `.archive/<ts>/*` 回去 + 在 config.yaml 把注释前缀去掉。`install.sh` 不自动回滚 —— 重装即可
得新 block,无须回滚旧的。

## 口径细节

### "在哪里跑 install.sh"

文档必须把这句写清楚:**先切到目标 profile 子环境(`hermes --profile ops` 等),再跑 `install.sh`**。
这是用户行为约定,也是"`$HOME` 是真理源"成立的前提。

### 一次只装一个 profile

每次 install.sh 只服务当前 `$HOME` 对应那个 profile。要装多个 → 切多次、跑多次。每次互不影响。

### 卡片身份合并

`/api/state` 按 ADR-0006 的 `(operator, agent || runtime)` 合并:
- default profile:`agent=hermes` → 卡片标识 = `(op, hermes)`
- ops profile:`agent=hermes-ops` → 卡片标识 = `(op, hermes-ops)`
- 自然分卡,不需要服务端改动。

### profile 名安全化

`profile_name` 在 `install.sh` 写入 shell rc / 事件之前必须做 `[^a-zA-Z0-9_-] → _` 替换,防止用户用奇葩字符
(中文 / 空格 / shell 元字符)注入 yaml 或事件 JSON。原始名仅在日志里保留参考。

### 默认 profile 用户不受影响

- 不在 profile 子环境 → `profile_home_from_env($HOME)` 走 default 分支
- `TF_AGENT=hermes` 不变
- config.yaml 路径 `~/.hermes/config.yaml` 不变
- 首次升级会把旧字面行 `command: ~/.tranfu/...` 加注释、写新 marker block(写绝对路径)—— **行为等价但更鲁棒**
  (不再依赖 Hermes expanduser)
- 已有事件 / 排行数据完全不变

## 已知边界与风险

- **风险 1**:Task 0 验出 Hermes hook 子进程 `$HOME` 不是 profile-scoped(假设破)。应对:fallback 到
  `["sh","-c","exec \"$HOME/.tranfu/tf-hermes-hook.sh\""]` 或 Hermes env 变量;design 要在 Task 0 通过后才
  正式锁绝对路径。
- **风险 2**:Hermes profile config.yaml 不在 `<profile>/config.yaml` 而在别处。应对:`profile_home_from_env`
  推断逻辑修正,test 矩阵补真机布局。
- **风险 3**:profile 名安全化把不同 profile 撞名(`profile/a` 与 `profile_a` → `profile_a`)。应对:不太
  可能出现合法 profile 名包含 `/`,但安全化时若有非法字符替换发生,在 install.sh 日志里**明确告知**安全化结果。
- **风险 4**:用户在两个 profile 共用同一个 `operator` + 同一个名(`--agent hermes` 强制覆盖),会合并卡片。
  这是用户行为,文档警告即可,不强制阻止。
- **风险 5**:升级时主 HOME 错位残留(类别 3)未来变成"需要清理"的场景。当前默认 WARN 是因为可能正好是另一个
  profile 在用。如果验证发现"几乎所有用户都希望自动归档" → 后续 ADR 提案改默认。

## 部署 / 回滚

部署:
1. 服务端 `/shims/manifest` 加 `namespace` 字段(向后兼容,旧客户端不读不影响)。
2. 新 `install.sh` / `tf_profile.py` / `tf-doctor` / `_hermes_profile.py` / `tf-hermes-hook.sh` 注释更新
   推到服务端 `shims/`。
3. 队友重跑 `install.sh`(在他们当前所在的 profile 子环境):default profile 用户得到带 marker block 的
   绝对路径 hook + `TF_AGENT=hermes`(行为不变);profile 用户首次得到绝对路径 hook + `hermes-<profile>` 身份卡。
4. 已装错位残留的用户(如果有)收到 WARN,自行处理。

回滚:
- 服务端可同时支持新旧 `install.sh`(从 manifest namespace 字段判断);极端情况下回滚 `install.sh` 到旧版,
  已写入的 marker block 不会被 hermes 误读(仍是合法 yaml),只是不会再被升级流程识别,留作 dead 配置。
  config.yaml 旧字面行的注释前缀也是 yaml 合法语法,无害。

## 验证计划(实现后据此填结果)

1. **真机 ops profile 首装**:在 `hermes --profile ops` 子环境跑 `install.sh` →
   `cat <profile_root>/config.yaml` 含 marker block + 绝对路径 hook + profile-scoped HOME →
   `skill_view(name)` → 远端 `/api/skills` 与 `/api/state.skills` 排行出现该 skill,卡片 agent = `hermes-ops`。
2. **真机默认 profile 首装**:在用户主 HOME 跑 `install.sh` → marker block 写到 `~/.hermes/config.yaml` →
   `skill_view` → 远端排行出现,卡片 agent = `hermes`(数值与现状一致)。
3. **真机同机双 profile**:依次在 default + ops 子环境各跑一次 `install.sh`、各触发一次 skill_view →
   `/api/state` 出现两张独立卡片(`hermes` 和 `hermes-ops`),skill 归位准确。
4. **升级路径**:在已装旧版的机器上跑新 `install.sh` →
   - 旧 `command: ~/.tranfu/...` 行被注释前缀(`# [archived by tranfu install <ts>] command: ~/...`)
   - 新 marker block 出现在末尾(或合适位置)
   - 旧 wrapper 孤儿(若有)在 `~/.tranfu/.archive/<ts>/` 下
   - hook 命中:`skill_view` → 远端排行出现
5. **幂等**:连跑 `install.sh` 两次 →
   - 第二次 stdout 含 "no changes"
   - config.yaml 内容与第一次完全一致(diff 为空)
   - `.archive/` 下无新建空目录
6. **错位残留容错**:profile 子环境,故意在 `/home/<user>/.tranfu/tf-hermes-hook.sh` 留旧文件 → 跑 `install.sh`
   → 输出 WARN 列出该路径,**不动它**;hook 仍正常装到 profile-scoped HOME。
7. **doctor 与 profile 单一视角**:在 ops profile 跑 `tf-doctor` → 只报 `<profile_root>/config.yaml` 状态;
   切到 default 再跑 → 只报 `~/.hermes/config.yaml`。
8. **profile 名安全化**:用 `--profile "weird/name"` 启动 hermes(或别的极端名)→ install.sh 输出"profile name
   safened: weird/name → weird_name",`TF_AGENT=hermes-weird_name`。

任一条失败 → 回 Task 0/1 找根因。
