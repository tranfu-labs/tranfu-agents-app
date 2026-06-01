# TRANFU reporter — MCP server

让**支持 MCP 的 agent**(尤其是 **Claude 桌面版**,以及任何 MCP 客户端)把实时状态
**自动上报**到团队看板。适合那些没有命令行、无法用 `tf-run` 包装的"黑盒"。

## 原理
MCP server 给 agent 提供一个工具 `tranfu_report`。配上一小段指令后,agent 会在
**开始 / 换步骤 / 完成 / 出错**时自己调用它,工具把事件转发到 `POST /v1/events`。
对 Claude 桌面版来说,这就是它能"自动上报"的唯一干净方式(它没有命令行钩子)。

## 安装
```bash
pip install -r requirements.txt        # 装 mcp
```

## 接入 Claude 桌面版
把下面合并进 Claude 桌面版的 `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tranfu-reporter": {
      "command": "python3",
      "args": ["/绝对路径/tranfu-agents-app/shims/mcp/server.py"],
      "env": {
        "TF_SERVER": "https://你的看板",
        "TF_KEY": "接入密钥",
        "TF_OPERATOR": "nezha",
        "TF_RUNTIME": "claude-desktop",
        "TF_AGENT": "build"
      }
    }
  }
}
```
重启 Claude 桌面版,工具栏里出现 `tranfu-reporter` 即接好。

## 让它"自动"上报(关键一步)
把这段加进你的**项目说明 / 自定义指令**,agent 就会自觉调用:

> 每开始一个任务,先调用 tranfu_report(status="running", task=任务标题)。
> 每进入一个主要步骤,调用 tranfu_report(status="running", step=当前在做什么)。
> 暂停等我时 status="waiting";完成时 status="done";出错时 status="error" 并带上 step。

## 其它 MCP 客户端
同理:把本 server 加进该客户端的 MCP 配置即可,字段含义一致。
