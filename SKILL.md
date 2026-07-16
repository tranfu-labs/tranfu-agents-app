---
name: tranfu-agents-app
description: Install and connect this agent to the team's TRANFU//AGENTS live dashboard, so the team can see what everyone's agents are doing (who, which agent, current step, status, active time). Trigger when the user says things like "安装 TRANFU//AGENTS", "install tranfu telemetry", "接入团队 agent 看板", "我是 bob,这个用来写代码"/"我是 bob,用 open claw 处理文案" (a who/what self-introduction aimed at joining the board — the user need NOT mention which runtime), or links to github.com/tranfu-labs/tranfu-agents-app asking to install this. Works for Claude Code, Codex, Open Claw, Hermes, and any CLI agent; cloud agents (Manus, MuleRun) are supported at start/end granularity.
---

# TRANFU//AGENTS — 入职(给 agent 读)

把用户接入团队看板 = 给他**办入职**:他成为一个 **Pod 的调度员**(一人一 Pod),
他用的每个 agent 是这个 Pod 的**编队**。用户用**自然语言**说明身份与用途,例如:

> 「帮我接入 TRANFU//AGENTS,我是 bob,这个用来写代码。」

**完整、权威的安装步骤在 [INSTALL.md](INSTALL.md) —— 打开它,从上到下一次执行完,不要让用户粘命令。**

要点(细节全在 INSTALL.md):

- **解析三件事**:`operator`(用户说「我是 X」)、`agent`(用途短标签,如 code/copy/research)、`runtime`。
  **runtime 不用问用户——你就是当前 runtime**(Claude Code→`claude-code`、Codex→`codex`、OpenClaw→`openclaw`、Hermes→`hermes`);拿不准就**不传** `--runtime`,安装器会用进程内信号兜底。
- **(重)装前先读本机已有身份**:`python3 ~/.tranfu/tf-doctor --identity --json`(无网络);装过就把已登记的调度员/编队列给用户确认**沿用/改/新增**,而不是从头再问。用户只说「装一下」时,主动引导补全缺的字段。
- **server / key**:先从用户消息取 → 再看本机已有(`has_key:true` 即免问,不传 `--key` 安装器也会保留)→ 都没有才**只问一次**。
- **执行**:跑 INSTALL.md 第 1 步的 `curl … | install.sh …`(你自己拼好,用户看不到 flag)→ 安装器预检+全量装 shim+接 hooks(Codex/macOS 同步装纯换序信任守护)+当场注册 → 跑 `python3 ~/.tranfu/tf-doctor --runtime <你> --json` 自检 → 把结果回话确认。
- **护栏**:一次跑完、不拆成手敲命令、不问 runtime、env 只写 `~/.tranfu`、key 不进 hooks/Hermes config、**绝不 sudo**、不动用户已有 hooks/skills。

隐私:默认只上报 谁/用途/状态/步骤/活跃时长 + 可安全识别的 Skill 名(不含参数/内容);
用户要回传 prompt/代码/输出设 `TF_CAPTURE_CONTENT=1`(开启后看板可见者皆可见)。
