# spec delta:onboarding(安装与接入域)—— hermes-multi-profile-install

## ADDED Requirements

### Requirement: install.sh 以当前 `$HOME` 作为 Hermes profile 安装的唯一真理源

`install.sh` 在执行时 MUST 以当前 shell 的 `$HOME` 推断本次安装服务的 Hermes profile,且 MUST 使用同一推断函数
决定:(a) shim 文件落盘根 `$HOME/.tranfu/`,(b) profile 名(`$HOME` 路径形如 `*/.hermes/profiles/<name>/home`
取 `<name>`,否则视为 `default`),(c) config.yaml 默认位置(profile 形态 → `$HOME/../config.yaml`,
default 形态 → `$HOME/.hermes/config.yaml`)。

config.yaml 最终路径优先级 MUST 为:
1. 命令行 `--hermes-config <path>`(最高);
2. `$HERMES_CONFIG_FILE` 环境变量;
3. 上述推断结果。

profile 名 MUST 在写入 shell rc / 事件协议前做安全化(`[^a-zA-Z0-9_-]` 替换为 `_`);原始名仅用于日志参考。

#### Scenario: profile 子环境推断
- **WHEN** 在 `hermes --profile ops` 子环境跑 `install.sh`,此时 `$HOME=/home/u/.hermes/profiles/ops/home`
- **THEN** 推断 `profile_name=ops`、`config_path=/home/u/.hermes/profiles/ops/config.yaml`、
  shim 落 `/home/u/.hermes/profiles/ops/home/.tranfu/`

#### Scenario: 默认环境推断
- **WHEN** 在用户主 HOME(无 profile 路径痕迹)跑 `install.sh`,`$HOME=/home/u`
- **THEN** 推断 `profile_name=default`、`config_path=/home/u/.hermes/config.yaml`、shim 落 `/home/u/.tranfu/`

#### Scenario: 显式参数优先
- **WHEN** 跑 `install.sh --hermes-config /custom/path.yaml`
- **THEN** `config_path` 使用 `/custom/path.yaml`,忽略 `$HERMES_CONFIG_FILE` 与推断

#### Scenario: profile 名安全化
- **WHEN** `profile_name` 原始值含非法字符(如 `weird/name`)
- **THEN** 写入的 `TF_AGENT` 为 `hermes-weird_name`,且 stdout 输出安全化结果

### Requirement: Hermes hook command 必须写绝对路径

`install.sh` 写入 config.yaml 的 Hermes `pre_tool_call` hook command MUST 是当前 `$HOME` 展开后的绝对路径
`<$HOME>/.tranfu/tf-hermes-hook.sh`,MUST NOT 使用 `~` 字面、`${HOME}` 字面或任何依赖 Hermes 自身做 expanduser/
expandvars 的写法。该字符串与该 profile 安装位置绑死,跨 profile 不可共享。

#### Scenario: profile 子环境写绝对路径
- **WHEN** 在 `$HOME=/home/u/.hermes/profiles/ops/home` 跑 `install.sh`
- **THEN** config.yaml 中 hook command 字面值为 `/home/u/.hermes/profiles/ops/home/.tranfu/tf-hermes-hook.sh`

#### Scenario: 默认环境写绝对路径
- **WHEN** 在 `$HOME=/home/u` 跑 `install.sh`
- **THEN** config.yaml 中 hook command 字面值为 `/home/u/.tranfu/tf-hermes-hook.sh`

### Requirement: Hermes hook block 必须用 marker 注释包夹并支持整段替换

`install.sh` 在 Hermes config.yaml 写入的 hook 配置 MUST 包裹在 `# >>> tranfu-hermes-hook >>>` 与
`# <<< tranfu-hermes-hook <<<` 两行 marker 之间。升级时 MUST 用 marker 定位旧 block 并整段替换,
MUST NOT 在 config.yaml 末尾追加重复 block。block 内 MUST 含一行审计注释(写入时间 UTC + shim 版本)。

#### Scenario: 首装追加 block
- **WHEN** `install.sh` 跑在没有 marker block 的 config.yaml 上
- **THEN** 新 block 追加到文件末尾(保留尾部空行),包含 marker 对、审计注释、hook 段

#### Scenario: 升级整段替换
- **WHEN** `install.sh` 跑在已有 marker block 的 config.yaml 上
- **THEN** 旧 block 被整段替换为新 block,文件中只有一对 marker、一个 block;marker 外内容不受影响

#### Scenario: 幂等
- **WHEN** 连续两次跑同一 `install.sh`(无新变化)
- **THEN** 第二次跑后 config.yaml 字节级与第一次相同;stdout 含 "no changes"

### Requirement: 升级时旧节点必须归档而非删除

`install.sh` 在升级路径上发现以下三类旧节点时 MUST 归档而非删除:

1. **marker 外的旧字面 hook 行**(匹配 `command:.*tf-hermes-hook.sh`):MUST 在该行前加注释前缀
   `# [archived by tranfu install <UTC ISO8601>] `,原行保留作为审计痕迹。
2. **本 profile 内的旧 wrapper 孤儿**(在新 manifest `namespace` 字段外的 `~/.tranfu/<file>`,但属于
   tranfu 拥有的文件名集合):MUST `mv` 到 `$HOME/.tranfu/.archive/<UTC ISO8601>/<原相对路径>`,保留相对结构。
3. **主 HOME 错位残留**(`$HOME != /home/$(whoami)` 时,主 HOME 下存在 `.tranfu/tf-hermes-hook.sh`):
   MUST 仅输出 WARN 列出该路径与建议处理方式,MUST NOT 自动 mv 或删除(可能是另一 profile 在用)。

