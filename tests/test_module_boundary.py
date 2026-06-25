"""服务端模块边界守门(由 refactor-server-app-by-domain 引入)。

防回归:
1. server/app.py 不可膨胀回大单文件。
2. routes/* 子模块必须独立可 import,无循环依赖。
3. conftest.py 的 monkeypatch 路径(app.<symbol>)必须仍可访问。
4. 子模块顶层不得 from server import app,否则会和 app 末尾 include_router 撞循环。
"""
import importlib
import os
import pathlib


def test_app_py_under_size_limit():
    """server/app.py 仅做组装、可变开关与符号 re-export;不允许放业务代码。"""
    p = os.path.join(os.path.dirname(__file__), "..", "server", "app.py")
    n = sum(1 for _ in open(p))
    assert n <= 220, f"server/app.py {n} lines, expected <= 220"


def test_route_modules_import_independently():
    for mod in ("server.routes.ingest", "server.routes.admin",
                "server.routes.board", "server.routes.onboarding"):
        importlib.import_module(mod)


def test_app_reexports_conftest_contract():
    import server.app as app
    # conftest.py 直接访问的符号必须可读可写
    for name in ("DB_PATH", "INGEST_KEY", "ADMIN_KEY", "ADMIN_MAX_ROWS",
                 "TRASH_DAYS", "STATE_TTL_SECONDS", "REQUIRE_TOKEN",
                 "READ_AUTH_OK", "TRUST_PROXY", "_lock",
                 "_state_cache", "_state_cache_lock",
                 "_rate_lock", "_rate_state",
                 "_prune_state",
                 "_catalog_lock", "_catalog_state", "_catalog_thread_started",
                 "init_db", "sync_catalog_once"):
        assert hasattr(app, name), f"server.app.{name} missing — conftest will break"


def test_submodules_no_toplevel_app_import():
    """子模块只能在函数体内 from server import app,不能写在文件顶层(否则循环 import)。"""
    root = pathlib.Path(__file__).parent.parent / "server"
    offenders = []
    for path in list(root.glob("*.py")) + list((root / "routes").glob("*.py")):
        if path.name in ("app.py", "__init__.py"):
            continue
        in_class_or_func = False
        for raw in path.read_text().splitlines():
            stripped = raw.lstrip()
            if stripped.startswith(("def ", "async def ", "class ")):
                in_class_or_func = True
                continue
            if in_class_or_func:
                continue
            if stripped.startswith(("from server import app", "import server.app")):
                offenders.append(str(path))
                break
    assert not offenders, f"top-level app import found in: {offenders}"
