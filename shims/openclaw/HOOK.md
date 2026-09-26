---
name: tranfu-telemetry
description: "Report OpenClaw session activity to the TRANFU//AGENTS board (TATP v0.1)"
metadata:
  { "openclaw": { "emoji": "📡",
    "events": ["command:new", "message:received", "message:sent", "command:stop", "gateway:shutdown"],
    "requires": { "env": ["TF_SERVER"] } } }
---

# TRANFU telemetry hook (OpenClaw)

把 OpenClaw 的会话活动上报到团队看板。OpenClaw 没有 Claude Code 那种工具级钩子,
所以这里用**命令 / 消息 / 网关**级事件,映射到 TATP 的 status:

| OpenClaw 事件      | TATP status | 说明 |
|--------------------|-------------|------|
| `command:new`      | `started`   | 新会话开始 |
| `message:received` | `running`   | 收到消息(保持存活) |
| `message:sent`     | `running`   | 发出回复(仍在会话中,非终态) |
| `command:stop`     | `done`      | 用户 /stop |
| `gateway:shutdown` | `done`      | 网关关闭 |

保真度介于 Tier A 与 B 之间:有会话开始、每条消息往返、停止;**拿不到工具级步骤**
(OpenClaw 不暴露该粒度事件)。会话超过 180s 无消息会在看板显示为 idle —— 这是正确的
(会话确实空闲了);OpenClaw 无定时钩子,不做额外心跳。

## 安装
```bash
# 1) 装到用户级 hooks 目录(跨 workspace)
mkdir -p ~/.openclaw/hooks/tranfu-telemetry
cp HOOK.md handler.ts ~/.openclaw/hooks/tranfu-telemetry/

# 2) 确保 OpenClaw Gateway 进程能读到这些环境变量(上报凭证与身份):
#    TF_SERVER(必填)、TF_KEY、TF_TOKEN(开强制归因时)、TF_OPERATOR、TF_AGENT
#    在启动 gateway 的 shell / 服务单元里 export。

# 3) 启用
openclaw hooks enable tranfu-telemetry
openclaw hooks check
```

session_id 用 OpenClaw 的 `event.sessionKey`,因此一个会话的多条事件天然共用一张看板卡片。