归档失败(权限/磁盘满)MUST 非静默退出且 exit code != 0,与 shim 运行期"静默失败"约束相反 —— install 期错误
必须告知用户。`.archive/<UTC ISO8601>/` 目录 MUST NOT 在没有实际归档发生时被创建(保幂等)。

#### Scenario: 归档旧字面行
- **WHEN** config.yaml marker 外含 `      - command: ~/.tranfu/tf-hermes-hook.sh`
- **THEN** install 后该行变为 `# [archived by tranfu install <ts>]       - command: ~/.tranfu/tf-hermes-hook.sh`

#### Scenario: 归档孤儿 wrapper
- **WHEN** `~/.tranfu/tf-legacy-thing.sh` 存在、在 namespace 内、不在新 manifest 中
- **THEN** install 后该文件位于 `~/.tranfu/.archive/<ts>/tf-legacy-thing.sh`,原位置不存在

#### Scenario: 错位残留仅警告
- **WHEN** `$HOME=/home/u/.hermes/profiles/ops/home` 且 `/home/u/.tranfu/tf-hermes-hook.sh` 存在
- **THEN** stdout 出现 WARN 列出该路径;`/home/u/.tranfu/` 内容不变

#### Scenario: 私有文件不动
- **WHEN** `~/.tranfu/my-private-script.sh` 不在 namespace 内
- **THEN** install 流程不动该文件,无论是否在新 manifest 中

#### Scenario: 幂等归档
- **WHEN** 已归档过一次后再跑 `install.sh`,无新孤儿
- **THEN** 不创建新 `.archive/<ts>/` 目录;stdout 含 "no changes"

### Requirement: 多 profile 下 agent 命名必须可区分以保看板分卡

`install.sh` MUST 按推断的 profile 名设置 `TF_AGENT`:
- `is_default == true` → `TF_AGENT=hermes`(向后兼容,**已装的 default profile 用户数据不受影响**)。
- `is_default == false` → `TF_AGENT=hermes-<safened_profile_name>`。

用户命令行 `--agent <A>` 显式覆盖最优先(沿用现有 onboarding 规则)。

同机同 operator 的 default 与 profile 安装 MUST 在 `/api/state` 呈现为两张独立卡片(由 ADR-0006 的
`(operator, agent)` 合并语义自然实现,服务端无须改动)。

#### Scenario: default profile 卡片命名
- **WHEN** 在用户主 HOME 跑 `install.sh`
- **THEN** shell rc 写入 `TF_AGENT=hermes`,/api/state 卡片标识为 `(operator, hermes)`

#### Scenario: 子 profile 卡片命名
- **WHEN** 在 `profiles/ops/home` 子环境跑 `install.sh`
- **THEN** shell rc 写入 `TF_AGENT=hermes-ops`,/api/state 卡片标识为 `(operator, hermes-ops)`

#### Scenario: 同机双 profile 分卡
- **WHEN** 同一 operator 在同机的 default 与 ops 各装一次、各触发 skill_view 一次
- **THEN** /api/state 出现两张独立卡片,各自的 skill 上报不混淆

#### Scenario: 用户 --agent 覆盖
- **WHEN** 跑 `install.sh --agent my-custom-name`(任意 profile 子环境)
- **THEN** `TF_AGENT=my-custom-name`,不受 profile 推断影响

### Requirement: shim 探测必须按当前 `$HOME` 对应 profile 来定位资源

`shims/tf_profile.py` 探测 Hermes 已装 skill 清单、IM `secrets.env`、`memory.md`,以及 `shims/wrapper/tf-doctor`
检查 hook 接线状态时,MUST 调用与 `install.sh` 等价的 `profile_home_from_env($HOME)` 推断函数,而 MUST NOT
硬编码 `~/.hermes/...` 路径。同一次探测 MUST 只针对当前 `$HOME` 对应的 profile,MUST NOT 跨 profile 汇总。

#### Scenario: profile 子环境探测 skill
- **WHEN** 在 `$HOME=/home/u/.hermes/profiles/ops/home` 跑 `tf_profile.py`
- **THEN** skill 清单来自该 profile 推断的 skills 目录,不包含其它 profile 已装但本 profile 未装的 skill

#### Scenario: doctor 只报当前 profile
- **WHEN** 在 ops 子环境跑 `tf-doctor`
- **THEN** hook 检查结果只反映 `<profile_root>/config.yaml` 是否含 marker block;不扫描其它 profile

## MODIFIED Requirements

### Requirement: shim manifest 必须声明 tranfu 拥有的文件名集合(namespace)

`shims/manifest` 与服务端 `/shims/manifest` 响应 MUST 包含顶层 `namespace` 字段,列出 tranfu 拥有的 shim 文件名
白名单。`install.sh` 升级时 MUST 仅对 namespace 内的孤儿文件归档,MUST NOT 触碰白名单外的私有文件。

旧客户端读不到 `namespace` 字段时 MUST 回退到当前文件名硬编码列表(行为等价于不归档孤儿),不得失败。

#### Scenario: manifest 含 namespace
- **WHEN** `GET /shims/manifest`
- **THEN** 响应含顶层 `namespace`(字符串数组),列出 tranfu 拥有的 shim 文件名

#### Scenario: 旧客户端兼容
- **WHEN** 旧版 `install.sh`(不读 `namespace`)拉取新 manifest
- **THEN** 安装流程正常完成,行为与本变更前一致(不归档孤儿)
