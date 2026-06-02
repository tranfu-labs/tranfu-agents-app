#!/usr/bin/env python3
"""TRANFU//AGENTS — MCP reporter server.

让任何支持 MCP 的 agent(Claude 桌面版、Claude Code、其它 MCP 客户端)把实时状态
自动上报到团队看板。对外暴露一个工具:tranfu_report。

环境变量:
  TF_SERVER    https://你的看板            (必填)
  TF_KEY       团队写入密钥                (服务端开启校验时必填)
  TF_TOKEN     per-operator 令牌           (服务端开启 TF_REQUIRE_TOKEN 时必填,见 §4)
  TF_OPERATOR  你的名字(调度员)            (默认 $USER)
  TF_RUNTIME   运行时标签                  (默认 claude-desktop)
  TF_AGENT     默认用途标签                (可选,如 code / research)
  TF_PARENT_SESSION 父 run 的 session_id   (可选,子 agent 挂到父 run 下)

启动(stdio):  python3 server.py
"""
import os, sys, json, time, random, asyncio, urllib.request, importlib.util
from mcp.server.fastmcp import FastMCP

PROTOCOL_VERSION = "0.1"


def _load_tf_profile():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tf_profile.py")
        spec = importlib.util.spec_from_file_location("tf_profile", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


tf_profile = _load_tf_profile()

TF_SERVER = os.environ.get("TF_SERVER", "").rstrip("/")
TF_KEY = os.environ.get("TF_KEY", "")
TF_TOKEN = os.environ.get("TF_TOKEN", "")
TF_OPERATOR = os.environ.get("TF_OPERATOR") or os.environ.get("USER") or "unknown"
TF_RUNTIME = os.environ.get("TF_RUNTIME", "claude-desktop")
TF_AGENT = os.environ.get("TF_AGENT")
TF_PARENT_SESSION = os.environ.get("TF_PARENT_SESSION")
SESSION = f"mcp-{int(time.time())}-{random.randint(1000, 9999)}"
_profiled = False  # attach auto-detected profile once per process

mcp = FastMCP("tranfu-reporter")


def _post(payload):
    data = json.dumps(payload).encode()
    headers = {"content-type": "application/json", "X-TF-Key": TF_KEY}
    if TF_TOKEN:                              # per-operator attribution (§4)
        headers["X-TF-Token"] = TF_TOKEN
    req = urllib.request.Request(f"{TF_SERVER}/v1/events", data=data,
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:   # §3 short timeout
        return r.read()


@mcp.tool()
async def tranfu_report(status: str, task: str = "", step: str = "", agent: str = "") -> str:
    """Report this agent's live status to the team TRANFU//AGENTS board.

    Call this tool:
      - at the START of a task             -> status="running", task="<short title>"
      - on each MAJOR step                 -> status="running", step="<what you're doing>"
      - when you finish                    -> status="done"
      - if you pause for the user          -> status="waiting", step="<why>"
      - on failure                         -> status="error", step="<error>"

    Args:
      status: one of running | waiting | done | error
      task:   short human task title (keep it stable across the task)
      step:   what is happening right now
      agent:  optional purpose label (e.g. "code", "research"); defaults to TF_AGENT
    """
    if not TF_SERVER:
        return "TRANFU not configured: set TF_SERVER in this server's env."
    payload = {
        "v": PROTOCOL_VERSION,
        "operator": TF_OPERATOR, "runtime": TF_RUNTIME, "agent": agent or TF_AGENT,
        "session_id": SESSION, "parent_session_id": TF_PARENT_SESSION, "status": status,
        "task": task or None, "current_step": step or None,
    }
    payload = {k: v for k, v in payload.items() if v}
    global _profiled
    if tf_profile and not _profiled:
        try:
            payload.update(tf_profile.collect(runtime=TF_RUNTIME)); _profiled = True
        except Exception:
            pass
    try:
        await asyncio.to_thread(_post, payload)
        return f"reported to TRANFU: {status}" + (f" — {step}" if step else "")
    except Exception as e:
        return f"TRANFU report failed: {e}"


if __name__ == "__main__":
    mcp.run()
