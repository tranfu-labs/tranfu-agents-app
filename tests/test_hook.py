"""tf_hook.resolve 契约测试：Claude/Codex 与 Hermes 事件都映射到正确的上报参数。"""
import io
import json
import multiprocessing
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_hook


def _concurrent_writer(log_path, worker_id, n):
    """multiprocessing 子进程入口:重置 LOG_* 指向同一份临时文件后连写 n 条 hook 日志。
    顶层定义以确保 macOS spawn-mode 下可 pickle。"""
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "shims"))
    import tf_hook as h
    h.LOG_PATH = log_path
    h.LOG_DIR = _os.path.dirname(log_path)
    h.LOG_BAK = log_path + ".1"
    _os.environ.pop("TF_HOOK_DEBUG", None)
    for i in range(n):
        h._hook_log(
            ev="pre_tool_call", tool="t",
            sid=f"w{worker_id}", skill=f"s{i:03d}",
            argv=["--status", "running", "--step", "tool: t",
                  "--session", f"w{worker_id}"],
            rc=0, err="")


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
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda rargs, **kw: reported.append(rargs))

    tf_hook.main()

    assert reported
    assert reported[0][reported[0].index("--skill") + 1] == "lark-base"


# ---------- scan_claude_skills (Claude Code 斜杠 skill 从 transcript jsonl 兜底) ----------

def _write_transcript(tmp_path, lines):
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _command_content(name, *, command_name_first=True):
    command_name = f"<command-name>{name}</command-name>"
    command_message = f"<command-message>{name.lstrip('/')}</command-message>"
    command_args = "<command-args></command-args>"
    if command_name_first:
        return f"{command_name}\n{command_message}\n{command_args}"
    return f"{command_message}\n{command_name}\n{command_args}"


def _command_row(name, *, record_type="user", prefix="", content_list=False,
                 block_type="text", command_name_first=True):
    text = prefix + _command_content(name, command_name_first=command_name_first)
    if content_list:
        if block_type == "text":
            content = [{"type": "text", "text": text}]
        else:
            content = [{"type": block_type, "content": text}]
    else:
        content = text
    return json.dumps({"type": record_type, "message": {"content": content}}, ensure_ascii=False)


def _make_payload(transcript, event="Stop", sid="s-claude-1"):
    return {"hook_event_name": event, "session_id": sid,
            "transcript_path": transcript}


def test_scan_claude_skills_hit_single(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        _command_row("/openspec-driven-development", command_name_first=False),
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
        _command_row("/openspec-driven-development"),
        _command_row("/openspec-driven-development"),  # 重复同 skill
        '{"x":"<command-name>verify</command-name>"}',  # fixture 文本不在 user-message 起头
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = {argv[argv.index("--skill") + 1] for argv in reported}
    assert names == {"openspec-driven-development"}
    assert len(reported) == 1  # 同 skill 在同次扫描里只发一次


def test_scan_claude_skills_only_user_message_at_start(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        _command_row("/from-assistant", record_type="assistant"),
        _command_row("/from-tool-result", content_list=True, block_type="tool_result"),
        _command_row("/openspec-driven-development", prefix="   \n\t"),
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = {argv[argv.index("--skill") + 1] for argv in reported}
    assert names == {"openspec-driven-development"}


@pytest.mark.parametrize("command", [
    "/clear", "/compact", "/context", "/login", "/model", "/memory",
    "/usage", "/help", "/agents", "/doctor", "/hooks", "/permissions",
    "/status", "/cost", "/config", "/exit", "/quit", "/vim", "/mcp",
    "/output-style", "/add-dir", "/resume", "/ide", "/bashes", "/fast",
])
def test_scan_claude_skills_builtin_blacklist(tmp_path, monkeypatch, command):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [_command_row(command)])
    tf_hook.scan_claude_skills(_make_payload(transcript))


def test_scan_claude_skills_subcommand_normalized_to_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [_command_row("/output-style:new")])
    tf_hook.scan_claude_skills(_make_payload(transcript))


def test_scan_claude_skills_fixture_in_middle_not_collected(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [
        _command_row("verify", prefix="fixture says "),
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))


