# 使用文档 — 一句话接入(全员)

把你平时用的 AI agent 接到团队 **TRANFU//AGENTS** 看板,**不用记命令、不用配环境变量**:
对你的 agent 说一句话,它自己装好并开始上报。接好后,团队能实时看到
**谁在跑、用哪个 agent、当前在哪一步、状态、活跃了多久**。

> **一人一 Pod**:用你的名字,你就是自己这个 Pod 的「调度员」,你用的每个 agent 是它的「编队」。
> 你不用选"加入哪个 Pod",系统按名字自动归到你名下。

---

## 一、对 agent 说一句话(全员通用)

把下面这句**填好三处空**(名字 / agent / 用途)发给你平时用的 agent。`server` 已按本团队填好,
`key` 用管理员**私发**给你的(别写进公开文档/截图):

> 帮我接入团队的 TRANFU//AGENTS 看板。
> 安装:运行  `curl -fsSL https://tranfu-agents-app.tranfu.com/install.sh | bash -s -- --server https://tranfu-agents-app.tranfu.com --key PASTE_KEY_HERE --operator 你的名字 --runtime agent形态 --agent "给它起个名" --role "它是干嘛的"`
> 我是 **<你的名字>**(调度员);这个 agent 叫「**<给它起个名>**」,用来 **<做什么>**。装好后开始上报。

agent 会自动:装好上报工具(到 `~/.tranfu`)→ 把你登记为**调度员**、这个 agent 进你的**编队** → 开始上报。
粘一次即可,装好后这台机器不再问。
新版安装器会按版本清单全量安装本地 shim,校验成功后写入本地版本清单;之后会话开始时后台自动更新
shim,不用再手动通知。若看板显示「旧 shim」,让该机器最后重跑一次安装命令即可进入自动更新链路。

**填好示例(多儿):**

> 帮我接入团队的 TRANFU//AGENTS 看板。
> 安装:运行  `curl -fsSL https://tranfu-agents-app.tranfu.com/install.sh | bash -s -- --server https://tranfu-agents-app.tranfu.com --key <私发的密钥> --operator nezha --runtime hermes --agent "多儿" --role "哪吒的 Lark 助手 · 写文档/调研"`
> 我是 **哪吒**(调度员);这个 agent 叫「**多儿**」,是我的 Lark 助手,用来写文档、做调研。装好后开始上报。

> **关键:`--operator` 填"人"的名字(nezha / 哪吒),不是 agent 名(多儿)。**
> 这样"多儿"会出现在**哪吒这个 Pod**下;你以后接的其它 agent 也都归到哪吒名下,不会各自散开。

> 上面命令里的 `--agent`/`--role` 会被安装脚本记住,并在**装完当场注册**(看板立刻出现这张卡且详情有内容)。
> 想再补充"擅长/上手提示",可选地在该 agent 运行环境里加:
```bash
export TF_ABOUT="基于飞书的助手,负责文档撰写与资料调研"
export TF_TIPS="给它目标人群+一个样例,它会贴着语气产出"
```

> 管理员小贴士:把 `key` 填进上面模板,做成一句**现成话术私发**给队友(`key` 别进群公告/公开渠道),
> 他们只改"名字 / agent 名 / 用途"三处即可,最省事。

---

## 二、装不上 / 报错怎么办

- **`command not found: tf-run` 或装完没反应**:新开一个终端(或 `source ~/.zshrc`)再试;
  安装会把 `~/.tranfu` 加进 PATH,需新 shell 生效。
- **`curl: (7) Failed to connect` / 超时**:看板地址连不上——多半是服务端还没部署好或域名没通,找管理员确认 `https://tranfu-agents-app.tranfu.com` 能打开。
- **上报后看板没动静、或返回 401**:`key` 不对。用管理员私发的最新 `key` 重新装一次。
- **公司网络限制**:确保这台机器能访问看板域名;必要时连公司 VPN。

---

## 三、给你的编队加更多 agent

一个调度员通常带好几个 agent。**对每个 agent 各说一句**,讲清「我是谁 + 这个 agent 干啥用」:

- 文案那个:`…我是 bob,用 open claw 做文案。`
- 写代码那个:`…我是 bob,用 codex 写代码。`

看板上 **bob 这个 Pod** 名下就会出现两张编队卡:

```
bob(调度员)
  ├ 文案  [Open Claw]   运行中
  └ 代码  [Codex]       运行中
```
> 你的身份(bob)只说一次就固定;每个 agent 各自登记"用什么、干啥用"。同款工具靠用途区分。

---

