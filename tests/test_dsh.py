"""DSH 接入契约:事件分发器映射、插件自动安装(幂等/静默/开关)、manifest 收录、selfupdate 守护。"""
import io
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_dsh_event
import tf_dsh_plugin
import tf_hook
import tf_selfupdate


def _msg(event, **kw):
    return {"protocol": 1, "event": event, "session_id": "s1", **kw}


# ---------- tf_dsh_event ----------

@pytest.mark.parametrize("msg,name", [
    (_msg("session/created"), "SessionStart"),
    (_msg("session/disposed"), "SessionEnd"),
    (_msg("session/event", type="turn/start"), "UserPromptSubmit"),
    (_msg("session/event", type="turn/end"), "Stop"),
    (_msg("tools/pre-execute", tool="bash"), "PreToolUse"),
    (_msg("tools/result", tool="bash"), "PostToolUse"),
    (_msg("agent/error"), "Stop"),
    (_msg("agent/turn-stopping"), "Stop"),
])
def test_event_mapping(msg, name):
    d = tf_dsh_event.to_hook_payload(msg)
    assert d["hook_event_name"] == name and d["session_id"] == "s1"
    assert tf_hook.resolve(d) is not None  # tf_hook 认得


@pytest.mark.parametrize("msg", [
    {"protocol": 2, "event": "session/created", "session_id": "s"},   # 未知 protocol
    _msg("session/event", type="step/start"),                         # 无关内部类型
    _msg("nope"),
    {"protocol": 1, "event": "session/created"},                      # 无 session
    "junk", None,
])
def test_unknown_or_malformed_ignored(msg):
    assert tf_dsh_event.to_hook_payload(msg) is None


def test_skill_tool_reports_skill_and_flag_off(monkeypatch):
    d = tf_dsh_event.to_hook_payload(_msg("tools/pre-execute", tool="skill_view", skill="alpha"))
    monkeypatch.delenv("TF_REPORT_SKILLS", raising=False)
    args = tf_hook.resolve(d)
    assert args[args.index("--skill") + 1] == "alpha"
    assert "tool: skill_view" in args
    monkeypatch.setenv("TF_REPORT_SKILLS", "0")
    assert "--skill" not in tf_hook.resolve(d)
    # PostToolUse 不带 skill
    post = tf_dsh_event.to_hook_payload(_msg("tools/result", tool="skill_view", skill="alpha"))
    assert "tool_input" not in post


def test_load_env_file(tmp_path):
    f = tmp_path / "tf_env.dsh.sh"
    f.write_text('export TF_SERVER="http://x"\nexport TF_KEY=k\nunset TF_MODELS\n# c\n')
    env = {"TF_MODELS": "m"}
    assert tf_dsh_event.load_env_file(str(f), env) is True
    assert env == {"TF_SERVER": "http://x", "TF_KEY": "k"}
    assert tf_dsh_event.load_env_file(str(tmp_path / "missing"), env) is False


def test_main_feeds_tf_hook_and_never_raises(monkeypatch):
    seen = {}
    monkeypatch.setattr(tf_hook, "main", lambda: seen.update(d=json.loads(sys.stdin.read())))
    monkeypatch.setattr(tf_dsh_event, "load_env_file", lambda *a, **k: False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_msg("session/created"))))
    tf_dsh_event.main()
    assert seen["d"] == {"hook_event_name": "SessionStart", "session_id": "s1"}
    assert os.environ["TF_RUNTIME"] == "dsh"
    # 坏输入与内部异常都静默
    monkeypatch.setattr(sys, "stdin", io.StringIO("{bad"))
    tf_dsh_event.main()
    monkeypatch.setattr(tf_hook, "main", lambda: 1 / 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_msg("session/created"))))
    tf_dsh_event.main()


def test_main_drops_inherited_agent_identity(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(tf_hook, "main", lambda: seen.update(agent=os.environ.get("TF_AGENT"),
                                                              role=os.environ.get("TF_ROLE")))
    monkeypatch.setenv("TF_AGENT", "沸羊羊")          # 从 Codex 会话继承
    monkeypatch.setenv("TF_ROLE", "Codex agent")
    monkeypatch.setattr(tf_dsh_event, "load_env_file", lambda *a, **k: False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_msg("session/created"))))
    tf_dsh_event.main()
    assert seen == {"agent": None, "role": None}


# ---------- tf_dsh_plugin ----------

def _profile(home, name, linked_dir=None):
    p = home / "profiles" / name
    p.mkdir(parents=True)
    data = {"name": "dsh-profile-" + name, "dependencies": {},
            "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base"]}}}
    if linked_dir:
        data["dependencies"][tf_dsh_plugin.PKG] = "link:" + str(linked_dir)
        data["dsh"]["profile"]["bundles"].append(tf_dsh_plugin.PKG)
    (p / "package.json").write_text(json.dumps(data))


@pytest.fixture
def dsh_env(tmp_path, monkeypatch):
    th = tmp_path / "tranfu"
    (th / "dsh").mkdir(parents=True)
    (th / "dsh" / "package.json").write_text("{}")
    monkeypatch.setenv("TF_TRANFU_HOME", str(th))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))
    monkeypatch.delenv("TF_DSH_PLUGIN", raising=False)
    monkeypatch.setattr(tf_dsh_plugin, "find_cli", lambda: "/fake/dsh")
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw["env"]["DSH_HOME"]))
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(tf_dsh_plugin.subprocess, "run", fake_run)
    return tmp_path, th, calls


