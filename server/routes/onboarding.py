"""onboarding 域路由(对应 openspec/specs/onboarding/spec.md):
/healthz / / / install.sh / llms.txt / robots.txt / shims/* / SPA fallback。

路径常量(FRONTEND_INDEX/INSTALL_PATH/LLMS_PATH/ROBOTS_PATH/SHIMS_DIR)留在 server/app.py
以保留 monkeypatch 兼容,本模块函数体内通过 `from server import app` 延迟读。
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from server.config import _MEDIA
from server.shim import _SHIM_MANIFEST

router = APIRouter()

_SPA_BLOCKED_PREFIXES = {"api", "v1", "shims", "assets"}
_SPA_BLOCKED_PATHS = {"install.sh", "healthz", "llms.txt", "robots.txt"}


def _spa_index():
    from server import app
    try:
        with open(os.path.abspath(app.FRONTEND_INDEX), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:  # pragma: no cover  — 开发期路径,生产构建必然存在
        return HTMLResponse("<h1>frontend/dist/index.html not found</h1>", status_code=404)


def _plain_file(path, media_type="text/plain"):
    try:
        with open(path, encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type=media_type)
    except FileNotFoundError:
        return PlainTextResponse(f"{os.path.basename(path)} not found", status_code=404)


@router.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")


@router.get("/")
def dashboard():
    return _spa_index()


@router.get("/install.sh")
def install_sh():
    """Serve the installer from the dashboard domain, so teammates can install
    even when the GitHub repo is private:  curl -fsSL $SERVER/install.sh | bash -s -- ..."""
    from server import app
    return _plain_file(app.INSTALL_PATH, "text/x-shellscript")


@router.get("/llms.txt")
def llms_txt():
    from server import app
    return _plain_file(app.LLMS_PATH, "text/plain")


@router.get("/robots.txt")
def robots_txt():
    from server import app
    return _plain_file(app.ROBOTS_PATH, "text/plain")


@router.get("/shims/manifest")
def shim_manifest():
    """Serve the content-addressed shim manifest used by install/self-update."""
    return JSONResponse(_SHIM_MANIFEST)


@router.get("/shims/{path:path}")
def shim_file(path: str):
    """Serve shim client files (install.sh fetches these from $SERVER/shims/...)."""
    from server import app
    target = os.path.abspath(os.path.join(app.SHIMS_DIR, path))
    if not (target == app.SHIMS_DIR or target.startswith(app.SHIMS_DIR + os.sep)) or not os.path.isfile(target):
        raise HTTPException(status_code=404)
    media = _MEDIA.get(os.path.splitext(target)[1], "text/plain")
    with open(target, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type=media)


@router.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve React BrowserRouter deep links without swallowing API/system routes."""
    first = full_path.split("/", 1)[0]
    leaf = full_path.rsplit("/", 1)[-1]
    if first in _SPA_BLOCKED_PREFIXES or full_path in _SPA_BLOCKED_PATHS or "." in leaf:
        raise HTTPException(status_code=404)
    return _spa_index()
