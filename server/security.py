"""鉴权 / 速率限流 / 安全响应头(由 refactor-server-app-by-domain 引入)。

跨 spec 域共享:ingest 写、admin 写、export 都走 check_auth / check_admin;
限流器以 (bucket, ip) 为键,enroll / admin 各自独立桶。

`INGEST_KEY/ADMIN_KEY/TRUST_PROXY/HSTS_FORCE/ADMIN_RATE_*/ADMIN_LOCK_*` 与全局
`_lock` 是可变开关 / 模块状态,留在 server/app.py;本模块函数体内 from server import app
延迟读,避免循环 import。
"""
import hmac
import threading
import time
from contextlib import closing

from fastapi import HTTPException, Request

from server.config import _RATE_MAX_ENTRIES
from server.db import _audit, _sha, db


# 锁定本源的 CSP:script 仅允许同源(挡掉注入的内联/外链脚本偷 sessionStorage
# 里的管理钥匙);connect 仅同源(挡外传);style/font/img 放行前端实际用到的
# Google Fonts 与品牌图床。前端无内联脚本(JSON-LD 数据块不受 script-src 管控)。
# 维护规则:前端新接外部域名(脚本/接口/字体/图片/iframe)时,必须把该来源加进
# 对应指令(脚本->script-src、fetch/ws->connect-src、字体->font-src、图片->img-src),
# 否则浏览器会静默拦截、功能坏掉。改完按 AGENTS.md「修改后检查」核对暗/亮主题。
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' https://tranfu.com data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    _cache_headers(request.url.path, resp)
    if _req_is_https(request):
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp


