"""tf_hook.resolve 契约测试：Claude/Codex 与 Hermes 事件都映射到正确的上报参数。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_hook


def _args(d):
    return tf_hook.resolve(d)


def test_unknown_event_ignored():
    assert tf_hook.resolve({"hook_event_name": "Nope"}) is None
    assert tf_hook.resolve({}) is None


def test_claude_pretooluse_tool_name():
    a = _args({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s1"})
    assert "--status" in a and a[a.index("--status") + 1] == "running"
    assert a[a.index("--step") + 1] == "tool: Bash"
    assert a[a.index("--session") + 1] == "s1"


def test_claude_sessionstart_has_profile():
    a = _args({"hook_event_name": "SessionStart", "session_id": "s1"})
    assert "--profile" in a and a[a.index("--status") + 1] == "started"


def test_hermes_pre_tool_call():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "terminal",
               "session_id": "sess_abc", "cwd": "/x"})
    assert a[a.index("--status") + 1] == "running"
    assert a[a.index("--step") + 1] == "tool: terminal"
    assert a[a.index("--session") + 1] == "sess_abc"


def test_hermes_session_lifecycle():
    start = _args({"hook_event_name": "on_session_start", "session_id": "s"})
    end = _args({"hook_event_name": "on_session_end", "session_id": "s"})
    prompt = _args({"hook_event_name": "pre_llm_call", "session_id": "s"})
    assert "--profile" in start and start[start.index("--status") + 1] == "started"
    assert end[end.index("--status") + 1] == "done" and end[end.index("--step") + 1] == "session end"
    assert prompt[prompt.index("--step") + 1] == "prompt"


def test_hermes_subagent_parent_from_extra():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "x",
               "session_id": "child", "extra": {"parent_session_id": "root"}})
    assert a[a.index("--parent") + 1] == "root"
