"""tf_report.py 自动注入 shim_version 契约。

设计意图:每次心跳都附带 shim_version,且不强制 caller 显式传参或走 --profile。
tf_hook.py 不感知该字段;由 tf_report 自己从本机 manifest.json 兜底注入。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))


@pytest.fixture
def with_manifest(tmp_path, monkeypatch):
    """把 SHIM_DIR 指向 tmp_path 并写入一份 manifest.json,重置进程内缓存。"""
    import tf_profile
    (tmp_path / "manifest.json").write_text('{"version":"sv-deadbeef"}', encoding="utf-8")
    monkeypatch.setattr(tf_profile, "SHIM_DIR", tmp_path)
    tf_profile._QUICK_SHIM_CACHE["loaded"] = False
    tf_profile._QUICK_SHIM_CACHE["version"] = None
    return tmp_path


def _run_dry(monkeypatch, capsys, argv):
    """跑 tf_report.main() 的 --print 模式,返回 payload dict。"""
    import tf_report
    monkeypatch.setattr(sys, "argv", ["tf_report.py"] + argv + ["--print"])
    # main 走的是 TF_SERVER 兜底;空就走 dry 路径,我们再加 --print 兜两遍。
    monkeypatch.delenv("TF_SERVER", raising=False)
    monkeypatch.setenv("TF_OPERATOR", "alice")
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.setenv("TF_AGENT", "美羊羊")
    tf_report.main()
    out = capsys.readouterr().out
    return json.loads(out)


def test_no_profile_no_flag_payload_still_carries_shim_version(with_manifest, monkeypatch, capsys):
    """这是修复的核心契约:任何 hook 事件(不 --profile)都应该自动带上 shim_version。"""
    p = _run_dry(monkeypatch, capsys, [
        "--status", "running", "--step", "tool: Bash", "--session", "s1",
    ])
    assert p["shim_version"] == "sv-deadbeef"


def test_explicit_flag_wins_over_manifest_cache(with_manifest, monkeypatch, capsys):
    p = _run_dry(monkeypatch, capsys, [
        "--status", "running", "--step", "x", "--session", "s1",
        "--shim-version", "v-override",
    ])
    assert p["shim_version"] == "v-override"


def test_profile_path_already_provides_shim_version(with_manifest, monkeypatch, capsys):
    """--profile 时由 tf_profile.collect() 把 shim_version 塞进 payload,
    后续的兜底逻辑不应重复或覆盖。"""
    p = _run_dry(monkeypatch, capsys, [
        "--status", "started", "--step", "session start", "--session", "s1",
        "--profile",
    ])
    assert p["shim_version"] == "sv-deadbeef"


def test_missing_manifest_omits_field(tmp_path, monkeypatch, capsys):
    """manifest.json 读不到时不抛错、不带字段,让服务端 sticky/前端 unknown 生效。"""
    import tf_profile
    monkeypatch.setattr(tf_profile, "SHIM_DIR", tmp_path)  # 空目录
    tf_profile._QUICK_SHIM_CACHE["loaded"] = False
    tf_profile._QUICK_SHIM_CACHE["version"] = None
    p = _run_dry(monkeypatch, capsys, [
        "--status", "running", "--step", "x", "--session", "s1",
    ])
    assert "shim_version" not in p