## 四、它会自动认出这些(你不用填)

接入后,agent 详情页会自动显示它探测到的:**类型/版本、终端、安装位置、集成的 IM、
连接的 MCP、已装的技能(Skill)**。这些**全自动**,你唯一可选填的是"这个 agent 是干嘛的"——
想填就在它的运行环境里加一行(可选,不填也能用):

```bash
export TF_ROLE="品牌文案执行体"     # 这个 agent 的角色/定位
```

---

## 五、验证接好了没

让 agent 跑个小任务,或直接说「发一条测试到 TRANFU 看板」。打开看板,应能在**你的 Pod**里看到
「**你的名字 · 用途 [agent] 运行中**」。如果这次任务用到了 Skill,稍后也能在 **SKILLS** 页看到
7/30/90 天连续 `Asia/Shanghai` 时间轴、used-only 排行和单 Skill 详情。看不到?超过 3 分钟没动静会判为掉线(空闲),重新跑一下即可。

---

## 六、不同形态的 agent(自动处理,你不用操心)

| 你用的 | 看板能看到 |
|---|---|
| Codex | 实时步骤 + 状态 + 活跃时长(或用 `tf-run` 临时包装) |
| Hermes | 配 shell hooks 后实时步骤 + 状态 + 活跃时长;也可用 `tf-run` 临时包装 |
| 本地命令行(Open Claw / 其它 CLI…) | 开始 / 运行中 / 完成或出错 + 活跃时长 |
| Claude Code | 实时步骤 + 状态 + 活跃时长 |
| Claude 桌面版 / 支持 MCP 的 | 通过内置上报工具,开始/步骤/完成 |
| 云端(Manus / MuleRun / ChatGPT 网页) | 仅「开始 / 结束」,标记为「云端·粗粒度」 |

本地 hook 型 runtime(Claude Code / Codex / Hermes)在 shim 文件替换后下一次 hook 触发即生效;OpenClaw
插件文件可自动下载,但要重启 OpenClaw 才会加载新版 JS。

---

## 七、隐私 / 退出

- 默认只上报:**谁、用途、状态、当前步骤、活跃时长**;**不**上报你的 prompt、代码、输出、记忆。
- SKILLS 统计页默认只统计 skill 名,不记录参数或内容:Claude Code 取自 `Skill` 工具调用,
  Hermes 取自 `skill_view` 工具调用,Codex 取自本机会话文件里的已装 `SKILL.md` 读取信号;
  OpenClaw 取自 prompt 注入块并标为 `equipped` 装备态。总览页只排 `used`,装备态只在单 Skill 详情里展示,不与使用态相加。
  不想参与统计可在本机设置 `export TF_REPORT_SKILLS=0` 后重启对应 agent。
- 想把内容也回传做团队复盘:告诉 agent「打开内容回传」。
  ⚠️ 打开后这些内容会显示给所有有看板权限的人,慎用(看板应放在内网/VPN/SSO 之后)。
- 退出:对 agent 说「关闭 TRANFU 上报」或「卸载 TRANFU//AGENTS」,它会撤掉相关配置;
  或手动删掉 `~/.tranfu` 和 shell 配置里的 `TF_*` 段落。

---

## 八、常见问题

**Q:粘了那句话,agent 说装不上?**
A:见第二节排查。安装走的是看板域名(`…/install.sh`),不依赖代码库是否公开;最常见是没连上看板地址或 key 不对。

**Q:我开了好几个 agent,会乱吗?**
A:不会。都在你这个 Pod 的编队里,各自一张卡,按"用途"区分。

**Q:看板上我的卡片变灰 / 不动了?**
A:超过 3 分钟没收到心跳判为掉线(空闲),运行时长停在最后一次确认心跳;重新跑任务会从恢复时刻开启新计时段。

**Q:活动流为什么不是每隔几秒刷一条?**
A:通常只有 agent **真的换了状态/步骤**才记一条;连续段内没变化的心跳不进活动流(但卡片和活跃时长照常更新)。
同状态/同步骤若断档超过 3 分钟后恢复,服务端会额外保留一条计时边界,避免把离线期间算成运行时长。

**Q:云端网页版 agent(ChatGPT/Manus)能接吗?**
A:能,但只能看到"开始/结束",标记为"云端·粗粒度";要细到步骤,用本地 agent、Claude Code 或 Codex hooks。

---

> 想看更技术化的接入路径(tf-run / Claude Code 或 Codex 钩子 / Hermes shell hooks / MCP reporter)与各自细节,见 `QUICKSTART.md`。
