"""tf_rollout_scan 口径测试 + tf_hook Codex 扫描入口契约测试。

旧夹具取自真实 thread 019eb6e9(脱敏):Codex 把读取 SKILL.md 写成
function_call。新夹具取自 Codex Desktop 0.144 rollout(脱敏):外层是
custom_tool_call exec,真实 shell 调用在 tools.exec_command(...)。两种格式都只认
静态 cmd 读取的强信号;技能目录、提示词点名、输出、改写和动态命令一律不算。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_rollout_scan
import tf_hook


SID = "019eb6e9-ff68-76d2-82e9-d22296407d3f"

# 一份覆盖正例/负例/幂等的最小 rollout。每个元素 = 一行 jsonl。
FIXTURE = [
    # 1) session 元信息 —— 忽略
    {"type": "session_meta", "payload": {"id": SID}},
    # 2) developer message:注入到上下文的"技能目录",列出多个 SKILL.md 路径。
    #    它是 message 不是 function_call,绝不能被计入(否则目录里每个 skill 都中招)。
    {"type": "response_item", "payload": {"type": "message", "role": "developer",
        "content": [{"type": "input_text", "text":
            "可用技能:\n- web-product-craft (file: /repo/.codex/skills/web-product-craft/SKILL.md)\n"
            "- skill-creator (file: /repo/.codex/skills/skill-creator/SKILL.md)"}]}},
    # 3) 用户提示词显式点名 —— 不算使用
    {"type": "response_item", "payload": {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "用 web-product-craft 审核 http://localhost:3000/products/"}]}},
    # 4) 正例:shell function_call 真读了已装 skill 的 SKILL.md
    {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
        "arguments": json.dumps({"cmd": "sed -n '1,220p' /Users/wing/Develop/codex-tranfu-demo/.codex/skills/web-product-craft/SKILL.md",
                                 "workdir": "/Users/wing/Develop/codex-tranfu-demo"})}},
    # 5) 工具输出回显 SKILL.md 内容(含 name: 与另一路径)—— 不算
    {"type": "response_item", "payload": {"type": "function_call_output",
        "output": "Output:\n---\nname: web-product-craft\n# 见 /repo/.codex/skills/other-skill/SKILL.md"}},
    # 6) apply_patch 改写一个 skill 的 SKILL.md —— 是 custom_tool_call,不是 function_call,不算
    {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch",
        "input": "*** Begin Patch\n*** Update File: /repo/.codex/skills/edited-skill/SKILL.md\n*** End Patch"}},
    # 7) 非 dot 目录下的 SKILL.md(skills 作者仓库里的散落文件)—— 不算
    {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
        "arguments": json.dumps({"cmd": "cat /Users/wing/Develop/skillsbench/docs/skills/streamlit/SKILL.md"})}},
    # 8) 正例:.claude 目录同样算
    {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
        "arguments": json.dumps({"cmd": "head -50 ~/.claude/skills/credibility-review/SKILL.md"})}},
    # 9) 同一 skill 再读一次 —— 文件内去重
    {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
        "arguments": json.dumps({"cmd": "sed -n '221,400p' /Users/wing/Develop/codex-tranfu-demo/.codex/skills/web-product-craft/SKILL.md"})}},
]

EXPECTED = ["credibility-review", "web-product-craft"]


def _write_rollout(home, lines, session_id=SID):
    d = home / "sessions" / "2026" / "06" / "11"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"rollout-2026-06-11T21-40-49-{session_id}.jsonl"
    fp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return fp


def test_skills_in_file_counts_legacy_command_reads(tmp_path):
    fp = _write_rollout(tmp_path, FIXTURE)
    assert sorted(tf_rollout_scan.skills_in_file(str(fp))) == EXPECTED


def test_desktop_custom_exec_counts_static_cmd(tmp_path):
    source = """const r = await tools.exec_command({
      cmd: "sed -n '1,620p' /Users/wing/.codex/skills/openspec-driven-development/SKILL.md",
      workdir: "/Users/wing/Develop/tranfucom"
    });
    text(r.output);"""
    fp = _write_rollout(tmp_path, [{"type": "response_item", "payload": {
        "type": "custom_tool_call", "name": "exec", "input": source}}])
    assert tf_rollout_scan.skills_in_file(str(fp)) == {"openspec-driven-development"}


def test_desktop_exec_supports_multiple_calls_and_cross_format_dedupe(tmp_path):
    source = """const results = await Promise.all([
      tools.exec_command({cmd: "cat /r/.codex/skills/web-product-craft/SKILL.md"}),
      tools.exec_command({"cmd": 'head ~/.claude/skills/desktop-beta/SKILL.md'}),
      tools.exec_command({cmd: `sed -n '1,20p' /r/.codex/skills/web-product-craft/SKILL.md`})
    ]);"""
    desktop = {"type": "response_item", "payload": {
        "type": "custom_tool_call", "name": "exec", "input": source}}
    fp = _write_rollout(tmp_path, [FIXTURE[3], desktop])
    assert tf_rollout_scan.skills_in_file(str(fp)) == {
        "desktop-beta", "web-product-craft"}


def test_desktop_exec_ignores_fake_calls_edits_dynamic_cmd_and_other_fields(tmp_path):
    source = r'''const fake = "tools.exec_command({cmd: 'cat /r/.codex/skills/string-only/SKILL.md'})";
    // tools.exec_command({cmd: "cat /r/.codex/skills/line-comment/SKILL.md"})
    /* tools.exec_command({cmd: "cat /r/.codex/skills/block-comment/SKILL.md"}) */
    await tools.apply_patch("*** Update File: /r/.codex/skills/edited/SKILL.md");
    await tools.exec_command({
      cmd: dynamicCmd,
      workdir: "/r/.codex/skills/workdir-only/SKILL.md",
      justification: "mentions /r/.codex/skills/justification-only/SKILL.md"
    });
    await tools.exec_command({
      cmd: `cat /r/.codex/skills/dynamic-template/SKILL.md ${skillName}`
    });
    await tools.exec_command({
      /* a misleading ) in a comment */ cmd /* keep parsing */:
        "printf ')' && cat /r/.codex/skills/real-read/SKILL.md",
      workdir: "/tmp"
    });'''
    fp = _write_rollout(tmp_path, [{"type": "response_item", "payload": {
        "type": "custom_tool_call", "name": "exec", "input": source}}])
    assert tf_rollout_scan.skills_in_file(str(fp)) == {"real-read"}


def test_non_shell_legacy_call_and_malformed_formats_are_ignored(tmp_path):
    lines = [
        {"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent",
            "arguments": json.dumps({"message": "read /r/.codex/skills/delegated/SKILL.md"})}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
            "arguments": "{broken"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
            "input": "tools.exec_command({cmd: 'cat /r/.codex/skills/unclosed/SKILL.md'"}},
    ]
    fp = _write_rollout(tmp_path, lines)
    assert tf_rollout_scan.skills_in_file(str(fp)) == set()


def test_js_lexer_skips_nested_templates_comments_and_fake_identifiers():
    source = r'''const ignored = `outer ${ {nested: `inner ${"value"}`} /* } */ }`;
    mytools.exec_command({cmd: "cat /r/.codex/skills/prefix/SKILL.md"});
    tools.exec_command_suffix({cmd: "cat /r/.codex/skills/suffix/SKILL.md"});
    tools.exec_command /* not a call */;
    tools.exec_command({cmd: "printf ')' && cat /r/.codex/skills/after/SKILL.md"});'''
    calls = list(tf_rollout_scan._js_call_arguments(source))
    assert len(calls) == 1
    assert tf_rollout_scan._static_cmd(calls[0]).endswith("/after/SKILL.md")


def test_static_js_string_and_cmd_parser_cover_escapes_and_nested_fields():
    parsed = tf_rollout_scan._read_static_js_string(r'"a\n\x2f\u0062\q"', 0)
    assert parsed and parsed[0] == "a\n/bq"
    assert tf_rollout_scan._read_static_js_string(r'"\xzz"', 0)[0] == "xzz"
    assert tf_rollout_scan._read_static_js_string('"unterminated', 0) is None
    assert tf_rollout_scan._static_cmd(
        '''{nested: {cmd: "wrong"}, "cmd" /* c */: 'cat /r/.codex/skills/right/SKILL.md'}'''
    ).endswith("/right/SKILL.md")
    assert tf_rollout_scan._static_cmd("buildArgs()") is None
    assert tf_rollout_scan._static_cmd("{cmd: dynamic}") is None
    assert tf_rollout_scan._static_cmd("{cmd: `cat ${name}`} ") is None


def test_payload_normalizer_rejects_unknown_shapes():
    assert tf_rollout_scan._commands_in_payload(None) == []
    assert tf_rollout_scan._commands_in_payload({"type": "function_call",
        "name": "exec_command", "arguments": {"cmd": "x"}}) == []
    assert tf_rollout_scan._commands_in_payload({"type": "function_call",
        "name": "exec_command", "arguments": json.dumps(["x"])}) == []
    assert tf_rollout_scan._commands_in_payload({"type": "custom_tool_call",
        "name": "exec", "input": None}) == []
    assert tf_rollout_scan._commands_in_payload({"type": "message"}) == []


def test_skills_in_file_ignores_invalid_json_and_missing_file(tmp_path):
    fp = tmp_path / "invalid.jsonl"
    fp.write_text("SKILL.md but not json\n", encoding="utf-8")
    assert tf_rollout_scan.skills_in_file(str(fp)) == set()
    assert tf_rollout_scan.skills_in_file(str(tmp_path / "missing.jsonl")) == set()


def test_scan_session_finds_file_by_id(tmp_path):
    _write_rollout(tmp_path, FIXTURE)
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == EXPECTED


def test_scan_session_ignores_other_sessions(tmp_path):
    _write_rollout(tmp_path, FIXTURE, session_id="other-session-id")
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == []


def test_no_rollout_returns_empty(tmp_path):
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == []


def test_file_size_limit_stops_before_parsing_large_line(tmp_path, monkeypatch):
    fp = _write_rollout(tmp_path, [FIXTURE[3]])
    monkeypatch.setattr(tf_rollout_scan, "MAX_BYTES", 1)
    assert tf_rollout_scan.skills_in_file(str(fp)) == set()


def test_developer_catalog_alone_yields_nothing(tmp_path):
    # 只有技能目录(message),没有任何 function_call 读取 -> 零结果
    fp = _write_rollout(tmp_path, [FIXTURE[1]])
    assert tf_rollout_scan.skills_in_file(str(fp)) == set()


def test_skill_name_is_truncated(tmp_path):
    long = "x" * 200
    fp = _write_rollout(tmp_path, [{"type": "response_item", "payload": {
        "type": "function_call", "name": "exec_command",
        "arguments": json.dumps({"cmd": f"cat /r/.codex/skills/{long}/SKILL.md"})}}])
    out = list(tf_rollout_scan.skills_in_file(str(fp)))
    assert out == ["x" * tf_rollout_scan.MAX_SKILL_NAME]


def test_report_skills_emits_one_event_per_name(monkeypatch):
    calls = []
    monkeypatch.setattr(tf_rollout_scan.subprocess, "run",
                        lambda args, **kw: calls.append(args))
    tf_rollout_scan.report_skills(SID, ["a", "b"])
    assert len(calls) == 2
    for args, nm in zip(calls, ["a", "b"]):
        assert "--skill" in args and args[args.index("--skill") + 1] == nm
        assert "--session" in args and args[args.index("--session") + 1] == SID


def test_report_skills_swallows_subprocess_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr(tf_rollout_scan.subprocess, "run", fail)
    tf_rollout_scan.report_skills(SID, ["safe"])


# --- tf_hook 接入入口 ---

def _stop_event(name="Stop"):
    return {"hook_event_name": name, "session_id": SID}


@pytest.mark.parametrize("event_name", ["Stop", "SessionEnd"])
def test_hook_scans_on_codex_end_events(monkeypatch, event_name):
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    # scan_codex_skills 内部 `import tf_rollout_scan` 取的是同一个已缓存模块对象
    monkeypatch.setattr(tf_rollout_scan, "scan_session", lambda sid, **kw: ["web-product-craft"])
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", lambda rargs: reported.append(rargs))
    tf_hook.scan_codex_skills(_stop_event(event_name))
    assert reported and reported[0][reported[0].index("--skill") + 1] == "web-product-craft"


def test_hook_skips_non_codex_runtime(monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.setattr(tf_hook, "_run_report", lambda rargs: pytest.fail("should not report"))
    tf_hook.scan_codex_skills(_stop_event())


def test_hook_respects_report_skills_switch(monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    monkeypatch.setattr(tf_hook, "_run_report", lambda rargs: pytest.fail("should not report"))
    tf_hook.scan_codex_skills(_stop_event())


def test_hook_skips_non_end_events(monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.setattr(tf_hook, "_run_report", lambda rargs: pytest.fail("should not report"))
    tf_hook.scan_codex_skills({"hook_event_name": "PreToolUse", "session_id": SID})
