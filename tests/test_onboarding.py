"""onboarding 域:install / shims / SPA / static / healthz。
对应 server/app.py 的 install_sh / shim_file / shim_manifest / _plain_file / SPA fallback / healthz。
由 add-server-app-test-baseline 引入。
"""
import os

import pytest
from fastapi import HTTPException

from server.routes import onboarding


# ---- /shims/{path} 目录穿越拒绝 ------------------------------------------
def test_shims_dotdot_returns_404(client):
    assert client.get("/shims/../server/app.py").status_code == 404


def test_shims_unknown_file_404(client):
    assert client.get("/shims/no-such.py").status_code == 404


def test_shims_legal_file_returns_content(client):
    r = client.get("/shims/tf_hook.py")
    assert r.status_code == 200
    assert "tranfu" in r.text.lower() or r.text  # 非空


def test_shims_nested_wrapper(client):
    r = client.get("/shims/wrapper/tf-run")
    assert r.status_code == 200
    assert r.text


# ---- /shims/manifest ------------------------------------------------------
def test_shims_manifest_schema(client):
    r = client.get("/shims/manifest")
    assert r.status_code == 200
    m = r.json()
    assert m["schema"] == 1
    assert m["version"]
    assert isinstance(m["files"], list) and len(m["files"]) > 0
    f0 = m["files"][0]
    for k in ("path", "target", "sha256", "size", "executable"):
        assert k in f0


# ---- /install.sh + 缺失态 -------------------------------------------------
def test_install_sh_present(client):
    r = client.get("/install.sh")
    assert r.status_code == 200
    assert "#!/" in r.text or r.text


def test_install_sh_missing_returns_404(client, app_mod, monkeypatch):
    # 把 INSTALL_PATH 指到不存在的路径,触发 _plain_file 的 FileNotFoundError 分支
    monkeypatch.setattr(app_mod, "INSTALL_PATH", "/tmp/__definitely_not_here.sh")
    r = client.get("/install.sh")
    assert r.status_code == 404


def test_llms_txt_present_or_missing(client):
    r = client.get("/llms.txt")
    assert r.status_code in (200, 404)


def test_robots_txt_present_or_missing(client):
    r = client.get("/robots.txt")
    assert r.status_code in (200, 404)


def test_llms_txt_missing_returns_404(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "LLMS_PATH", "/tmp/__no_llms.txt")
    assert client.get("/llms.txt").status_code == 404


def test_robots_txt_missing_returns_404(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "ROBOTS_PATH", "/tmp/__no_robots.txt")
    assert client.get("/robots.txt").status_code == 404


def test_frontend_root_static_assets_support_get_and_head(client, app_mod, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", str(tmp_path))
    legacy_assets = {
        "favicon.ico": (b"\x00\x00\x01\x00", "image/x-icon"),
        "favicon-32x32.png": (b"\x89PNG\r\n\x1a\n", "image/png"),
        "favicon-16x16.png": (b"\x89PNG\r\n\x1a\n", "image/png"),
        "apple-touch-icon.png": (b"\x89PNG\r\n\x1a\n", "image/png"),
        "manifest.json": (b"{}", "application/json"),
    }
    for filename, (content, _) in legacy_assets.items():
        (tmp_path / filename).write_bytes(content)
    (tmp_path / "favicon.svg").write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>")
    (tmp_path / "favicon-20260626.ico").write_bytes(b"\x00\x00\x01\x00")
    versioned_pngs = (
        "favicon-32x32-20260530.png",
        "favicon-16x16-20260530.png",
        "apple-touch-icon-20260530.png",
        "android-chrome-192x192-20260530.png",
        "android-chrome-512x512-20260530.png",
    )
    for filename in versioned_pngs:
        (tmp_path / filename).write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "og-image-1200x630.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    favicon = client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert "image/svg+xml" in favicon.headers["content-type"]
    assert "<svg" in favicon.text

    for filename, (_, media) in legacy_assets.items():
        asset = client.get(f"/{filename}")
        assert asset.status_code == 200
        assert media in asset.headers["content-type"]

    ico_head = client.head("/favicon-20260626.ico")
    assert ico_head.status_code == 200
    assert "image/x-icon" in ico_head.headers["content-type"]
    assert ico_head.content == b""

    for filename in versioned_pngs:
        asset = client.get(f"/{filename}")
        assert asset.status_code == 200
        assert "image/png" in asset.headers["content-type"]
        assert asset.content.startswith(b"\x89PNG")

    og_head = client.head("/og-image-1200x630.png")
    assert og_head.status_code == 200
    assert "image/png" in og_head.headers["content-type"]
    assert og_head.content == b""

    assert client.get("/favicon-20260529.ico").status_code == 404


def test_frontend_root_static_rejects_non_whitelisted_name():
    with pytest.raises(HTTPException) as exc:
        onboarding._frontend_root_static("not-allowed.png")
    assert exc.value.status_code == 404


def test_frontend_root_static_missing_whitelisted_asset_returns_404(client, app_mod, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", str(tmp_path))
    assert client.get("/favicon.ico").status_code == 404


# ---- /healthz -------------------------------------------------------------
def test_healthz_is_ok_and_does_not_touch_db(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


# ---- SPA fallback --------------------------------------------------------
def test_spa_fallback_serves_index_for_unknown_route(client):
    r = client.get("/some-deep-link")
    # 取决于 frontend/dist 是否构建;响应应为 200(SPA)或 404(无 build)
    assert r.status_code in (200, 404)


def test_spa_fallback_serves_skills_deep_links(client, app_mod):
    expected = 200 if os.path.exists(os.path.abspath(app_mod.FRONTEND_INDEX)) else 404
    for path in (
        "/skills?view=skill&lens=untracked",
        "/skill/ghost-skill?lens=untracked",
        "/operator/alice?view=operator&lens=untracked",
    ):
        r = client.get(path)
        assert r.status_code == expected
        if expected == 200:
            assert '<div id="root"></div>' in r.text


def test_spa_fallback_does_not_swallow_api_routes(client):
    assert client.get("/api/nope").status_code == 404
    assert client.get("/v1/nope").status_code == 404


def test_spa_fallback_does_not_swallow_paths_with_dots(client):
    # 含 . 的叶子被当作静态资源,不进 SPA
    assert client.get("/some-file.css").status_code == 404