def test_no_dsh_home_does_nothing(dsh_env):
    _, _, calls = dsh_env
    assert tf_dsh_plugin.ensure() == [] and calls == []


def test_installs_unlinked_profiles_only(dsh_env):
    tmp, th, calls = dsh_env
    home = tmp / "dsh"
    _profile(home, "desktop")
    _profile(home, "web", linked_dir=th / "dsh")
    (home / "profiles" / "junk").mkdir()   # 无 package.json,忽略
    assert tf_dsh_plugin.ensure() == ["desktop"]
    assert calls == [(["/fake/dsh", "plugin", "--profile", "desktop", "add",
                       "link:" + str(th / "dsh")], str(home))]


def test_switch_off_and_missing_pieces(dsh_env, monkeypatch):
    tmp, th, calls = dsh_env
    _profile(tmp / "dsh", "desktop")
    monkeypatch.setenv("TF_DSH_PLUGIN", "0")
    assert tf_dsh_plugin.ensure() == []
    monkeypatch.delenv("TF_DSH_PLUGIN")
    monkeypatch.setattr(tf_dsh_plugin, "find_cli", lambda: None)
    assert tf_dsh_plugin.ensure() == []
    monkeypatch.setattr(tf_dsh_plugin, "find_cli", lambda: "/fake/dsh")
    (th / "dsh" / "package.json").unlink()
    assert tf_dsh_plugin.ensure() == [] and calls == []


def test_cli_failure_is_silent(dsh_env, monkeypatch):
    tmp, _, _ = dsh_env
    _profile(tmp / "dsh", "desktop")
    monkeypatch.setattr(tf_dsh_plugin.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert tf_dsh_plugin.ensure() == []
    assert tf_dsh_plugin.main(["ensure"]) == 0


def test_status_and_main(dsh_env, capsys):
    tmp, th, _ = dsh_env
    _profile(tmp / "dsh", "desktop", linked_dir=th / "dsh")
    assert tf_dsh_plugin.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["profiles"] == {"desktop": True}


def test_env_file_generated_from_shared_env(dsh_env):
    tmp, th, _ = dsh_env
    _profile(tmp / "dsh", "desktop")
    (th / "tf_env.sh").write_text(
        'export TF_SERVER="http://x"\nexport TF_KEY="k"\nexport TF_OPERATOR="op"\n'
        'export TF_AGENT="other"\nexport TF_ROLE="r"\nexport TF_RUNTIME="codex"\n')
    tf_dsh_plugin.ensure()
    f = th / "tf_env.dsh.sh"
    body = f.read_text()
    assert 'TF_SERVER="http://x"' in body and 'TF_KEY="k"' in body and 'TF_OPERATOR="op"' in body
    assert 'TF_RUNTIME="dsh"' in body and 'TF_AGENT="大肥鱼"' in body
    assert "other" not in body and "TF_ROLE" not in body
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    f.write_text("custom")                      # 已存在不覆盖
    tf_dsh_plugin.ensure()
    assert f.read_text() == "custom"


def test_env_file_skipped_without_shared_env_or_server(dsh_env):
    tmp, th, _ = dsh_env
    _profile(tmp / "dsh", "desktop")
    tf_dsh_plugin.ensure()
    assert not (th / "tf_env.dsh.sh").exists()
    (th / "tf_env.sh").write_text('export TF_OPERATOR="op"\n')
    tf_dsh_plugin.ensure()
    assert not (th / "tf_env.dsh.sh").exists()


# ---------- manifest / selfupdate ----------

def test_manifest_includes_dsh_files_with_safe_targets():
    from server.shim import _build_shim_manifest
    files = {f["path"]: f for f in _build_shim_manifest()["files"]}
    for p in ("dsh/package.json", "dsh/index.js", "dsh/cordis.patch.yml", "dsh/icon.svg",
              "dsh/locale/en.json", "dsh/locale/zh.json", "tf_dsh_event.py", "tf_dsh_plugin.py"):
        assert p in files and files[p]["target"] == p
        assert ".." not in files[p]["target"] and not files[p]["target"].startswith("/")


def test_selfupdate_ensure_dsh_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(tf_selfupdate, "ROOT", tmp_path)
    assert tf_selfupdate._ensure_dsh_plugin() is False          # 脚本不存在
    (tmp_path / "tf_dsh_plugin.py").write_text("")
    ran = []
    monkeypatch.setattr(tf_selfupdate.subprocess, "run",
                        lambda argv, **k: ran.append(argv) or subprocess.CompletedProcess(argv, 0))
    assert tf_selfupdate._ensure_dsh_plugin() is True and ran[0][-2:] == ["ensure", "--quiet"]
    monkeypatch.setenv("TF_DSH_PLUGIN", "0")
    assert tf_selfupdate._ensure_dsh_plugin() is False
    monkeypatch.delenv("TF_DSH_PLUGIN")
    monkeypatch.setattr(tf_selfupdate.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert tf_selfupdate._ensure_dsh_plugin() is False
