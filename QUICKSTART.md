# QUICKSTART — 队友 5 分钟接入

把你的 AI agent 接到团队的 **TRANFU//AGENTS** 看板。装一次,之后每次跑 agent 自动上报:
**谁在跑、用哪个 agent、当前步骤、状态、活跃时长**,详情页还会显示这个 agent 的
**类型/版本、终端、安装位置、集成的 IM、MCP、已装技能**——这些**全部自动探测**,你基本不用填。

> 一人一 Pod:用你的名字,你就是自己这个 Pod 的「调度员」,你的每个 agent 是它的「编队」。

---

## 1. 一键安装(每台机器一次)

```bash
curl -fsSL https://你的看板地址/install.sh | bash -s -- \
  --server https://你的看板地址 --key 接入密钥 --operator 你的名字 --runtime claude-code
```

`--server` / `--key` 找管理员要。装好后会写进 `~/.tranfu` 和你的 shell 配置,**新开一个终端**生效
(或 `source ~/.zshrc`)。

---

## 2. 选你的接入方式(按你用的 agent 三选一)

### A) 任意命令行 agent —— 用 `tf-run` 包一下(最通用)
Codex / Open Claw / Hermes / 自写脚本都行。`started` 时**自动探测并上报 profile**,中途心跳,结束报完成/失败:

```bash
tf-run --runtime codex     --agent code --task "重构支付" -- codex exec "重构支付模块"
tf-run --runtime open-claw --agent copy --task "改写落地页" -- claw run ./task.md
# 云端黑盒(只看起止)加 --coarse:
tf-run --runtime manus --agent research --task "市场报告" --coarse -- ./dispatch_manus.sh
```

### B) Claude Code —— 用钩子(能看到实时步骤)
把 `shims/claude-code/hooks.settings.json` 的内容合并进 `~/.claude/settings.json`
(填好里面的 `TF_SERVER/TF_KEY/TF_OPERATOR/TF_AGENT`)。之后照常 `claude` 即可:
会话开始上报 `started` + profile,每步上报 `running`,结束上报 `done`。

### C) Claude 桌面版 / 其它支持 MCP 的 agent —— 用 MCP reporter
桌面版没有命令行,用 MCP 自动上报。把下面合并进
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tranfu-reporter": {
      "command": "python3",
      "args": ["~/.tranfu/mcp/server.py"],
      "env": { "TF_SERVER": "https://你的看板", "TF_KEY": "密钥",
               "TF_OPERATOR": "你的名字", "TF_RUNTIME": "claude-desktop", "TF_AGENT": "code" }
    }
  }
}
```
再把这段加进它的**项目说明 / 自定义指令**,让它自觉上报:
> 每开始一个任务先调用 tranfu_report(status="running", task=标题);每进入主要步骤调用
> tranfu_report(status="running", step=当前在做什么);完成时 status="done";出错时 status="error"。

(细节见 `shims/mcp/README.md`。)

---

## 3. 唯一需要手填的一项:`role`

机器能自动探测**版本、终端、位置、IM、MCP、技能**,但推不出这个 agent「**是干嘛的**」。
用一行环境变量补上(可选,但建议填,详情页更有用):

```bash
export TF_ROLE="品牌文案执行体"      # 这个 agent 的角色/定位
export TF_ABOUT="吃品牌语气库,产出多版标题与正文"   # 可选:它擅长什么
export TF_TIPS="先喂目标人群和一个样例,它会贴着语气走"  # 可选:别人怎么用好它
```
放进 `~/.zshrc`(或写在该 agent 的运行环境里)即可。其余字段无需填。

> 敏感内容(完整系统指令、记忆文件)**默认不上报**;确有团队复盘需要再开
> `export TF_REPORT_MEMORY=1`,并确保看板在内网/VPN 后。

---

## 4. 验证

跑一个小任务,然后打开看板:
- **Pods 看板**:你的 Pod 下出现一张卡「你的名字 · 用途 [agent] 运行中」。
- **Agents 列表 → 点进详情**:能看到自动探测出的 类型/版本、终端、位置、IM、MCP、已装技能、近 90 天活跃。

没出现?看板超过 3 分钟没收到心跳会判为掉线(空闲),重新跑任务即可。

---

## 5. 退出

对 agent 说「关闭 TRANFU 上报」,或删掉 `~/.tranfu` 与 shell 配置里的 TF_* 段落即可。
