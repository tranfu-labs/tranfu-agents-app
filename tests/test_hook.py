"""tf_hook.resolve 契约测试：Claude/Codex 与 Hermes 事件都映射到正确的上报参数。"""
import io
import json
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
    assert "--skill" not in a


def test_claude_skill_tool_adds_skill_arg():
    # Expected Claude Code PreToolUse payload shape for Skill tool calls:
    # tool_name is "Skill" and the selected skill name is inside tool_input.
    a = _args({"hook_event_name": "PreToolUse", "tool_name": "Skill",
               "tool_input": {"skill_name": "openai-docs"}, "session_id": "s1"})
    assert a[a.index("--step") + 1] == "tool: Skill"
    assert a[a.index("--skill") + 1] == "openai-docs"


def test_skill_tool_missing_name_is_ignored():
    a = _args({"hook_event_name": "PreToolUse", "tool_name": "Skill",
               "tool_input": {"prompt": "use a skill"}, "session_id": "s1"})
    assert "--skill" not in a


def test_skill_reporting_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    a = _args({"hook_event_name": "PreToolUse", "tool_name": "Skill",
               "tool_input": {"name": "openai-docs"}, "session_id": "s1"})
    assert "--skill" not in a


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


def test_hermes_skill_view_adds_skill_arg():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "skill_view",
               "tool_input": {"name": "lark-base"}, "session_id": "s1"})
    assert a[a.index("--step") + 1] == "tool: skill_view"
    assert a[a.index("--skill") + 1] == "lark-base"


def test_hermes_skill_view_reference_read_keeps_skill_arg():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "skill_view",
               "tool_input": {"name": "lark-base", "path": "refs/card.md"},
               "session_id": "s1"})
    assert a[a.index("--skill") + 1] == "lark-base"


def test_hermes_skills_list_is_not_counted():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "skills_list",
               "tool_input": {}, "session_id": "s1"})
    assert a[a.index("--step") + 1] == "tool: skills_list"
    assert "--skill" not in a


def test_hermes_skill_manage_is_not_counted():
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "skill_manage",
               "tool_input": {"action": "create", "name": "new-skill"},
               "session_id": "s1"})
    assert "--skill" not in a


def test_hermes_post_tool_skill_view_is_not_counted():
    a = _args({"hook_event_name": "post_tool_call", "tool_name": "skill_view",
               "tool_input": {"name": "lark-base"}, "session_id": "s1"})
    assert a[a.index("--step") + 1] == "tool done: skill_view"
    assert "--skill" not in a


def test_hermes_skill_reporting_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    a = _args({"hook_event_name": "pre_tool_call", "tool_name": "skill_view",
               "tool_input": {"name": "lark-base"}, "session_id": "s1"})
    assert "--skill" not in a


def test_main_reports_hermes_skill_view_argv(monkeypatch):
    reported = []
    payload = {"hook_event_name": "pre_tool_call", "tool_name": "skill_view",
               "tool_input": {"name": "lark-base"}, "session_id": "s1"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    tf_hook.main()

    assert reported
    assert reported[0][reported[0].index("--skill") + 1] == "lark-base"