def _cache_headers(path, resp):
    """Keep entry HTML revalidated while letting Vite fingerprinted assets stick."""
    if getattr(resp, "status_code", 500) >= 400:
        return
    if path.startswith("/assets/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return
    if "text/html" in resp.headers.get("content-type", ""):
        resp.headers.setdefault("Cache-Control", "no-cache")


def _key_eq(given, expected):
    """常量时间比较:避免按字符短路泄露 key 长度/前缀;编码成 bytes 兼容
    非 ASCII 输入,且不会因输入类型异常抛 500。"""
    return hmac.compare_digest((given or "").encode("utf-8"), (expected or "").encode("utf-8"))


def check_auth(key):
    from server import app
    if app.INGEST_KEY and not _key_eq(key, app.INGEST_KEY):
        raise HTTPException(status_code=401, detail="bad ingest key")


def _client_host(request):
    """真实客户端 IP。反代后 request.client.host 恒为反代 IP,直接限流会
    『一人触发、全员被封』。仅在显式声明可信反代(TRUST_PROXY)时,才取
    X-Forwarded-For 的最右段(可信反代追加的那一跳);否则用连接对端 IP。"""
    from server import app
    try:
        if app.TRUST_PROXY:
            xff = request.headers.get("x-forwarded-for", "")
            if xff:
                parts = [p.strip() for p in xff.split(",") if p.strip()]
                if parts:
                    return parts[-1]
        return request.client.host or "unknown"
    except Exception:  # pragma: no cover  — 防御性兜底,request.client 缺失场景在 TestClient 中难触发
        return "unknown"


def _req_is_https(request):
    from server import app
    if app.HSTS_FORCE:
        return True
    try:
        if app.TRUST_PROXY and request.headers.get("x-forwarded-proto", "").lower() == "https":
            return True
        return request.url.scheme == "https"
    except Exception:  # pragma: no cover  — request.url 缺失场景在 TestClient 中难触发
        return False


# ------------------------------------------------------------ 防爆破限流(进程内)
# bucket(如 "admin" / "enroll")× 来源 IP 为键,做滑窗失败计数 + 指数退避封锁。
# 只碰内存与一把独立轻锁,不抢全局 DB 写锁、不引入 Redis(契合「无外部服务」)。
_rate_lock = threading.Lock()
_rate_state = {}   # (bucket, ip) -> {win_start, fails, audited, blocked_until, streak}


def _rate_prune(now):
    """惰性清理:超过硬上限时,丢弃既未封锁、窗口又已过期的陈旧条目。"""
    from server import app
    if len(_rate_state) <= _RATE_MAX_ENTRIES:
        return
    stale = [k for k, e in _rate_state.items()  # pragma: no cover  — 触发条件是 _RATE_MAX_ENTRIES=10000 撑爆,测试夹具不易造
             if e["blocked_until"] <= now and now - e["win_start"] >= app.ADMIN_RATE_WINDOW]
    for k in stale:  # pragma: no cover
        _rate_state.pop(k, None)


def _rate_retry_after(bucket, ip):
    """命中封锁窗口则返回剩余秒数(>=1),否则 None。无副作用。"""
    now = time.time()
    with _rate_lock:
        e = _rate_state.get((bucket, ip))
        if e and e["blocked_until"] > now:
            return int(e["blocked_until"] - now) + 1
    return None


def _rate_register_failure(bucket, ip):
    """记一次验钥失败。返回 (should_audit, retry_after)。
    should_audit:本窗口是否首次失败(降噪,每来源每窗口至多审计一条)。
    retry_after:本次失败若触发封锁则为剩余秒数,否则 None。"""
    from server import app
    now = time.time()
    with _rate_lock:
        e = _rate_state.get((bucket, ip))
        if e is None or now - e["win_start"] >= app.ADMIN_RATE_WINDOW:
            e = {"win_start": now, "fails": 0, "audited": False,
                 "blocked_until": e["blocked_until"] if e else 0.0,
                 "streak": e["streak"] if e else 0}
            _rate_state[(bucket, ip)] = e
        e["fails"] += 1
        should_audit = not e["audited"]
        e["audited"] = True
        retry_after = None
        if e["fails"] > app.ADMIN_RATE_MAX:
            lock = min(app.ADMIN_LOCK_BASE * (2 ** e["streak"]), app.ADMIN_LOCK_MAX)
            e["streak"] = min(e["streak"] + 1, 30)
            e["blocked_until"] = now + lock
            retry_after = int(lock) + 1
        _rate_prune(now)
        return should_audit, retry_after


def _rate_register_success(bucket, ip):
    """验钥成功:清除该来源的失败/封锁记录。"""
    with _rate_lock:
        _rate_state.pop((bucket, ip), None)


def _admin_actor(key, request):
    kid = _sha(key or "")[:10] if key else "missing"
    return f"admin:{kid}@{_client_host(request)}"


def _audit_denied(request, key, selector=None):
    from server import app
    try:
        with app._lock, closing(db()) as conn:
            _audit(conn, _admin_actor(key, request), "denied", selector or {}, {}, None)
            conn.commit()
    except Exception:  # pragma: no cover  — 审计兜底,DB 不可写时静默
        pass


def check_admin(key, request, selector=None):
    from server import app
    ip = _client_host(request)
    actor = _admin_actor(key, request)
    # 1) 命中封锁窗口:直接 429,不验钥、不写审计(防爆破 + 写放大 DoS)
    retry = _rate_retry_after("admin", ip)
    if retry is not None:
        raise HTTPException(status_code=429, detail="too many attempts",
                            headers={"Retry-After": str(retry)})
    # 2) 常量时间比较(见 _key_eq)
    if not (bool(app.ADMIN_KEY) and _key_eq(key, app.ADMIN_KEY)):
        should_audit, retry = _rate_register_failure("admin", ip)
        if should_audit:                  # 每来源每窗口至多一条 denied 汇总(降噪)
            _audit_denied(request, key, selector)
        if retry is not None:             # 本次失败触发封锁 -> 429 + Retry-After
            raise HTTPException(status_code=429, detail="too many attempts",
                                headers={"Retry-After": str(retry)})
        raise HTTPException(status_code=403, detail="admin disabled or bad key")
    _rate_register_success("admin", ip)   # 验钥成功:清空该来源失败计数
    return actor