def test_scan_claude_skills_list_of_blocks_content(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        _command_row("/foo-bar", content_list=True),
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = [argv[argv.index("--skill") + 1] for argv in reported]
    assert names == ["foo-bar"]


def test_scan_claude_skills_malformed_json_line_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", reported.append)

    transcript = _write_transcript(tmp_path, [
        '{"type":"user","message":',
        _command_row("/foo-bar"),
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = [argv[argv.index("--skill") + 1] for argv in reported]
    assert names == ["foo-bar"]


def test_scan_claude_skills_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [_command_row("/openspec-driven-development")])
    tf_hook.scan_claude_skills(_make_payload(transcript))  # 不触发即通过


def test_scan_claude_skills_wrong_runtime_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "codex")  # 不是 claude-code
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [_command_row("/openspec-driven-development")])
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
        _command_row("/12345"),          # 纯数字
        _command_row("/-foo"),           # 首字符是连字符
        _command_row("/foo--bar"),       # 连续 --
        _command_row("/foo_"),           # 尾部下划线
        _command_row("/openspec-driven-development"),  # 这条应通过
    ])
    tf_hook.scan_claude_skills(_make_payload(transcript))

    names = [argv[argv.index("--skill") + 1] for argv in reported]
    assert names == ["openspec-driven-development"]


def test_scan_claude_skills_only_on_stop_and_session_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no report")))

    transcript = _write_transcript(tmp_path, [_command_row("/openspec-driven-development")])

    # 这些事件不应触发扫描
    for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"):
        tf_hook.scan_claude_skills(_make_payload(transcript, event=ev))


def test_main_invokes_scan_claude_skills_on_stop(tmp_path, monkeypatch):
    """main() 末尾必须调 scan_claude_skills,且与 _run_report 串通起来。"""
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report",
                        lambda rargs, **kw: reported.append(rargs))

    transcript = _write_transcript(tmp_path, [_command_row("/openspec-driven-development")])
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


# ============= _hook_log Hermes 钩子链路常态结构化诊断日志 (ADR-0022) =============

@pytest.fixture
def hook_log_tmp(tmp_path, monkeypatch):
    """把 LOG_DIR/LOG_PATH/LOG_BAK 重定向到 tmp_path,确保 TF_HOOK_DEBUG 默认未设。"""
    log_dir = str(tmp_path / "logs")
    log_path = os.path.join(log_dir, "hermes-hook.ndjson")
    log_bak = log_path + ".1"
    monkeypatch.setattr(tf_hook, "LOG_DIR", log_dir)
    monkeypatch.setattr(tf_hook, "LOG_PATH", log_path)
    monkeypatch.setattr(tf_hook, "LOG_BAK", log_bak)
    monkeypatch.delenv("TF_HOOK_DEBUG", raising=False)
    return log_path, log_bak


