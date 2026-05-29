# 使用指引(团队成员)

把你的 agent 接到 [TRANFU//AGENTS](https://tranfu.com) 看板。接好后,团队能实时看到:
**谁在跑、在哪一步、状态、活跃了多久。**

---

## 一句话安装(推荐)

你日常用的 agent(Claude Code / Codex / Open Claw / Hermes …)大多能读取技能库。
直接对它说,让它从技能仓库装好并完成接入:

> 安装 https://github.com/tranfu-labs/tranfu-skills 里的 TRANFU//AGENTS,
> **我是 bob,用 open claw 处理文案内容。**

agent 会自动:
1. 读取该仓库的 `tranfu-agent-telemetry/SKILL.md`;
2. 装好上报工具;
3. 把这个 agent 登记为 **operator=bob、用 open-claw、用途=文案**,开始上报。

---

## 有好几个 agent?分别说一句就行

一个人开多个 agent 很常见。**对每个 agent 各说一句**,讲清「我是谁 + 这个 agent 干啥用」:

- agent ①(文案):
  > 安装 https://github.com/tranfu-labs/tranfu-skills 里的 TRANFU//AGENTS,**我是 bob,用 open claw 处理文案内容。**
- agent ②(写代码):
  > 安装 https://github.com/tranfu-labs/tranfu-skills 里的 TRANFU//AGENTS,**我是 bob,用 codex 写代码。**

看板上会显示成两张卡,都挂在 **bob** 名下:

```
bob · 文案   [Open Claw]   运行中
bob · 代码   [Codex]       运行中
```

> 规则:**你是谁(bob)只说一次身份就固定**;每个 agent 的「用什么、干啥用」各自登记。
> 就算两个都是 codex,也能靠用途(文案 / 代码)区分开。

---

## 首次需要的两样东西

管理员会给你(一次性):**接入地址** 和 **接入密钥**。
一句话安装时 agent 会问你,贴进去即可;同一台机器之后不用再填。

---

## 验证

装完让 agent 跑个小任务,或直接说「发一条测试到 TRANFU 看板」。
打开看板应能看到「**你的名字 · 用途 [agent] 运行中**」。

---

## 不同形态的 agent(agent 自动处理,你不用操心)

| 你用的 | 看板能看到 |
|---|---|
| 本地命令行(Codex / Open Claw / Hermes…) | 开始 / 运行中 / 完成或出错 + 活跃时长 |
| Claude Code | 实时步骤 + 状态 + 活跃时长 |
| 云端(Manus / MuleRun / ChatGPT 网页) | 仅「开始 / 结束」,标记为「云端·粗粒度」 |

---

## 隐私 / 停用

- 默认只上报:**谁、用途、状态、当前步骤、活跃时长**。
- 想把 **prompt / 代码 / 输出** 也回传做团队复盘:告诉 agent「打开内容回传」。
  ⚠️ 打开后这些内容会显示给所有有看板权限的人,慎用(团队该把看板放在内网/VPN 后)。
- 想停:对 agent 说「关闭 TRANFU 上报」或「卸载 TRANFU//AGENTS」,它会撤掉相关配置。

---

## 常见问题

**Q:看板上我的卡片变灰 / 不动了?**
A:超过 3 分钟没收到心跳会判为掉线(空闲)。重新跑任务即可恢复。

**Q:我开了 3 个 agent,会乱吗?**
A:不会。它们都挂在你名下,各自一张卡,按「用途」区分。

**Q:agent 说它读不到技能库 / 装不上?**
A:确认它能访问 GitHub;或把仓库 `tranfu-agent-telemetry/install.sh` 的链接发给它,让它按里面的步骤装。
