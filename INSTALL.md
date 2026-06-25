# INSTALL — TRANFU//AGENTS 一句话接入(给 AI agent 读)

本手册供**正在运行的 AI agent** 读后**自动一次性执行**,不是给人按步骤手敲的。
用户只会说一句自然语言(谁 + 拿这个 agent 干啥),例如:

> 「帮我接入 TRANFU//AGENTS,我是 bob,这个用来写代码。」

你(执行安装的 agent)读完本手册后,应当**不再让用户粘任何命令**,自己跑完全程。
**先建一个 TODO 清单再动手**(照它逐项推进、勾掉,别边装边问):
1) 读本机已登记身份(第 0a 步)  2) 解析 / 引导补全 operator + agent 用途(第 0b 步)
3) 取 server / key(第 0.5 步)  4) 执行安装(第 1 步)  5) 判读自检 JSON(第 2 步)  6) 回话确认(第 3 步)
`runtime` 不用问用户——**你就是那个 runtime**(见第 0 步)。
即使用户只说了一句「装一下」,也由你**主动引导补全**缺的信息(把要问的一次性问清,别边装边问);若这台机器**装过**,先读出已有身份让用户确认沿用,而不是从头再问。

---

## 第 0 步:确定身份(先读本机已有,再引导补全)

### 0a. 先读本机已登记身份(重装 / 加 agent 时免重复问)

先无网络读一次本机已有身份:

```bash
python3 ~/.tranfu/tf-doctor --identity --json 2>/dev/null
```

- 命令不存在 / `installed:false` / `identities` 为空 → 这台机器是**全新安装**,跳到 0b。
- 有内容 → 这台机器装过。把读到的**列给用户确认**,而不是从头再问,例如:

  > 这台机器已登记:调度员 **Wing**(server、key 都在)。已有编队:
  > · 美羊羊 [claude-code] — 规划项目  · 沸羊羊 [codex] — 写代码
  > 这次是**沿用其中某个重装**、**改一下**、还是**新增一个 agent**?

  - **沿用重装**:复用读到的 `operator/agent/role`,`runtime` 仍是你自己;server/key 不必再问。
  - **改**:在读到的值上改用户指定的字段。
  - **新增**:`operator` 沿用(同机通常同一个调度员),只补这次 agent 的**用途**(`runtime` 还是你自己)。

  > `--identity` 故意**不回显 key 明文**;重装时你不传 `--key` 也行,安装器会保留本机已存的 key。

### 0b. 解析 + 引导补全(全新安装,或用户没说全)

从用户那句话能解析多少先解析,**缺哪个就主动引导问哪个**(给默认/选项,别让他猜):

| 项 | 来源 / 引导 | 例 |
|---|---|---|
| `operator`(人 = 这个 Pod 的调度员) | 用户说「我是 X」;没说就问,可默认系统用户名。**填人名,不是 agent 名。** | bob |
| `agent`(用途短标签) | 用户说「用来做 Z」;没说就引导「给它起个用途:写代码=code / 文案=copy / 调研=research」 | code / copy / research |
| `runtime`(用哪个 agent) | **自动:你就是当前 runtime,不用问用户** | claude-code / codex / openclaw / hermes |

**runtime 自动确定规则(关键改进 —— 用户不用提)**:
- 你读这份手册、执行安装,**你自己就是要登记的那个 runtime**。Claude Code 在跑 → `claude-code`;Codex 在跑 → `codex`;OpenClaw → `openclaw`(`open-claw` 是别名);Hermes → `hermes`。
- 把它作为 `--runtime` 传给安装器即可;**不要问用户「你用什么 runtime」**。
- 若你无法确定自己是谁,也**不要瞎猜环境变量**:直接不传 `--runtime`,安装器会用进程内信号兜底识别(认不出就按 `cli` 注册)。
- **唯一例外**:用户明确点名要接另一个 runtime(如「把我的 codex 也接上」),才用用户说的那个。

**一人一 Pod**:`operator` 同名即同一个 Pod,自动归并,**不要问「加入哪个 Pod」**。
一个调度员可带多个 agent,用户会**对每个 agent 各说一句**;每次只登记当前这个。

---

## 第 0.5 步:拿接入地址 + 接入密钥(server / key)

来源优先级,**逐级取,取到就别再问**:
1. **用户这条消息**里若有 `server=…` / `key=…`(或「地址 …」「密钥 …」)→ 直接用。
2. **本机已有**(第 0a 步 `tf-doctor --identity` 显示 `has_key:true`)→ 直接复用,**重装免问**;你不传 `--key`,安装器也会自动保留本机已存的 key。
3. 都没有 → **只问这一次**;装好后写入 `~/.tranfu`,以后同机不再问。

> key 是「写入凭证」,只能往看板写遥测,不是任何 LLM 用量;泄露面小、可由管理员随时轮换。

---

## 第 1 步:执行安装(你自己拼命令,用户看不到 flag)

把上面解析到的值代入,直接运行(`--role` 可选,一句话定位;`runtime` 用你自己):

```bash
curl -fsSL <server>/install.sh | bash -s -- \
  --server <server> --key <key> \
  --operator <operator> --runtime <你自己的 runtime> \
  --agent "<用途短标签>" --role "<一句话定位,可省>"
```

