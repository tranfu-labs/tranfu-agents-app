"""Shim 文件清单生成 + 内容版本(由 refactor-server-app-by-domain 引入)。

onboarding 域:install.sh 与 tf_selfupdate.py 据此校验本地 ~/.tranfu 状态。
模块加载时立即扫盘 SHIMS_DIR(与原行为一致)。
"""
import hashlib
import json
import os

from server.config import _EXECUTABLE_SHIMS, SHIMS_DIR


def _shim_target(rel):
    if rel.startswith("wrapper/"):
        return os.path.basename(rel)
    return rel


def _build_shim_manifest():
    """Content-addressed manifest for the files served from /shims.

    The installer historically flattens wrapper/* into ~/.tranfu while keeping
    nested plugin files such as openclaw/* under their directory. Encoding that
    target path here lets old clients fetch new shim files without hard-coding a
    new download list.
    """
    files = []
    root = os.path.abspath(SHIMS_DIR)
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
        for name in sorted(names):
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            with open(path, "rb") as f:
                data = f.read()
            files.append({
                "path": rel,
                "target": _shim_target(rel),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "executable": rel in _EXECUTABLE_SHIMS or os.access(path, os.X_OK),
            })
    files.sort(key=lambda x: x["path"])
    h = hashlib.sha256()
    for item in files:
        h.update(json.dumps({
            "path": item["path"], "target": item["target"],
            "sha256": item["sha256"], "executable": item["executable"],
        }, sort_keys=True, separators=(",", ":")).encode())
        h.update(b"\n")
    return {"schema": 1, "version": h.hexdigest(), "files": files}


# 模块加载时立即扫盘并固化 manifest(与原 app.py 顶层行为一致)。
_SHIM_MANIFEST = _build_shim_manifest()
