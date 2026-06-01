# 入职指引(团队成员)

把你的 agent 接入 [TRANFU//AGENTS](https://tranfu.com) 就算完成"入职"——你会成为团队里一个 **Pod 的调度员**,你用的 agent 就是这个 Pod 的 **Agent 编队**。接好后,团队能实时看到:**谁在跑、在哪一步、状态、活跃了多久。**

> **一人一 Pod**:你不用选"加入哪个 Pod"。用你的名字,系统自动把你登记为**你自己这个 Pod 的调度员**,你的 agent 自动进你的编队。

---

## 一句话入职(推荐)

你日常用的 agent(Claude Code / Codex / Open Claw / Hermes …)大多能读取技能库。直接对它说:

> 安装 https://github.com/tranfu-labs/tranfu-agents-app 里的 TRANFU//AGENTS,
> **我是 bob,用 open claw 处理文案内容。**

agent 会自动:
1. 读取该仓库的 `SKILL.md`;
2. 装好上报工具;
3. 把你登记为 **调度员 bob**,并把这个 agent 加入你的**编队**(用 open-claw,用途=文案),开始上报。

---

## 给你的编队加更多 agent

一个调度员通常带好几个 agent。**对每个 agent 各说一句**,讲清「我是谁 + 这个 agent 干啥用」:

- agent ①(文案):
  > …tranfu-agents-app 里的 TRANFU//AGENTS,**我是 bob,用 open claw 处理文案内容。**
- agent ②(写代码):
  > …tranfu-agents-app 里的 TRANFU//AGENTS,**我是 bob,用 codex 写代码。**

看板上 **bob 这个 Pod** 名下会出现两张编队卡:

```
bob(调度员)
  ├ 文案  [Open Claw]   运行中
  └ 代码  [Codex]       运行中
```

> 你的身份(bob = 调度员)只说一次就固定;每个 agent 各自登记「用什么、干啥用」。同款工具也能靠用途(文案 / 代码)区分。

---

## key(接入密钥)怎么输入?——不用敲命令

你**不用记命令、也不用手设环境变量**。key 有两种进入方式,任选其一:

**方式一:agent 问,你粘一次。**
发出入职那句话后,agent 会反问「接入地址」和「接入密钥」,把管理员给的那串粘进对话即可。装好后存进这台机器(`~/.tranfu`),**之后同一台机器不再问**。

**方式二(更省事):管理员把 key 写进话术,你只填身份。**
管理员发一句现成模板,你把空填上整句发给 agent,一次粘贴搞定:

> 安装 https://github.com/tranfu-labs/tranfu-agents-app 里的 TRANFU//AGENTS。
> server=https://agents.tranfu.com  key=tf_xxxxx
> 我是 ___,用 ___ 做 ___。

> 小提醒:key 只是"能往看板写数据"的凭证,影响面很小、可随时轮换。若你用的是**云端 agent(网页版 ChatGPT / Manus 等)**,把它粘进对话等于交给了该厂商,介意的话用本地 agent 或方式一。

---

## 验证

入职后让 agent 跑个小任务,或直接说「发一条测试到 TRANFU 看板」。打开看板,应能在**你的 Pod**里看到「**你的名字 · 用途 [agent] 运行中**」。

---

## 不同形态的 agent(agent 自动处理,你不用操心)

| 你用的 | 看板能看到 |
|---|---|
| 本地命令行(Codex / Open Claw / Hermes…) | 开始 / 运行中 / 完成或出错 + 活跃时长 |
| Claude Code | 实时步骤 + 状态 + 活跃时长 |
| 云端(Manus / MuleRun / ChatGPT 网页) | 仅「开始 / 结束」,标记为「云端·粗粒度」 |

---

## 隐私 / 退出

- 默认只上报:**谁、用途、状态、当前步骤、活跃时长**。
- 想把 **prompt / 代码 / 输出** 也回传做团队复盘:告诉 agent「打开内容回传」。
  ⚠️ 打开后这些内容会显示给所有有看板权限的人,慎用(团队该把看板放在内网/VPN 后)。
- 想退出:对 agent 说「关闭 TRANFU 上报」或「卸载 TRANFU//AGENTS」,它会撤掉相关配置。

---

## 常见问题

**Q:看板上我的卡片变灰 / 不动了?**
A:超过 3 分钟没收到心跳会判为掉线(空闲)。重新跑任务即可恢复。

**Q:我开了 3 个 agent,会乱吗?**
A:不会。它们都在你这个 Pod 的编队里,各自一张卡,按「用途」区分。

**Q:活动流为什么不是每隔几秒刷一条?**
A:只有 agent **真的换了状态/步骤**才记一条。没变化的心跳不进活动流(但卡片和活跃时长照常更新)。

**Q:agent 说它读不到技能库 / 装不上?**
A:确认它能访问看板域名;或把 `https://你的看板地址/install.sh` 发给它,让它按里面的步骤装。