安装器会(全部幂等,重跑安全):
- 先做**预检**(python3 / curl / 看板可达 / `~/.tranfu` 可写),任一不过会**明确报错并停**——按「错误处理」转述,**不要绕过**。
- 按 `<server>/shims/manifest` 校验 sha256 全量装 shim 到 `~/.tranfu`,清掉旧版孤儿文件,把身份 env 写进 `~/.tranfu`(key chmod 600);并往你登录 shell 的 rc 追加一段带标记的托管块(仅 `source` env + 加 `PATH`,幂等可重跑)。
- 若 runtime 是 `claude-code`/`codex` → 幂等合并用户级 hooks(保留已有其它 hooks);`hermes` → 装 hook 脚本并打印要合并进 `~/.hermes/config.yaml` 的配置(**合并后必须重启 Hermes gateway + Hermes 进程才生效——重要的事情见第 3 步 ⚠️**);`openclaw` → 装原生插件(装备态 Skill 统计)。
- **当场注册**到看板,并在最后自动跑一次 `tf-doctor` 自检。

---

## 第 2 步:自检(机器可读,你来判读)

```bash
python3 ~/.tranfu/tf-doctor --runtime <你自己的 runtime> --json
```

解析返回的 JSON(`.ok` 已等于「无 fail」,以它为准):
- `.ok == true` → 进第 3 步;其中 `warn` 项照常进行并提示用户(如 PATH 需开新终端、shim 待自动更新)。
- `.ok == false` → 取出所有 `status == "fail"` 的 check,按 `detail` 与「错误处理」分类处置:
  - 「agent 可自行修复」(缺身份 / 无 manifest → 重跑安装命令):重跑,至多 2 次。
  - 「需用户介入」(401 换 key、连不上 / VPN):停下,把该 check 的 `name`+`detail` 原样转述,等用户处理后再重跑,不硬来。
- **终态**:重试 2 次仍有 fail → 停止自动重装,把所有 fail 的 `name`+`detail` 如实汇总,明说「接入未完成 + 卡在哪一步」,交还用户决定,**不再循环**。

---

## 第 3 步:回话确认(用用户的语言)

把自检结果翻成人话告诉用户,例如:

> ✅ 已接入。去看板你的 Pod 看「<用途> [<runtime>] 运行中」。
> 若这次用到了 Skill,稍后 SKILLS 页会出现 used-only 排行与 7/30/90 天时间轴。

> ⚠️ **Hermes 接入:hook 装完 ≠ 已生效**
>
> 👉 **必须重启 Hermes gateway 和 Hermes 进程!**
> 👉 **必须重启 Hermes gateway 和 Hermes 进程!**
> 👉 **必须重启 Hermes gateway 和 Hermes 进程!**
>
> (重要的事情说三遍)只重启其中一个,SkillUsage 都不会上报;已有的 Hermes 客户端连接需断开重连。在用户口头确认「两个都重启了」之前,**不要**宣布接入完成。
>
> `claude-code` / `codex`:重启对应 agent 即可,Codex 首次遇到新 hook 会要求信任,确认一次即可。

---

## 错误处理(把原因转述给用户,别自行硬来)

| 现象 | 处置 |
|---|---|
| 预检/自检报「连不上看板」 | 服务端没部署好 / 域名没通 / 需连公司 VPN。让用户确认 `<server>` 能打开后重跑,**不要继续装**。 |
| `tf-doctor` 看板检查返回 HTTP 401 | key 不对。用管理员私发的最新 key 重装一次。 |
| `command not found: tf-run` / `tf-doctor` | PATH 未生效。用绝对路径 `~/.tranfu/tf-doctor`,或让用户开新终端 / `source` 其 shell rc。 |
| 预检报缺 `python3` / `curl` | 让用户装好对应工具后重跑,**绝不 `sudo`**。 |
| 写入权限 `EACCES` | 调整 `~/.tranfu` 归属/权限或 PATH,**绝不 `sudo`**。 |
| 无法确定自己是哪个 runtime | 不传 `--runtime`,让安装器兜底;仍认不出就按 `cli` 注册并告知用户。 |
| Hermes 装完后,看板上 Hermes runtime 长时间无 used skill / SkillUsage | 90% 是 gateway 或 Hermes 没重启(**重要的事情说三遍**:gateway 和 Hermes 两个进程都要重启)。让用户用其部署方式对应的命令分别重启后再观察,**不要**改 hook 配置去"修"。 |
| 重试 2 次仍 fail / `detail` 不在本表 | 停止自动重装,把 fail 的 `name`+`detail` 原样转述,标记接入未完成,交还用户。 |

---

## 禁止项(护栏)

1. **不要**把安装拆成一条条命令丢给用户手敲;按本手册**一次跑完**。
2. **不要**问用户「你用什么 runtime」——你自己就是(见第 0 步)。
3. **不要**靠环境变量去猜 runtime;拿不准就不传 `--runtime`,交给安装器兜底。
4. env **值**只写 `~/.tranfu`(含 key);登录 shell rc 里只允许那一段托管块(`source` + `PATH`),**不要**碰 `.bash_profile` / `.profile` / `.zprofile` 等其它 shell 配置;**不要**把 key 写进 hooks JSON / Hermes config(它们会 `source ~/.tranfu/tf_env.*`)。
5. 除第 0.5 步首次缺 server/key 外,**中途不要**反复找用户确认每一步。
6. **绝不 `sudo`**。
7. **不要**动用户已有的其它 hooks / skills;安装器只幂等合并自己的条目。

---

## 隐私(一句话)

默认只上报:谁 / 用途 / 状态 / 当前步骤 / 活跃时长,以及可安全识别的 Skill 名(不含参数/内容)。
用户若要回传 prompt/代码/输出,设 `TF_CAPTURE_CONTENT=1`,并提醒:开启后内容对所有有看板权限的人可见。
退出:对你说「关闭 TRANFU 上报 / 卸载」,删掉登录 shell rc(.zshrc/.bashrc)里 `# --- tranfu agent telemetry (managed) ---` 整段托管块,再删 `~/.tranfu` 即可。
