#!/usr/bin/env python3
"""
TRANFU//AGENTS — best-effort shim self-updater (stdlib only).

Runs in the background, normally launched by tf_hook.py on SessionStart. It
downloads /shims/manifest, stages changed files, verifies sha256, py-compiles
Python files, then atomically replaces the installed files under ~/.tranfu.
Failures are silent: telemetry/update must never break the host agent.
"""
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("TF_TRANFU_HOME") or Path(__file__).resolve().parent)
MANIFEST = ROOT / "manifest.json"
STATE = ROOT / ".selfupdate.json"
LOCK = ROOT / ".update.lock"
STAGING = ROOT / ".staging"
ROLLBACK = ROOT / ".rollback"
TIMEOUT = 5
CHECK_INTERVAL = 3600
LOCK_STALE_SECONDS = 900


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(str(tmp), str(path))


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _server():
    return os.environ.get("TF_SERVER", "").rstrip("/")


def _interval():
    try:
        return max(0, int(os.environ.get("TF_AUTO_UPDATE_INTERVAL", CHECK_INTERVAL)))
    except Exception:
        return CHECK_INTERVAL


def _throttled(now=None):
    now = now or time.time()
    st = _read_json(STATE) or {}
    try:
        return now - float(st.get("last_check", 0)) < _interval()
    except Exception:
        return False


def _mark_checked(now=None):
    try:
        _write_json_atomic(STATE, {"last_check": now or time.time()})
    except Exception:
        pass


def _fetch_json(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_bytes(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return r.read()


def _validate_manifest(manifest):
    if not isinstance(manifest, dict):
        return False
    if not isinstance(manifest.get("version"), str) or not manifest["version"]:
        return False
    files = manifest.get("files")
    if not isinstance(files, list):
        return False
    for item in files:
        if not isinstance(item, dict):
            return False
        if not all(isinstance(item.get(k), str) and item.get(k) for k in ("path", "target", "sha256")):
            return False
    return True


def _safe_parts(target):
    if not isinstance(target, str):
        raise ValueError("bad target")
    target = target.replace("\\", "/")
    if target.startswith("/"):
        raise ValueError("absolute target")
    parts = [p for p in target.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ValueError("unsafe target")
    return parts


def _inside(path, root):
    p = path.resolve()
    r = root.resolve()
    return p == r or str(p).startswith(str(r) + os.sep)


def _target_path(item):
    path = ROOT.joinpath(*_safe_parts(item["target"]))
    if not _inside(path, ROOT):
        raise ValueError("target escapes root")
    return path


def _staging_path(item):
    path = STAGING.joinpath(*_safe_parts(item["target"]))
    if not _inside(path, STAGING):
        raise ValueError("staging target escapes root")
    return path


def _rollback_path(item):
    path = ROLLBACK.joinpath(*_safe_parts(item["target"]))
    if not _inside(path, ROLLBACK):
        raise ValueError("rollback target escapes root")
    return path


def _needs_update(item):
    try:
        target = _target_path(item)
        return not target.exists() or _sha256_file(target) != item["sha256"]
    except Exception:
        return True


def _download_changed(server, manifest):
    changed = [item for item in manifest["files"] if _needs_update(item)]
    if not changed:
        return changed
    shutil.rmtree(STAGING, ignore_errors=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    for item in changed:
        url = server + "/shims/" + urllib.parse.quote(item["path"], safe="/")
        data = _fetch_bytes(url)
        if _sha256_bytes(data) != item["sha256"]:
            raise ValueError("sha256 mismatch")
        if item.get("size") is not None and int(item.get("size", len(data))) != len(data):
            raise ValueError("size mismatch")
        staged = _staging_path(item)
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(data)
        if item["target"].endswith(".py"):
            py_compile.compile(str(staged), doraise=True)
    return changed


def _apply_changed(changed):
    if not changed:
        return
    shutil.rmtree(ROLLBACK, ignore_errors=True)
    ROLLBACK.mkdir(parents=True, exist_ok=True)
    applied = []
    try:
        for item in changed:
            target = _target_path(item)
            staged = _staging_path(item)
            backup = _rollback_path(item)
            existed = target.exists()
            if existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(target), str(backup))
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(staged), str(target))
            os.chmod(str(target), 0o755 if item.get("executable") else 0o644)
            applied.append((target, backup, existed))
    except Exception:
        for target, backup, existed in reversed(applied):
            try:
                if existed:
                    os.replace(str(backup), str(target))
                elif target.exists():
                    target.unlink()
            except Exception:
                pass
        raise
    finally:
        shutil.rmtree(ROLLBACK, ignore_errors=True)


def _acquire_lock():
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError:
        try:
            if time.time() - LOCK.stat().st_mtime > LOCK_STALE_SECONDS:
                LOCK.unlink()
                fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                return fd
        except Exception:
            return None
    except Exception:
        return None
    return None


def _release_lock(fd):
    try:
        if fd is not None:
            os.close(fd)
    except Exception:
        pass
    try:
        LOCK.unlink()
    except Exception:
        pass


def _report_update(version):
    try:
        script = ROOT / "tf_report.py"
        if not script.exists():
            return
        subprocess.run(
            ["python3", str(script), "--status", "running", "--step",
             "shim 已自动更新到 " + version[:12], "--profile"],
            timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _ensure_codex_hook_guard():
    """Install/update the local guard even while remote update checks throttle.

    The updater itself is already spawned detached by tf_hook.py, so this local
    launchctl maintenance never blocks the host Codex turn.
    """
    if os.environ.get("TF_RUNTIME") != "codex":
        return False
    script = ROOT / "tf_codex_hook_guard.py"
    if not script.exists():
        return False
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "install-launch-agent"],
            timeout=12, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except Exception:
        return False


def update_once():
    if os.environ.get("TF_AUTO_UPDATE") == "0":
        return False
    server = _server()
    if not server:
        return False
    if _throttled():
        return False
    fd = _acquire_lock()
    if fd is None:
        return False
    try:
        _mark_checked()
        remote = _fetch_json(server + "/shims/manifest")
        if not _validate_manifest(remote):
            return False
        local = _read_json(MANIFEST) or {}
        if local.get("version") == remote["version"] and not any(_needs_update(item) for item in remote["files"]):
            return False
        changed = _download_changed(server, remote)
        _apply_changed(changed)
        _write_json_atomic(MANIFEST, remote)
        shutil.rmtree(STAGING, ignore_errors=True)
        _report_update(remote["version"])
        return True
    finally:
        shutil.rmtree(STAGING, ignore_errors=True)
        _release_lock(fd)


def main():
    try:
        _ensure_codex_hook_guard()
    except Exception:
        pass
    try:
        update_once()
    except Exception:
        pass


if __name__ == "__main__":
    main()
