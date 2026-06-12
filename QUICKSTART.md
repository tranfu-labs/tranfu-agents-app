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

# Codex 用户把 runtime 换成 codex:
curl -fsSL https://你的看板地址/install.sh | bash -s -- \
  --server https://你的看板地址 --key 接入密钥 --operator 你的名字 --runtime codex --agent code
```

`--server` / `--key` 找管理员要。装好后会写进 `~/.tranfu` 和你的 shell 配置,**新开一个终端**生效
(或 `source ~/.zshrc`)。

---

## 2. 选你的接入方式(按你用的 agent 选择)

### A) 任意命令行 agent —— 用 `tf-run` 包一下(最通用)
Open Claw / 自写脚本都行;Hermes 也可以这样临时包装,但要实时工具步骤与 Skill 统计请看 C。OpenClaw 的
equipped Skill 统计由 `install.sh` 安装的原生插件负责,wrapper 仍负责状态/活跃时长。Codex 也可以这样做一次性包装。`started` 时**自动探测并上报 profile**,
中途心跳,结束报完成/失败:

```bash
tf-run --runtime codex     --agent code --task "重构支付" -- codex exec "重构支付模块"
tf-run --runtime open-claw --agent copy --task "改写落地页" -- claw run ./task.md
# 云端黑盒(只看起止)加 --coarse:
tf-run --runtime manus --agent research --task "市场报告" --coarse -- ./dispatch_manus.sh
```

### B) Claude Code / Codex —— 装钩子(自动上报实时步骤,推荐)
第 1 步如果传了 `--runtime claude-code`,安装脚本会自动把 TRANFU hooks 幂等合并进
`~/.claude/settings.json`;如果传了 `--runtime codex`,会幂等合并进 `~/.codex/hooks.json`。
这两个都是用户级配置,对所有项目生效。会话开始 / 提交提示 / 每次工具调用 / 结束会自动上报,
不用人工发事件。已有 TRANFU hooks 时不会重复添加;已有其它 hooks 会保留。

```bash
# Claude Code:查看 / 修复 / 卸载 / 恢复
python3 ~/.tranfu/tf_hooks.py --target claude status
python3 ~/.tranfu/tf_hooks.py --target claude install
python3 ~/.tranfu/tf_hooks.py --target claude uninstall
python3 ~/.tranfu/tf_hooks.py --target claude restore

# Codex:查看 / 修复 / 卸载 / 恢复
python3 ~/.tranfu/tf_hooks.py --target codex status
python3 ~/.tranfu/tf_hooks.py --target codex install
python3 ~/.tranfu/tf_hooks.py --target codex uninstall
python3 ~/.tranfu/tf_hooks.py --target codex restore
```

每次写入前都会生成 `*.tranfu.bak.*` 备份。安装或修复后需要重启 Claude Code / Codex
(钩子在会话开始时快照,必须重启生效)。Codex 首次运行新增 hook 时可能会要求信任,确认一次即可。

事件 → 状态:`SessionStart`→started(+profile 注册)、`UserPromptSubmit`→running、
`PreToolUse`→running(step=tool: 工具名)、`Stop`/`SessionEnd`→done。
Claude Code 的 `Skill` 工具调用、Codex 轮末本地 transcript 扫描都会默认附带 skill 名用于团队排行统计;
只记录名称,不记录参数或内容。如需关闭,在本机环境里设置 `export TF_REPORT_SKILLS=0` 后重启 Claude Code / Codex。
如果 hooks 没继承 shell 环境,把这行加到 `~/.tranfu/tf_env.claude-code.sh` 或
`~/.tranfu/tf_env.codex.sh`。
身份与密钥从你 shell rc 里的 `TF_*` 继承(终端启动 `claude` 即可,密钥不必写进 settings.json)。
需要跳过自动安装时,安装命令加 `--no-claude-hooks` 或 `--no-codex-hooks`。

### C) Hermes —— 配 shell hooks(实时步骤 + skill_view 统计)
第 1 步如果传了 `--runtime hermes`,安装脚本会安装 `tf-hermes-hook.sh` 并打印下面这段配置。
把它合并进 `~/.hermes/config.yaml`,然后重启 Hermes gateway:

```yaml
hooks:
  on_session_start:
    - command: "~/.tranfu/tf-hermes-hook.sh"
  pre_llm_call:
    - command: "~/.tranfu/tf-hermes-hook.sh"
  pre_tool_call:
    - command: "~/.tranfu/tf-hermes-hook.sh"
  post_llm_call:
    - command: "~/.tranfu/tf-hermes-hook.sh"
  on_session_end:
    - command: "~/.tranfu/tf-hermes-hook.sh"
hooks_auto_accept: true
```

事件 → 状态:`on_session_start`→started(+profile 注册)、`pre_llm_call`→running(prompt)、
`pre_tool_call`→running(step=tool: 工具名)、`post_llm_call`/`on_session_end`→done。
Hermes 的 `skill_view(name)` 工具调用会默认附带 skill 名用于团队排行统计;只记录名称,
不记录参数或内容。如需关闭,把 `export TF_REPORT_SKILLS=0` 加到 `~/.tranfu/tf_env.hermes.sh`,
然后重启 Hermes gateway。

### D) Claude 桌面版 / 其它支持 MCP 的 agent —— 用 MCP reporter
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

> Skill 使用排行默认只统计 skill 名:Claude Code 取自 `Skill`,Hermes 取自 `skill_view`,
> Codex 取自本机会话文件里的已装 `SKILL.md` 读取信号;OpenClaw 取自 prompt 注入块并标为
> `equipped` 装备态,不与使用态相加。如不希望参与统计,设置 `export TF_REPORT_SKILLS=0`。
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

对 agent 说「关闭 TRANFU 上报」。Claude Code / Codex 先运行:

```bash
python3 ~/.tranfu/tf_hooks.py --target claude uninstall
python3 ~/.tranfu/tf_hooks.py --target codex uninstall
```

Hermes 需要从 `~/.hermes/config.yaml` 删除指向 `~/.tranfu/tf-hermes-hook.sh` 的 hooks 条目。
然后删掉 `~/.tranfu` 与 shell 配置里的 TF_* 段落即可。
