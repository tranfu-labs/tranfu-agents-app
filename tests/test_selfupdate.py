"""tf_selfupdate safety contract tests."""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_selfupdate


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _manifest(version, data, target="tf_hook.py", path="tf_hook.py", executable=False):
    return {
        "schema": 1,
        "version": version,
        "files": [{
            "path": path,
            "target": target,
            "sha256": _sha(data),
            "size": len(data),
            "executable": executable,
        }],
    }


def _use_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tf_selfupdate, "ROOT", tmp_path)
    monkeypatch.setattr(tf_selfupdate, "MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(tf_selfupdate, "STATE", tmp_path / ".selfupdate.json")
    monkeypatch.setattr(tf_selfupdate, "LOCK", tmp_path / ".update.lock")
    monkeypatch.setattr(tf_selfupdate, "STAGING", tmp_path / ".staging")
    monkeypatch.setattr(tf_selfupdate, "ROLLBACK", tmp_path / ".rollback")
    monkeypatch.setenv("TF_SERVER", "http://updates.example")
    monkeypatch.setenv("TF_AUTO_UPDATE_INTERVAL", "0")
    monkeypatch.delenv("TF_AUTO_UPDATE", raising=False)
    reports = []
    monkeypatch.setattr(tf_selfupdate, "_report_update", reports.append)
    return reports


def test_normal_update_replaces_file_and_writes_manifest(tmp_path, monkeypatch):
    reports = _use_root(tmp_path, monkeypatch)
    old = tmp_path / "tf_hook.py"
    old.write_text("print('old')\n", encoding="utf-8")
    data = b"print('new')\n"
    remote = _manifest("v2", data)
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: remote)
    monkeypatch.setattr(tf_selfupdate, "_fetch_bytes", lambda url: data)

    assert tf_selfupdate.update_once() is True

    assert old.read_bytes() == data
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["version"] == "v2"
    assert reports == ["v2"]


def test_no_change_does_not_download_files(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    data = b"print('same')\n"
    remote = _manifest("v1", data)
    (tmp_path / "tf_hook.py").write_bytes(data)
    (tmp_path / "manifest.json").write_text(json.dumps(remote), encoding="utf-8")
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: remote)
    monkeypatch.setattr(tf_selfupdate, "_fetch_bytes", lambda url: (_ for _ in ()).throw(AssertionError("no download")))

    assert tf_selfupdate.update_once() is False


def test_same_version_repairs_missing_file(tmp_path, monkeypatch):
    reports = _use_root(tmp_path, monkeypatch)
    data = b"print('restored')\n"
    remote = _manifest("v1", data)
    (tmp_path / "manifest.json").write_text(json.dumps(remote), encoding="utf-8")
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: remote)
    monkeypatch.setattr(tf_selfupdate, "_fetch_bytes", lambda url: data)

    assert tf_selfupdate.update_once() is True

    assert (tmp_path / "tf_hook.py").read_bytes() == data
    assert reports == ["v1"]


def test_bad_hash_keeps_old_file(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    old = tmp_path / "tf_hook.py"
    old.write_text("print('old')\n", encoding="utf-8")
    data = b"print('new')\n"
    remote = _manifest("v2", b"different")
    remote["files"][0]["size"] = len(data)
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: remote)
    monkeypatch.setattr(tf_selfupdate, "_fetch_bytes", lambda url: data)

    tf_selfupdate.main()

    assert old.read_text(encoding="utf-8") == "print('old')\n"
    assert not (tmp_path / "manifest.json").exists()


def test_syntax_error_keeps_old_file(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    old = tmp_path / "tf_hook.py"
    old.write_text("print('old')\n", encoding="utf-8")
    data = b"def broken(:\n"
    remote = _manifest("v2", data)
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: remote)
    monkeypatch.setattr(tf_selfupdate, "_fetch_bytes", lambda url: data)

    tf_selfupdate.main()

    assert old.read_text(encoding="utf-8") == "print('old')\n"


def test_throttle_skips_network(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    monkeypatch.setenv("TF_AUTO_UPDATE_INTERVAL", "3600")
    (tmp_path / ".selfupdate.json").write_text(json.dumps({"last_check": time.time()}), encoding="utf-8")
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: (_ for _ in ()).throw(AssertionError("no network")))

    assert tf_selfupdate.update_once() is False


def test_auto_update_switch_disables_all_work(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    monkeypatch.setenv("TF_AUTO_UPDATE", "0")
    monkeypatch.setattr(tf_selfupdate, "_fetch_json", lambda url: (_ for _ in ()).throw(AssertionError("no network")))

    assert tf_selfupdate.update_once() is False


def test_lock_prevents_concurrent_updates(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    fd = tf_selfupdate._acquire_lock()
    try:
        assert fd is not None
        assert tf_selfupdate._acquire_lock() is None
    finally:
        tf_selfupdate._release_lock(fd)


def test_main_ensures_codex_guard_before_throttled_update(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    monkeypatch.setenv("TF_RUNTIME", "codex")
    monkeypatch.setenv("TF_AUTO_UPDATE", "0")
    calls = []
    monkeypatch.setattr(tf_selfupdate, "_ensure_codex_hook_guard",
                        lambda: calls.append("guard") or True)
    monkeypatch.setattr(tf_selfupdate, "update_once",
                        lambda: calls.append("update") or False)

    tf_selfupdate.main()

    assert calls == ["guard", "update"]


def test_guard_ensure_only_runs_for_codex(tmp_path, monkeypatch):
    _use_root(tmp_path, monkeypatch)
    script = tmp_path / "tf_codex_hook_guard.py"
    script.write_text("# guard\n", encoding="utf-8")
    monkeypatch.setenv("TF_RUNTIME", "claude-code")
    monkeypatch.setattr(tf_selfupdate.subprocess, "run",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")))

    assert tf_selfupdate._ensure_codex_hook_guard() is False
