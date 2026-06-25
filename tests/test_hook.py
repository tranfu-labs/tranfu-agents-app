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


def test_userpromptsubmit_does_not_try_to_extract_skill():
    # Claude Desktop 在 hook 调完之后才把 /<skill> 展开成 <command-name>...,
    # hook stdin 上的 prompt 是裸文本无 markup。所以 UserPromptSubmit 这条路径
    # 不再尝试解析 skill —— 走 Stop/SessionEnd 扫 transcript 那条 (scan_claude_skills)。
    a = _args({"hook_event_name": "UserPromptSubmit",
               "prompt": "/openspec-driven-development  测试一下", "session_id": "s1"})
    assert "--skill" not in a
    assert a[a.index("--step") + 1] == "prompt"


def test_pretooluse_skill_tool_path_does_not_regress():
    # 既有 PreToolUse+Skill 工具路径必须照旧工作 —— 模型 invoke skill 走这条,实时上报。
    a = _args({"hook_event_name": "PreToolUse", "tool_name": "Skill",
               "tool_input": {"skill": "openspec-driven-development"},
               "session_id": "s1"})
    assert a[a.index("--step") + 1] == "tool: Skill"
    assert a[a.index("--skill") + 1] == "openspec-driven-development"


def test_claude_sessionstart_has_profile():
    a = _args({"hook_event_name": "SessionStart", "session_id": "s1"})
    assert "--profile" in a and a[a.index("--status") + 1] == "started"


def test_sessionstart_spawns_selfupdate(monkeypatch):
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        class Proc:
            pass
        return Proc()

    monkeypatch.setattr(tf_hook.subprocess, "Popen", fake_popen)
    tf_hook._spawn_selfupdate({"hook_event_name": "SessionStart", "session_id": "s1"})

    assert calls
    assert calls[0][0][-1].endswith("tf_selfupdate.py")
    assert calls[0][1]["env"]["TF_SESSION"] == "s1"
    assert calls[0][1]["start_new_session"] is True


def test_selfupdate_not_spawned_when_disabled(monkeypatch):
    monkeypatch.setenv("TF_AUTO_UPDATE", "0")
    monkeypatch.setattr(tf_hook.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no spawn")))
    tf_hook._spawn_selfupdate({"hook_event_name": "SessionStart", "session_id": "s1"})


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


# ---------- scan_claude_skills (Claude Code 斜杠 skill 从 transcript jsonl 兜底) ----------

def _write_transcript(tmp_path, lines):
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _make_payload(transcript, event="Stop", sid="s-claude-1"):
    return {"hook_event_name": event, "session_id": sid,
            "transcript_path": transcript}


def test_scan_claude_skills_hit_single(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        '{"role":"user","content":"<command-message>openspec-driven-development</command-message>\\n'
        '<command-name>/openspec-driven-development</command-name>\\n<command-args>x</command-args>"}',
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    assert len(reported) == 1
    argv = reported[0]
    assert argv[argv.index("--skill") + 1] == "openspec-driven-development"
    assert argv[argv.index("--status") + 1] == "done"
    assert argv[argv.index("--step") + 1] == "skill: openspec-driven-development"
    assert argv[argv.index("--session") + 1] == "s-claude-1"


def test_scan_claude_skills_multi_skills_deduped(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        '{"x":"<command-name>/openspec-driven-development</command-name>"}',
        '{"x":"<command-name>/openspec-driven-development</command-name>"}',  # 重复同 skill
        '{"x":"<command-name>verify</command-name>"}',  # 无前导 / 也算
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = {argv[argv.index("--skill") + 1] for argv in reported}
    assert names == {"openspec-driven-development", "verify"}
    assert len(reported) == 2  # 同 skill 在同次扫描里只发一次


def test_scan_claude_skills_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path,
        ['{"x":"<command-name>/openspec-driven-development</command-name>"}'])
    tf_hook.scan_claude_skills(_make_payload(transcript))  # 不触发即通过


def test_scan_claude_skills_wrong_runtime_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "codex")  # 不是 claude-code
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path,
        ['{"x":"<command-name>/openspec-driven-development</command-name>"}'])
    tf_hook.scan_claude_skills(_make_payload(transcript))


def test_scan_claude_skills_transcript_missing_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    # transcript_path 字段缺失
    tf_hook.scan_claude_skills({"hook_event_name": "Stop", "session_id": "s1"})
    # transcript_path 指向不存在的路径
    tf_hook.scan_claude_skills(_make_payload(str(tmp_path / "nope.jsonl")))
    # session_id 缺失
    tf_hook.scan_claude_skills({"hook_event_name": "Stop",
                                 "transcript_path": str(tmp_path)})


def test_scan_claude_skills_malformed_names_filtered(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        '{"x":"<command-name>/12345</command-name>"}',          # 纯数字
        '{"x":"<command-name>/-foo</command-name>"}',           # 首字符是连字符
        '{"x":"<command-name>/foo--bar</command-name>"}',       # 连续 --
        '{"x":"<command-name>/foo_</command-name>"}',           # 尾部下划线
        '{"x":"<command-name>/openspec-driven-development</command-name>"}',  # 这条应通过
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = [argv[argv.index("--skill") + 1] for argv in reported]
    assert names == ["openspec-driven-development"]


def test_scan_claude_skills_only_on_stop_and_session_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path,
        ['{"x":"<command-name>/openspec-driven-development</command-name>"}'])

    # 这些事件不应触发扫描
    for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"):
        tf_hook.scan_claude_skills(_make_payload(transcript, event=ev))


def test_main_invokes_scan_claude_skills_on_stop(tmp_path, monkeypatch):
    """main() 末尾必须调 scan_claude_skills,且与 _run_report 串通起来。"""
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path,
        ['{"x":"<command-name>/openspec-driven-development</command-name>"}'])
    payload = {"hook_event_name": "Stop", "session_id": "s-end",
               "transcript_path": transcript}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    # 让 selfupdate 子进程不要真起
    monkeypatch.setattr(tf_hook, "_spawn_selfupdate", lambda d: None)

    tf_hook.main()

    # main 会先 resolve() 出 Stop 自己的 ["--status","done",...] 一条,然后 scan_claude_skills 再追一条
    skill_reports = [a for a in reported if "--skill" in a]
    assert len(skill_reports) == 1
    argv = skill_reports[0]
    assert argv[argv.index("--skill") + 1] == "openspec-driven-development"
    assert argv[argv.index("--session") + 1] == "s-end"
