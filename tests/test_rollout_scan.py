"""tf_rollout_scan 口径测试 + tf_hook Codex 扫描入口契约测试。

夹具取自真实 thread 019eb6e9(脱敏):agent 用 web-product-craft 审核页面时,
Codex 把"读取 .codex/skills/web-product-craft/SKILL.md"写成一条 function_call。
我们只认这条强信号 —— 技能目录列表(developer message)、用户提示词点名、工具
输出回显、apply_patch 改写、非 dot 目录下的 SKILL.md 一律不算。
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


def test_skills_in_file_only_counts_function_call_reads(tmp_path):
    fp = _write_rollout(tmp_path, FIXTURE)
    assert sorted(tf_rollout_scan.skills_in_file(str(fp))) == EXPECTED


def test_scan_session_finds_file_by_id(tmp_path):
    _write_rollout(tmp_path, FIXTURE)
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == EXPECTED


def test_scan_session_ignores_other_sessions(tmp_path):
    _write_rollout(tmp_path, FIXTURE, session_id="other-session-id")
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == []


def test_no_rollout_returns_empty(tmp_path):
    assert tf_rollout_scan.scan_session(SID, home=str(tmp_path)) == []


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


# --- tf_hook 接入入口 ---

def _stop_event():
    return {"hook_event_name": "Stop", "session_id": SID}


def test_hook_scans_on_codex_stop(monkeypatch):
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    # scan_codex_skills 内部 `import tf_rollout_scan` 取的是同一个已缓存模块对象
    monkeypatch.setattr(tf_rollout_scan, "scan_session", lambda sid, **kw: ["web-product-craft"])
    reported = []
    monkeypatch.setattr(tf_hook, "_run_report", lambda rargs: reported.append(rargs))
    tf_hook.scan_codex_skills(_stop_event())
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
