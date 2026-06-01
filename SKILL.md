---
name: tranfu-agents-app
description: Install and connect this agent to the team's TRANFU//AGENTS live dashboard, so the team can see what everyone's agents are doing (who, which agent, current step, status, active time). Trigger when the user says things like "安装 TRANFU//AGENTS", "install tranfu telemetry", "接入团队 agent 看板", "我是 bob,用 open claw 处理文案" (a who/what self-introduction aimed at joining the board), or links to github.com/tranfu-labs/tranfu-agents-app asking to install this. Works for Claude Code, Codex, Open Claw, Hermes, and any CLI agent; cloud agents (Manus, MuleRun) are supported at start/end granularity.
---

# TRANFU//AGENTS — 入职(给 agent 读)

把用户接入团队看板 = 给他**办入职**:在 TRANFU//AGENTS 里,他将成为一个 **Pod 的调度员**(一人一 Pod),他用的 agent 就是这个 Pod 的**编队**。用户通常用**自然语言**说明身份与用途,例如:

> 「安装 TRANFU//AGENTS,我是 bob,用 open claw 处理文案内容。」

## 第 1 步:从这句话里解析三件事

| 解析项 | 来源 | 例子 |
|---|---|---|
| `operator`(人 = 该 Pod 的调度员) | "我是 X" | bob |
| `runtime`(用的工具) | "用 Y" → 归一化 | open claw→`open-claw`、codex→`codex`、claude code→`claude-code`、hermes→`hermes`、manus→`manus`、mulerun→`mulerun` |
| `agent`(用途标签) | "处理 Z / 用来做 Z" → 取一个短标签 | 文案→`copy`、写代码→`code`、研究→`research` |

**一人一 Pod**:`operator` 就是这个 Pod 的调度员,**不需要问"加入哪个 Pod"**——同名即同一个 Pod,自动归并。
**一个调度员多个 agent**:用户会对**每个 agent 各说一句**。每次只登记**当前这个** agent 进他的编队;
`operator` 相同、`runtime`+`agent` 各不相同即可(例:bob/`copy`/open-claw 与 bob/`code`/codex)。

## 第 2 步:拿到接入地址 + 接入密钥

需要两样:**接入地址**(server)和**接入密钥**(key)。来源优先级:
1. **先从用户这条消息里解析**——若出现 `server=...` / `key=...`(或"地址 …""密钥 …"),直接取用,不要再问。
2. 若消息里没有,**只问这一次**;装好后会写入本机配置 `~/.tranfu`,以后同一台机器不再问。

(注:key 是防止他人乱塞数据的写入凭证,不是任何 LLM 用量。它只能往看板写遥测,泄露的影响面很小、可随时由管理员轮换。)

## 第 3 步:安装上报工具(办入职)

```bash
curl -fsSL <接入地址>/install.sh \
  | bash -s -- --server <接入地址> --key <接入密钥> --operator <operator>
```
装完会把工具放到 `~/.tranfu` 并写入 `TF_SERVER / TF_KEY / TF_OPERATOR`——该调度员的 Pod 即建立。

## 第 4 步:按本 agent 的形态接好上报

- **本地命令行**(codex / open-claw / hermes / 任意 CLI):用包装器运行,带上 `--agent`(用途):
  ```bash
  tf-run --runtime <runtime> --agent <用途> --task "<在做什么>" -- <原本的启动命令>
  ```
- **Claude Code**:把 `shims/claude-code/hooks.settings.json` 合并进 `~/.claude/settings.json`
  (填入 server/密钥/operator/agent),或直接用上面的 `tf-run` 包装。
- **云端**(manus / mulerun / chatgpt):只能粗粒度,包住派发那一步:
  ```bash
  tf-run --runtime <runtime> --agent <用途> --task "<任务>" --coarse -- <派发脚本>
  ```

## 第 5 步:确认

```bash
source ~/.tranfu/tf_client.sh
TF_RUNTIME=<runtime> TF_AGENT=<用途> tf_emit running --task "测试" --step "hello"
```
告诉用户去看板,在**他的 Pod**里应能看到「用途 [runtime] 运行中」。

## 隐私
默认只上报 谁/用途/状态/步骤/活跃时长。若用户要回传 prompt/代码/输出,设 `TF_CAPTURE_CONTENT=1`,
并提醒:开启后内容对所有有看板权限的人可见。