def _read_log(log_path):
    with open(log_path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def test_hook_log_fields_complete(hook_log_tmp):
    """(a) 字段完整:pre_tool_call + skill_view(name='plan')"""
    log_path, _ = hook_log_tmp
    tf_hook._hook_log(
        ev="pre_tool_call", tool="skill_view",
        sid="sess_abcdef0123", skill="plan",
        argv=["--status", "running", "--step", "tool: skill_view",
              "--session", "sess_abcdef0123", "--skill", "plan"],
        rc=0, err="")
    rows = _read_log(log_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["ev"] == "pre_tool_call"
    assert r["tool"] == "skill_view"
    assert r["sid"] == "sess_abc"  # 前 8 字符脱敏
    assert r["skill"] == "plan"
    assert r["argv_tail"].endswith("--skill plan")
    assert r["rc"] == 0
    assert r["err"] == ""
    assert r["ts"].endswith("Z") and len(r["ts"]) == 20  # UTC ISO8601 秒精度


def test_hook_log_records_empty_skill(hook_log_tmp):
    """(b) 空 skill 也记:pre_tool_call + tool_name=terminal → 'hook 跑了但未识别 skill' 可被看见"""
    log_path, _ = hook_log_tmp
    tf_hook._hook_log(
        ev="pre_tool_call", tool="terminal",
        sid="s1", skill="",
        argv=["--status", "running", "--step", "tool: terminal", "--session", "s1"],
        rc=0, err="")
    rows = _read_log(log_path)
    assert len(rows) == 1
    assert rows[0]["skill"] == ""
    assert rows[0]["tool"] == "terminal"
    assert "--skill" not in rows[0]["argv_tail"]


def test_hook_log_records_skills_list_and_skill_manage(hook_log_tmp):
    """(c) skills_list / skill_manage 也记 —— 区分'hook 跑了 + 被过滤' vs 'hook 没跑'"""
    log_path, _ = hook_log_tmp
    for tool in ("skills_list", "skill_manage"):
        tf_hook._hook_log(
            ev="pre_tool_call", tool=tool, sid="s1", skill="",
            argv=["--status", "running", "--step", f"tool: {tool}", "--session", "s1"],
            rc=0, err="")
    rows = _read_log(log_path)
    assert [r["tool"] for r in rows] == ["skills_list", "skill_manage"]
    assert all(r["skill"] == "" for r in rows)


def test_hook_log_privacy_omits_tool_input_payload(hook_log_tmp):
    """(d) 隐私守门:tool_input 含 command/secret → 日志只含识别出的 skill 名,不含原 payload"""
    log_path, _ = hook_log_tmp
    sensitive = {"name": "x", "command": "rm -rf /", "secret": "k"}
    extracted = tf_hook._skill_from_tool_input({"tool_input": sensitive})
    assert extracted == "x"
    tf_hook._hook_log(
        ev="pre_tool_call", tool="skill_view",
        sid="s1", skill=extracted,
        argv=["--status", "running", "--step", "tool: skill_view",
              "--session", "s1", "--skill", "x"],
        rc=0, err="")
    raw = open(log_path, encoding="utf-8").read()
    assert "rm -rf /" not in raw
    assert "secret" not in raw
    assert '"skill": "x"' in raw


def test_hook_log_rotates_at_max_size(hook_log_tmp, monkeypatch):
    """(e) 轮转:LOG_MAX 缩到 500,连写 5 条 → .1 文件出现 + bak ≥ 阈值 + current 在阈值内(没无限膨胀)"""
    log_path, log_bak = hook_log_tmp
    monkeypatch.setattr(tf_hook, "LOG_MAX", 500)
    for i in range(5):
        tf_hook._hook_log(
            ev="pre_tool_call", tool="skill_view",
            sid=f"s{i:04d}xx", skill="plan",
            argv=["--status", "running", "--step", "tool: skill_view",
                  "--session", f"s{i:04d}xx", "--skill", "plan"],
            rc=0, err="")
    assert os.path.exists(log_bak)
    assert os.path.exists(log_path)
    # rotate 真的发生过 → bak 收下了那段超阈值的内容
    assert os.stat(log_bak).st_size >= tf_hook.LOG_MAX
    # current 自 rotate 后重新累积,大小受 LOG_MAX 守门,不会无限膨胀
    assert os.stat(log_path).st_size < tf_hook.LOG_MAX


def test_hook_log_gates_claude_codex_events(hook_log_tmp):
    """(f) Claude/Codex 守门:PreToolUse (CamelCase) 经 _hook_log 不落"""
    log_path, _ = hook_log_tmp
    tf_hook._hook_log(
        ev="PreToolUse", tool="Skill", sid="s1", skill="x",
        argv=["--status", "running", "--step", "tool: Skill",
              "--session", "s1", "--skill", "x"],
        rc=0, err="")
    assert not os.path.exists(log_path)


def test_hook_log_disabled_by_env(hook_log_tmp, monkeypatch):
    """(g) TF_HOOK_DEBUG=0 关闭逃逸口"""
    log_path, _ = hook_log_tmp
    monkeypatch.setenv("TF_HOOK_DEBUG", "0")
    tf_hook._hook_log(
        ev="pre_tool_call", tool="skill_view",
        sid="s1", skill="plan",
        argv=["--status", "running", "--step", "tool: skill_view",
              "--session", "s1", "--skill", "plan"],
        rc=0, err="")
    assert not os.path.exists(log_path)


def test_hook_log_failure_does_not_break_run_report(hook_log_tmp, monkeypatch):
    """(h) 写失败静默:makedirs 抛异常,_run_report 仍正常完成 + tf_report.py 被调起"""
    monkeypatch.setattr(tf_hook.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError("readonly")))
    seen = {}

    class FakeProc:
        returncode = 0
        stderr = b""

    def fake_run(args, **kw):
        seen["args"] = args
        return FakeProc()

    monkeypatch.setattr(tf_hook.subprocess, "run", fake_run)
    tf_hook._run_report(["--status", "running", "--step", "tool: skill_view",
                         "--session", "s1", "--skill", "plan"],
                        ev="pre_tool_call", tool="skill_view",
                        sid="s1", skill="plan")
    assert seen["args"][-1] == "plan"  # tf_report.py 仍被调起到末参数


def test_hook_log_concurrent_appends_are_atomic(tmp_path, monkeypatch):
    """(j) 并发 4 进程 × 100 条:总行数恰好 400 + 每行可独立 json.loads(O_APPEND 原子性回归)"""
    log_dir = str(tmp_path / "logs")
    log_path = os.path.join(log_dir, "hermes-hook.ndjson")
    log_bak = log_path + ".1"
    monkeypatch.setattr(tf_hook, "LOG_DIR", log_dir)
    monkeypatch.setattr(tf_hook, "LOG_PATH", log_path)
    monkeypatch.setattr(tf_hook, "LOG_BAK", log_bak)
    monkeypatch.delenv("TF_HOOK_DEBUG", raising=False)
    os.makedirs(log_dir, exist_ok=True)

    procs = [multiprocessing.Process(target=_concurrent_writer, args=(log_path, i, 100))
             for i in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    with open(log_path, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    assert len(lines) == 400
    for ln in lines:
        json.loads(ln)  # 不抛 = 行未交错
