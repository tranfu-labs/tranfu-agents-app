"""
TRANFU//AGENTS — collector server. Implements TATP v0.1 (see ../PROTOCOL.md).

Ingest:
  POST /v1/enroll        admin (X-TF-Key) issues a per-operator token (one-time)
  POST /v1/events        JSON heartbeat (all agents via shim / MCP reporter)
                         May carry OPTIONAL profile fields (models, config, mcp,
                         skills, integrations, about, tips, cf, instructions,
                         memory). instructions+memory are sensitive -> opt-in and
                         gated by read-side auth (see PROTOCOL.md §5).
  DELETE /v1/events      legacy admin (X-TF-Admin-Key) cleanup — drop events by session_ids or
                         by identity (operator[/agent/runtime]); optional profile
                         clear. For pruning test/junk sessions off the board.

Read:
  GET  /api/state        snapshot the dashboard polls (sessions + profile +
                         computed quality + leverage + 90d activity)
  GET  /api/skills       SKILLS overview (skill and operator aggregates)
  GET  /api/skill/{name} single skill detail
  GET  /api/operator/{name}
                         single operator skill-usage detail
  GET  /api/agent/{key}  single agent detail (key = "operator::agentOrRuntime")
  GET  /api/admin/inventory
  POST /api/admin/preview
  DELETE /api/admin/data
  GET  /api/admin/trash
  POST /api/admin/restore
                         admin cleanup (X-TF-Admin-Key)
  POST /api/admin/export consistent SQLite snapshot download (X-TF-Admin-Key);
                         whole-DB export, requires body {"confirm":"EXPORT"}
  GET  /                 the dashboard
  GET  /healthz

Storage is SQLite (WAL) at $TF_DB, default ./tf.db. No external services.
"""
import os, sys, json, sqlite3, time, threading, hashlib, hmac, secrets, urllib.request, uuid
from datetime import datetime, timezone, timedelta
from contextlib import closing
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = os.environ.get("TF_DB", "tf.db")
INGEST_KEY = os.environ.get("TF_KEY", "")          # "" = no auth (dev only)
ADMIN_KEY = os.environ.get("TF_ADMIN_KEY", "")     # "" = admin endpoints disabled
# per-operator attribution: when on, every event MUST carry a valid X-TF-Token
# whose bound operator matches the body's `operator` (TATP v0.1 §4).
REQUIRE_TOKEN = os.environ.get("TF_REQUIRE_TOKEN", "0") == "1"
# read-side auth gate for content capture (TATP v0.1 §5). Sensitive fields are
# stored ONLY when read access is protected: either the app read-key is set, or
# the operator asserts an edge gate (Cloudflare Access / Caddy) via TF_READ_AUTH=1.
READ_AUTH_OK = bool(os.environ.get("TF_READ_KEY")) or os.environ.get("TF_READ_AUTH", "0") == "1"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIST = os.path.join(REPO_ROOT, "frontend", "dist")
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
SHIMS_DIR = os.path.join(REPO_ROOT, "shims")
INSTALL_PATH = os.path.join(REPO_ROOT, "install.sh")
LLMS_PATH = os.path.join(REPO_ROOT, "llms.txt")
ROBOTS_PATH = os.path.join(REPO_ROOT, "robots.txt")
_MEDIA = {".sh": "text/x-shellscript", ".py": "text/x-python",
          ".js": "text/javascript", ".mjs": "text/javascript",
          ".json": "application/json", ".md": "text/markdown"}
_EXECUTABLE_SHIMS = {
    "tf_client.sh", "tf_hooks.py", "tf_claude_hooks.py",
    "wrapper/tf-run", "wrapper/tf-hermes-hook.sh", "wrapper/tf-doctor",
}

# profile keys the shim MAY include on an event (all optional, opt-in)
PROFILE_KEYS = ("models", "config", "mcp", "skills", "integrations",
                "about", "tips", "cf", "instructions", "memory",
                "shim_version")
# sensitive fields gated behind read-side auth (dropped if read access is open)
SENSITIVE_KEYS = ("input", "output", "instructions", "memory")

# §8 size limits
MAX_BODY = 256 * 1024          # reject the whole POST above this -> 413
MAX_CONTENT = 16 * 1024        # stored input/output, each
MAX_META = 4 * 1024            # stored meta json
MAX_SKILL_NAME = 160           # skill usage metadata, bounded like other strings
WINDOW_DAYS = 90               # retention + read window
SKILL_MODES = {"used", "equipped"}

# 启动自检:管理钥匙若过短或为常见示例值,在线猜测成本极低 —— 打印告警(不阻断)。
_WEAK_ADMIN_KEYS = {"devadmin", "admin", "password", "changeme", "test", "secret"}
if ADMIN_KEY and (len(ADMIN_KEY) < 16 or ADMIN_KEY.lower() in _WEAK_ADMIN_KEYS):
    print("[tranfu] WARNING: TF_ADMIN_KEY 偏弱(过短或为常见示例值),管理接口可被在线"
          "猜测;请用 `openssl rand -hex 32` 生成强随机值。", file=sys.stderr)

app = FastAPI(title="TRANFU//AGENTS")

# 锁定本源的 CSP:script 仅允许同源(挡掉注入的内联/外链脚本偷 sessionStorage
# 里的管理钥匙);connect 仅同源(挡外传);style/font/img 放行前端实际用到的
# Google Fonts 与品牌图床。前端无内联脚本(JSON-LD 数据块不受 script-src 管控)。
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' https://tranfu.com data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    if _req_is_https(request):
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp


app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets"), check_dir=False), name="assets")
_lock = threading.Lock()
_catalog_lock = threading.Lock()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default


TRASH_DAYS = _env_int("TF_TRASH_DAYS", 30)
ADMIN_MAX_ROWS = _env_int("TF_ADMIN_MAX_ROWS", 200)

# 反代场景:仅当声明前置可信反代时,才信任 X-Forwarded-For 提取真实客户端 IP。
# 默认关 —— XFF 可被请求方随意伪造,误信会让攻击者绕过按 IP 的限流。
TRUST_PROXY = os.environ.get("TF_TRUST_PROXY", "0") == "1"
# 管理接口防爆破限流(进程内,单 worker 前提;见 design.md「权衡」)。
ADMIN_RATE_MAX = _env_int("TF_ADMIN_RATE_MAX", 5)        # 窗口内允许的验钥失败次数
ADMIN_RATE_WINDOW = _env_int("TF_ADMIN_RATE_WINDOW", 60)  # 滑窗长度(秒)
ADMIN_LOCK_BASE = _env_int("TF_ADMIN_LOCK_BASE", 30)     # 首次封锁时长(秒),其后翻倍
ADMIN_LOCK_MAX = _env_int("TF_ADMIN_LOCK_MAX", 3600)     # 封锁时长封顶(秒)
_RATE_MAX_ENTRIES = 10000                                # 来源条目硬上限,防海量来源撑爆内存
# 生产 HTTPS 部署才发 HSTS:显式 TF_HSTS=1,或经可信反代识别到 https。
HSTS_FORCE = os.environ.get("TF_HSTS", "0") == "1"
CATALOG_URL = os.environ.get(
    "TF_SKILLS_CATALOG_URL",
    "https://github.com/tranfu-labs/tranfu-skills/releases/download/catalog/index.json",
)
CATALOG_TTL_SECONDS = _env_int("TF_SKILLS_CATALOG_TTL", 3600)
CATALOG_FETCH_TIMEOUT = _env_int("TF_SKILLS_CATALOG_TIMEOUT", 6)
CATALOG_COMPANY_TYPES = {"own", "meta"}
CATALOG_SOURCE_UNKNOWN = "非公司库"
_catalog_state = {"items": None, "fetched_at": None, "error": None, "last_attempt": None}
_catalog_thread_started = False


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


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


def _clip(s, n):
    """Truncate an over-long string for storage, marking the cut."""
    if isinstance(s, str) and len(s) > n:
        return s[:n] + "…[truncated]"
    return s


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # readers don't block the writer
    conn.execute("PRAGMA busy_timeout=4000")
    return conn


def init_db():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT, recv TEXT, day TEXT,          -- ts=client(display), recv=server(authoritative)
          v TEXT, operator TEXT, agent TEXT, runtime TEXT,
          session_id TEXT, parent_session_id TEXT, verified INTEGER DEFAULT 0,
          status TEXT, task TEXT, current_step TEXT,
          model TEXT, last_seen TEXT,
          input TEXT, output TEXT, meta TEXT, source TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ev_session ON events(operator, runtime, session_id, id);
        CREATE INDEX IF NOT EXISTS idx_ev_day ON events(day, operator, runtime);

        -- latest reported profile per agent identity (operator + agent_key + runtime)
        CREATE TABLE IF NOT EXISTS profiles (
          operator TEXT, ak TEXT, runtime TEXT,
          json TEXT, updated TEXT,
          PRIMARY KEY (operator, ak, runtime)
        );

        -- first time each skill name was seen (leverage: cumulative assets / new-this-week)
        CREATE TABLE IF NOT EXISTS skills_seen (
          name TEXT PRIMARY KEY, first_day TEXT
        );

        -- one row = one session × skill × semantic mode. "used" is the normal
        -- tool-boundary signal; "equipped" is OpenClaw prompt-injection presence.
        CREATE TABLE IF NOT EXISTS skill_uses (
          session_id TEXT NOT NULL,
          skill TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'used',
          operator TEXT,
          runtime TEXT,
          day TEXT,
          first_seen TEXT,
          PRIMARY KEY (session_id, skill, mode)
        );
        -- per-operator token bindings (TATP v0.1 §4). Stores sha256(token) only.
        CREATE TABLE IF NOT EXISTS operators (
          operator TEXT PRIMARY KEY, token_hash TEXT, created TEXT
        );

        -- operator identity: case/space-insensitive key -> first-seen display
        -- casing. Lets NEZHA / nezha / " NeZhA " resolve to ONE dispatcher.
        CREATE TABLE IF NOT EXISTS identities (
          norm TEXT PRIMARY KEY, display TEXT, created TEXT
        );

        -- cached tranfu-skills catalog for the SKILLS stats page. One row only.
        CREATE TABLE IF NOT EXISTS catalog_cache (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          json TEXT NOT NULL,
          fetched_at TEXT NOT NULL
        );

        -- destructive admin cleanup: hard-delete with reversible source-row
        -- snapshots plus append-only audit.
        CREATE TABLE IF NOT EXISTS admin_trash (
          batch_id TEXT PRIMARY KEY,
          created TEXT,
          actor TEXT,
          selector TEXT,
          payload TEXT,
          counts TEXT,
          restored INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS admin_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT,
          actor TEXT,
          action TEXT,
          selector TEXT,
          counts TEXT,
          batch_id TEXT
        );
        """)
        # tolerate upgrades from an older schema (add columns if missing)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
        for col, decl in (("recv", "TEXT"), ("v", "TEXT"),
                          ("parent_session_id", "TEXT"), ("verified", "INTEGER DEFAULT 0")):
            if col not in cols:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
        _ensure_skill_uses_schema(conn)

        # --- identity normalization migration (idempotent) ---
        # Merge case/space variants of operator (NEZHA/nezha) and lowercase
        # runtime (Hermes/hermes), so one human/agent = one Pod/card. Safe to
        # re-run: operators converge to first-seen display; lower() is stable.
        conn.execute("""INSERT OR IGNORE INTO identities(norm,display,created)
          SELECT lower(trim(operator)), trim(operator), MIN(COALESCE(recv,ts,''))
          FROM events WHERE trim(COALESCE(operator,'')) <> ''
          GROUP BY lower(trim(operator))""")
        conn.execute("""UPDATE events SET operator = COALESCE(
          (SELECT display FROM identities WHERE norm = lower(trim(events.operator))),
          operator)""")
        conn.execute("UPDATE events SET runtime = lower(trim(runtime)) WHERE runtime IS NOT NULL")
        # profiles PK is (operator,ak,runtime); canonicalizing can collide ->
        # rebuild keeping the latest 'updated' per canonical key.
        prof = conn.execute("SELECT operator,ak,runtime,json,updated FROM profiles").fetchall()
        if prof:
            best = {}
            for r in prof:
                row = conn.execute("SELECT display FROM identities WHERE norm=?",
                                   ((r["operator"] or "").strip().casefold(),)).fetchone()
                opd = row["display"] if row else r["operator"]
                k = (opd, r["ak"], (r["runtime"] or "").strip().lower())
                if k not in best or (r["updated"] or "") > (best[k]["updated"] or ""):
                    best[k] = {"json": r["json"], "updated": r["updated"]}
            conn.execute("DELETE FROM profiles")
            for (opd, ak, rt), v in best.items():
                conn.execute("INSERT INTO profiles(operator,ak,runtime,json,updated) VALUES(?,?,?,?,?)",
                             (opd, ak, rt, v["json"], v["updated"]))
        conn.commit()


def _ensure_skill_uses_schema(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_uses)")}
    if "mode" not in cols:
        conn.execute("ALTER TABLE skill_uses ADD COLUMN mode TEXT NOT NULL DEFAULT 'used'")
    info = conn.execute("PRAGMA table_info(skill_uses)").fetchall()
    pk = [r["name"] for r in sorted((r for r in info if r["pk"]), key=lambda r: r["pk"])]
    if pk != ["session_id", "skill", "mode"]:
        conn.execute("ALTER TABLE skill_uses RENAME TO skill_uses_old")
        conn.execute("""
        CREATE TABLE skill_uses (
          session_id TEXT NOT NULL,
          skill TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'used',
          operator TEXT,
          runtime TEXT,
          day TEXT,
          first_seen TEXT,
          PRIMARY KEY (session_id, skill, mode)
        )""")
        old_cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_uses_old)")}
        mode_expr = "CASE WHEN mode IN ('used','equipped') THEN mode ELSE 'used' END" if "mode" in old_cols else "'used'"
        conn.execute(f"""INSERT OR IGNORE INTO skill_uses
          (session_id,skill,mode,operator,runtime,day,first_seen)
          SELECT session_id,skill,{mode_expr},operator,runtime,day,first_seen
          FROM skill_uses_old""")
        conn.execute("DROP TABLE skill_uses_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_uses_skill ON skill_uses(skill)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_uses_skill_mode ON skill_uses(skill, mode)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_uses_day ON skill_uses(day)")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _key_eq(given, expected):
    """常量时间比较:避免按字符短路泄露 key 长度/前缀;编码成 bytes 兼容
    非 ASCII 输入,且不会因输入类型异常抛 500。"""
    return hmac.compare_digest((given or "").encode("utf-8"), (expected or "").encode("utf-8"))


def check_auth(key):
    if INGEST_KEY and not _key_eq(key, INGEST_KEY):
        raise HTTPException(status_code=401, detail="bad ingest key")


def _json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _client_host(request):
    """真实客户端 IP。反代后 request.client.host 恒为反代 IP,直接限流会
    『一人触发、全员被封』。仅在显式声明可信反代(TRUST_PROXY)时,才取
    X-Forwarded-For 的最右段(可信反代追加的那一跳);否则用连接对端 IP。"""
    try:
        if TRUST_PROXY:
            xff = request.headers.get("x-forwarded-for", "")
            if xff:
                parts = [p.strip() for p in xff.split(",") if p.strip()]
                if parts:
                    return parts[-1]
        return request.client.host or "unknown"
    except Exception:
        return "unknown"


def _req_is_https(request):
    if HSTS_FORCE:
        return True
    try:
        if TRUST_PROXY and request.headers.get("x-forwarded-proto", "").lower() == "https":
            return True
        return request.url.scheme == "https"
    except Exception:
        return False


# ------------------------------------------------------------ 防爆破限流(进程内)
# bucket(如 "admin" / "enroll")× 来源 IP 为键,做滑窗失败计数 + 指数退避封锁。
# 只碰内存与一把独立轻锁,不抢全局 DB 写锁、不引入 Redis(契合「无外部服务」)。
_rate_lock = threading.Lock()
_rate_state = {}   # (bucket, ip) -> {win_start, fails, audited, blocked_until, streak}


def _rate_prune(now):
    """惰性清理:超过硬上限时,丢弃既未封锁、窗口又已过期的陈旧条目。"""
    if len(_rate_state) <= _RATE_MAX_ENTRIES:
        return
    stale = [k for k, e in _rate_state.items()
             if e["blocked_until"] <= now and now - e["win_start"] >= ADMIN_RATE_WINDOW]
    for k in stale:
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
    now = time.time()
    with _rate_lock:
        e = _rate_state.get((bucket, ip))
        if e is None or now - e["win_start"] >= ADMIN_RATE_WINDOW:
            e = {"win_start": now, "fails": 0, "audited": False,
                 "blocked_until": e["blocked_until"] if e else 0.0,
                 "streak": e["streak"] if e else 0}
            _rate_state[(bucket, ip)] = e
        e["fails"] += 1
        should_audit = not e["audited"]
        e["audited"] = True
        retry_after = None
        if e["fails"] > ADMIN_RATE_MAX:
            lock = min(ADMIN_LOCK_BASE * (2 ** e["streak"]), ADMIN_LOCK_MAX)
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


def _audit(conn, actor, action, selector=None, counts=None, batch_id=None):
    conn.execute("""INSERT INTO admin_audit(ts,actor,action,selector,counts,batch_id)
      VALUES(?,?,?,?,?,?)""",
      (now_iso(), actor or "", action, _json(selector or {}), _json(counts or {}), batch_id))


def _audit_denied(request, key, selector=None):
    try:
        with _lock, closing(db()) as conn:
            _audit(conn, _admin_actor(key, request), "denied", selector or {}, {}, None)
            conn.commit()
    except Exception:
        pass


def check_admin(key, request, selector=None):
    ip = _client_host(request)
    actor = _admin_actor(key, request)
    # 1) 命中封锁窗口:直接 429,不验钥、不写审计(防爆破 + 写放大 DoS)
    retry = _rate_retry_after("admin", ip)
    if retry is not None:
        raise HTTPException(status_code=429, detail="too many attempts",
                            headers={"Retry-After": str(retry)})
    # 2) 常量时间比较(见 _key_eq)
    if not (bool(ADMIN_KEY) and _key_eq(key, ADMIN_KEY)):
        should_audit, retry = _rate_register_failure("admin", ip)
        if should_audit:                  # 每来源每窗口至多一条 denied 汇总(降噪)
            _audit_denied(request, key, selector)
        if retry is not None:             # 本次失败触发封锁 -> 429 + Retry-After
            raise HTTPException(status_code=429, detail="too many attempts",
                                headers={"Retry-After": str(retry)})
        raise HTTPException(status_code=403, detail="admin disabled or bad key")
    _rate_register_success("admin", ip)   # 验钥成功:清空该来源失败计数
    return actor


def canon_operator(conn, raw, when):
    """Resolve an operator string to its canonical display (first-seen casing),
    case/space-insensitively. 'NEZHA', ' nezha ' -> one identity = one Pod."""
    raw = (raw or "").strip()
    norm = raw.casefold()
    if not norm:
        return raw
    conn.execute("INSERT OR IGNORE INTO identities(norm,display,created) VALUES(?,?,?)",
                 (norm, raw, when))
    row = conn.execute("SELECT display FROM identities WHERE norm=?", (norm,)).fetchone()
    return row["display"] if row else raw


def verify_operator(conn, operator, token):
    """Per-operator attribution (§4). Returns True iff `token` is bound to
    `operator`. When TF_REQUIRE_TOKEN is on, a missing/mismatched token is a 403."""
    if not token:
        if REQUIRE_TOKEN:
            raise HTTPException(403, "X-TF-Token required (TF_REQUIRE_TOKEN on)")
        return False                                   # legacy: operator self-asserted
    row = conn.execute("SELECT operator FROM operators WHERE token_hash=?",
                       (_sha(token),)).fetchone()
    if not row or row["operator"] != operator:
        raise HTTPException(403, "token does not match operator")
    return True


def _skill_names(skills):
    """Flatten a skills object {local:[{name}],cross:[...]} (or list) to names."""
    out = []
    if isinstance(skills, dict):
        for grp in ("local", "cross"):
            for s in skills.get(grp) or []:
                out.append(s.get("name") if isinstance(s, dict) else s)
    elif isinstance(skills, list):
        for s in skills:
            out.append(s.get("name") if isinstance(s, dict) else s)
    return [n for n in out if n]


def _skill_use_name(value):
    """Normalize the optional event-level skill usage name."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value:
        return ""
    return value[:MAX_SKILL_NAME]


def _skill_mode(value):
    """Normalize event-level skill semantic mode; invalid values are legacy used."""
    if not isinstance(value, str):
        return "used"
    value = value.strip().lower()
    return value if value in SKILL_MODES else "used"


_SHIM_MANIFEST = _build_shim_manifest()


def _catalog_source(value):
    value = (value or "external").strip().lower() if isinstance(value, str) else "external"
    return value if value in ("own", "meta", "external") else "external"


def _parse_catalog_payload(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw) if isinstance(raw, str) else raw
    skills = data.get("skills") if isinstance(data, dict) else data
    if not isinstance(skills, list):
        raise ValueError("catalog skills must be a list")
    out, seen = [], set()
    for item in skills:
        if not isinstance(item, dict):
            continue
        name = _skill_use_name(item.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "type": _catalog_source(item.get("type")),
            "description": item.get("description") or "",
        })
    return {
        "version": data.get("version") if isinstance(data, dict) else None,
        "generated_at": data.get("generated_at") if isinstance(data, dict) else None,
        "skills": out,
    }


def _fetch_catalog():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "TRANFU-AGENTS/1.0"})
    with urllib.request.urlopen(req, timeout=CATALOG_FETCH_TIMEOUT) as resp:
        return _parse_catalog_payload(resp.read(768 * 1024))


def _save_catalog_cache(conn, catalog, fetched_at=None):
    fetched_at = fetched_at or now_iso()
    conn.execute("""INSERT INTO catalog_cache(id,json,fetched_at) VALUES(1,?,?)
      ON CONFLICT(id) DO UPDATE SET json=excluded.json,fetched_at=excluded.fetched_at""",
      (json.dumps(catalog, ensure_ascii=False), fetched_at))
    with _catalog_lock:
        _catalog_state.update({
            "items": catalog.get("skills") or [],
            "fetched_at": fetched_at,
            "error": None,
            "last_attempt": fetched_at,
        })


def _record_catalog_error(exc):
    msg = str(exc)[:240] if exc else "catalog fetch failed"
    with _catalog_lock:
        _catalog_state.update({"error": msg, "last_attempt": now_iso()})


def sync_catalog_once():
    """Fetch the catalog once. Failure is recorded but never raised."""
    try:
        catalog = _fetch_catalog()
    except Exception as exc:
        _record_catalog_error(exc)
        return False
    with _lock, closing(db()) as conn:
        _save_catalog_cache(conn, catalog)
        conn.commit()
    return True


def _catalog_loop():
    while True:
        sync_catalog_once()
        time.sleep(max(60, CATALOG_TTL_SECONDS))


def _start_catalog_sync():
    global _catalog_thread_started
    if os.environ.get("TF_SKILLS_CATALOG_SYNC", "1") == "0":
        return
    with _catalog_lock:
        if _catalog_thread_started:
            return
        _catalog_thread_started = True
    threading.Thread(target=_catalog_loop, name="tf-skills-catalog", daemon=True).start()


def _startup_catalog_sync():
    _start_catalog_sync()


app.add_event_handler("startup", _startup_catalog_sync)


def _load_catalog_cache(conn):
    with _catalog_lock:
        state = dict(_catalog_state)
    if state.get("items") is not None:
        items = state.get("items") or []
        return {
            "items": items,
            "fetched_at": state.get("fetched_at"),
            "stale": bool(state.get("error")),
            "available": bool(items),
            "error": state.get("error"),
            "last_attempt": state.get("last_attempt"),
        }
    row = conn.execute("SELECT json,fetched_at FROM catalog_cache WHERE id=1").fetchone()
    if not row:
        return {
            "items": [],
            "fetched_at": None,
            "stale": True,
            "available": False,
            "error": state.get("error"),
            "last_attempt": state.get("last_attempt"),
        }
    try:
        data = json.loads(row["json"])
        items = data.get("skills") or []
    except Exception as exc:
        items = []
        state["error"] = str(exc)[:240]
    return {
        "items": items,
        "fetched_at": row["fetched_at"],
        "stale": bool(state.get("error")),
        "available": bool(items),
        "error": state.get("error"),
        "last_attempt": state.get("last_attempt"),
    }


def _catalog_context(conn):
    cache = _load_catalog_cache(conn)
    by_name = {i["name"]: i["type"] for i in cache["items"] if i.get("name")}
    catalog = {
        "available": cache["available"],
        "fetched_at": cache["fetched_at"],
        "stale": cache["stale"],
        "error": cache["error"],
        "last_attempt": cache["last_attempt"],
        "count": len(cache["items"]),
    }
    return cache["items"], by_name, catalog


def _skill_source(name, catalog_by_name):
    return catalog_by_name.get(name) or CATALOG_SOURCE_UNKNOWN


def _installed_skill_names(conn):
    names = set()
    for r in conn.execute("SELECT json FROM profiles"):
        try:
            p = json.loads(r["json"])
        except Exception:
            continue
        for nm in _skill_names(p.get("skills")):
            clean = _skill_use_name(nm)
            if clean:
                names.add(clean)
    return names


def _catalog_list(names, catalog_by_name):
    return [{"name": n, "source": catalog_by_name[n]} for n in sorted(names)]


def _day_cutoff(days):
    return (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()


# ---------------------------------------------------------------- enroll (§4)
@app.post("/v1/enroll")
async def enroll(request: Request, x_tf_key: str = Header(default="")):
    """Admin issues a per-operator token. Guarded by the team write key.
    The plaintext token is returned ONCE; the server stores only its sha256."""
    # 签发持久 token 的写侧钥匙值得保护:与管理接口同类的按 IP 限流(独立 bucket)。
    ip = _client_host(request)
    retry = _rate_retry_after("enroll", ip)
    if retry is not None:
        raise HTTPException(status_code=429, detail="too many attempts",
                            headers={"Retry-After": str(retry)})
    try:
        check_auth(x_tf_key)
    except HTTPException:
        _, retry = _rate_register_failure("enroll", ip)
        if retry is not None:
            raise HTTPException(status_code=429, detail="too many attempts",
                                headers={"Retry-After": str(retry)})
        raise
    _rate_register_success("enroll", ip)
    body = await request.json()
    raw_op = (body.get("operator") or "").strip()
    if not raw_op:
        raise HTTPException(400, "operator required")
    token = "ttk_" + secrets.token_urlsafe(24)
    with _lock, closing(db()) as conn:
        operator = canon_operator(conn, raw_op, now_iso())   # bind token to canonical identity
        conn.execute("""INSERT INTO operators(operator,token_hash,created) VALUES(?,?,?)
          ON CONFLICT(operator) DO UPDATE SET token_hash=excluded.token_hash,created=excluded.created""",
          (operator, _sha(token), now_iso()))
        conn.commit()
    return {"operator": operator, "token": token,
            "note": "保存到 TF_TOKEN，仅此一次可见"}


# ---------------------------------------------------------------- ingest
@app.post("/v1/events")
async def ingest_event(request: Request, x_tf_key: str = Header(default=""),
                       x_tf_token: str = Header(default="")):
    check_auth(x_tf_key)
    # §8 reject oversized bodies before parsing
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, f"body exceeds {MAX_BODY} bytes")
    try:
        e = json.loads(raw)
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not all(e.get(k) for k in ("operator", "runtime", "status")):
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    skill_name = _skill_use_name(e.get("skill"))
    skill_mode = _skill_mode(e.get("skill_mode"))
    if not e.get("session_id"):
        if skill_name:
            return {"ok": True, "logged": False, "skill_ignored": True}
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    ts = e.get("ts") or now_iso()
    recv = now_iso()                               # server-authoritative time (§6)
    sid = e["session_id"]
    status, step = e["status"], e.get("current_step")

    # §5 read-side auth gate: drop sensitive fields unless read access is protected
    if not READ_AUTH_OK:
        for k in SENSITIVE_KEYS:
            e.pop(k, None)
    inp = _clip(e.get("input"), MAX_CONTENT)
    outp = _clip(e.get("output"), MAX_CONTENT)
    meta_json = _clip(json.dumps(e.get("meta"), ensure_ascii=False), MAX_META) if e.get("meta") else None

    with _lock, closing(db()) as conn:
        # normalize identity: operator case/space-insensitive, runtime lowercased
        op = canon_operator(conn, e["operator"], recv)
        rt = (e["runtime"] or "").strip().lower()
        ag = e.get("agent") or rt                      # agent identity label
        verified = 1 if verify_operator(conn, op, x_tf_token) else 0

        # Usage is processed before heartbeat dedup so a repeated tool step can
        # still record the first sighting of session×skill.
        if skill_name:
            conn.execute("""INSERT OR IGNORE INTO skill_uses
              (session_id,skill,mode,operator,runtime,day,first_seen) VALUES(?,?,?,?,?,?,?)""",
              (sid, skill_name, skill_mode, op, rt, recv[:10], recv))
            conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)",
                         (skill_name, recv[:10]))

        # OPTIONAL profile payload — full-snapshot replace per identity (§6)
        profile = {k: e[k] for k in PROFILE_KEYS if e.get(k) is not None}
        if profile:
            conn.execute("""INSERT INTO profiles(operator,ak,runtime,json,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET json=excluded.json,updated=excluded.updated""",
              (op, ag, rt, json.dumps(profile, ensure_ascii=False), recv))
            for nm in _skill_names(profile.get("skills")):
                conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)", (nm, recv[:10]))

        # dedup key now includes session_id (§6) so concurrent sessions of one
        # identity don't swallow each other's liveness.
        last = conn.execute("""SELECT id,status,current_step FROM events
            WHERE operator=? AND runtime=? AND COALESCE(agent,runtime)=? AND session_id=?
            ORDER BY id DESC LIMIT 1""", (op, rt, ag, sid)).fetchone()
        if last and last["status"] == status and (last["current_step"] or "") == (step or ""):
            # pure heartbeat: nothing changed -> only refresh liveness (server time)
            conn.execute("UPDATE events SET last_seen=? WHERE id=?", (recv, last["id"]))
            conn.commit()
            return {"ok": True, "heartbeat": True, "verified": bool(verified)}
        conn.execute("""INSERT INTO events
          (ts,recv,day,last_seen,v,operator,agent,runtime,session_id,parent_session_id,verified,
           status,task,current_step,model,input,output,meta,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (ts, recv, recv[:10], recv, e.get("v"), op, e.get("agent"), rt, sid,
           e.get("parent_session_id"), verified, status,
           e.get("task"), step, e.get("model"), inp, outp, meta_json, "heartbeat"))
        _maybe_prune(conn)
        conn.commit()
    return {"ok": True, "logged": True, "verified": bool(verified)}


# ---------------------------------------------------------------- destructive cleanup (admin)
def _rowdict(row):
    return {k: row[k] for k in row.keys()}


def _marks(items):
    return ",".join("?" for _ in items)


def _skill_key(row_or_key):
    if isinstance(row_or_key, tuple):
        return row_or_key
    return (row_or_key["session_id"], row_or_key["skill"], row_or_key["mode"] or "used")


def _skill_key_s(key):
    return "\x1f".join("" if v is None else str(v) for v in key)


def _profile_key(row_or_key):
    if isinstance(row_or_key, tuple):
        return row_or_key
    return (row_or_key["operator"], row_or_key["ak"], row_or_key["runtime"])


def _profile_key_s(key):
    return "\x1f".join("" if v is None else str(v) for v in key)


def _norm_op(value):
    return (value or "").strip().casefold()


def _validate_targets(targets):
    if not isinstance(targets, list) or not targets:
        raise HTTPException(400, "targets must be a non-empty array")
    out = []
    for target in targets:
        if not isinstance(target, dict):
            raise HTTPException(400, "each target must be an object")
        kinds = []
        if target.get("session_ids") is not None:
            kinds.append("session_ids")
        if target.get("skill") is not None:
            kinds.append("skill")
        if target.get("before_day") is not None:
            kinds.append("before_day")
        elif target.get("operator") is not None:
            kinds.append("operator")
        if len(kinds) != 1:
            raise HTTPException(400, "each target must select exactly one target kind")
        if target.get("session_ids") is not None:
            sids = target.get("session_ids")
            if isinstance(sids, str):
                sids = [sids]
            if not isinstance(sids, list) or not all(isinstance(s, str) and s for s in sids):
                raise HTTPException(400, "session_ids must be non-empty strings")
            clean = dict(target)
            clean["session_ids"] = sids
            out.append(clean)
            continue
        if target.get("before_day") is not None:
            if not isinstance(target.get("before_day"), str) or len(target["before_day"]) != 10:
                raise HTTPException(400, "before_day must be YYYY-MM-DD")
            if not target.get("operator"):
                raise HTTPException(400, "before_day requires operator")
        if target.get("operator") is not None and not isinstance(target.get("operator"), str):
            raise HTTPException(400, "operator must be a string")
        if target.get("skill") is not None:
            skill = _skill_use_name(target.get("skill"))
            if not skill:
                raise HTTPException(400, "skill must be a non-empty string")
            clean = dict(target)
            clean["skill"] = skill
            out.append(clean)
            continue
        out.append(dict(target))
    return out


def _event_ids_for_sessions(conn, session_ids, operator_norm=None):
    # operator_norm 非空时收口到该 operator 自身的行(共用 session 不误伤他人);
    # 为 None 时整删 session 全部行(供 session_ids 显式选择器用)。
    if not session_ids:
        return set()
    sql = f"SELECT id FROM events WHERE session_id IN ({_marks(session_ids)})"
    params = list(session_ids)
    if operator_norm is not None:
        sql += " AND lower(trim(COALESCE(operator,'')))=?"
        params.append(operator_norm)
    rows = conn.execute(sql, params).fetchall()
    return {int(r["id"]) for r in rows}


def _skill_keys_for_sessions(conn, session_ids, operator_norm=None):
    if not session_ids:
        return set()
    sql = f"SELECT session_id,skill,mode FROM skill_uses WHERE session_id IN ({_marks(session_ids)})"
    params = list(session_ids)
    if operator_norm is not None:
        sql += " AND lower(trim(COALESCE(operator,'')))=?"
        params.append(operator_norm)
    rows = conn.execute(sql, params).fetchall()
    return {_skill_key(r) for r in rows}


def _session_ids_by_operator(conn, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [norm]
    clauses = ["lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("COALESCE(agent,runtime)=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    event_rows = conn.execute(f"""SELECT DISTINCT session_id FROM events
      WHERE session_id IS NOT NULL AND {' AND '.join(clauses)}""", params).fetchall()
    sids = {r["session_id"] for r in event_rows if r["session_id"]}
    if not agent:
        sk_params = [norm]
        sk_clauses = ["lower(trim(COALESCE(operator,'')))=?"]
        if runtime:
            sk_clauses.append("lower(trim(COALESCE(runtime,'')))=?")
            sk_params.append((runtime or "").strip().lower())
        sk_rows = conn.execute(f"""SELECT DISTINCT session_id FROM skill_uses
          WHERE session_id IS NOT NULL AND {' AND '.join(sk_clauses)}""", sk_params).fetchall()
        sids.update(r["session_id"] for r in sk_rows if r["session_id"])
    return sids


def _session_ids_before_day(conn, before_day, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [before_day, norm]
    clauses = ["day < ?", "lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("COALESCE(agent,runtime)=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    rows = conn.execute(f"""SELECT DISTINCT session_id FROM events
      WHERE session_id IS NOT NULL AND {' AND '.join(clauses)}""", params).fetchall()
    sids = {r["session_id"] for r in rows if r["session_id"]}
    if not agent:
        sk_params = [before_day, norm]
        sk_clauses = ["day < ?", "lower(trim(COALESCE(operator,'')))=?"]
        if runtime:
            sk_clauses.append("lower(trim(COALESCE(runtime,'')))=?")
            sk_params.append((runtime or "").strip().lower())
        sk_rows = conn.execute(f"""SELECT DISTINCT session_id FROM skill_uses
          WHERE session_id IS NOT NULL AND {' AND '.join(sk_clauses)}""", sk_params).fetchall()
        sids.update(r["session_id"] for r in sk_rows if r["session_id"])
    return sids


def _skill_keys_for_skill(conn, skill):
    rows = conn.execute("""SELECT session_id,skill,mode FROM skill_uses
      WHERE skill=?""", (skill,)).fetchall()
    return {_skill_key(r) for r in rows}


def _profile_keys_for_selector(conn, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [norm]
    clauses = ["lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("ak=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    rows = conn.execute(f"""SELECT operator,ak,runtime FROM profiles
      WHERE {' AND '.join(clauses)}""", params).fetchall()
    return {_profile_key(r) for r in rows}


def _expand_child_sessions(conn, session_ids, operator_norm=None):
    # operator_norm 非空时后代会话只在同 operator 范围内扩展,不借后代把他人行卷入。
    all_sids = set(session_ids)
    frontier = set(session_ids)
    while frontier:
        sql = f"""SELECT DISTINCT session_id FROM events
          WHERE parent_session_id IN ({_marks(frontier)})
            AND session_id IS NOT NULL"""
        params = list(frontier)
        if operator_norm is not None:
            sql += " AND lower(trim(COALESCE(operator,'')))=?"
            params.append(operator_norm)
        rows = conn.execute(sql, params).fetchall()
        found = {r["session_id"] for r in rows if r["session_id"] and r["session_id"] not in all_sids}
        if not found:
            break
        all_sids.update(found)
        frontier = found
    return all_sids


def _fetch_event_rows(conn, event_ids):
    if not event_ids:
        return []
    return [_rowdict(r) for r in conn.execute(
        f"SELECT * FROM events WHERE id IN ({_marks(event_ids)}) ORDER BY id",
        list(event_ids)).fetchall()]


def _fetch_skill_rows(conn, skill_keys):
    rows = []
    for sid, skill, mode in sorted(skill_keys):
        row = conn.execute("""SELECT * FROM skill_uses
          WHERE session_id=? AND skill=? AND mode=?""", (sid, skill, mode)).fetchone()
        if row:
            rows.append(_rowdict(row))
    return rows


def _fetch_profile_rows(conn, profile_keys):
    rows = []
    for operator, ak, runtime in sorted(profile_keys):
        row = conn.execute("""SELECT * FROM profiles
          WHERE operator=? AND ak=? AND runtime=?""", (operator, ak, runtime)).fetchone()
        if row:
            rows.append(_rowdict(row))
    return rows


def _fetch_operator_rows(conn, operators):
    rows, seen = [], set()
    for norm in sorted(_candidate_operator_norms(operators)):
        for row in conn.execute("""SELECT * FROM operators
          WHERE lower(trim(operator))=? ORDER BY operator""", (norm,)):
            item = _rowdict(row)
            key = item.get("operator") or ""
            if key not in seen:
                seen.add(key)
                rows.append(item)
    return rows


def _resolution_token(resolved):
    payload = {
        "events": sorted(int(i) for i in resolved["event_ids"]),
        "skill_uses": sorted(_skill_key_s(k) for k in resolved["skill_keys"]),
        "profiles": sorted(_profile_key_s(k) for k in resolved["profile_keys"]),
        "operators": sorted(resolved.get("operator_keys") or []),
    }
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def _resolve_admin_targets(conn, targets, cascade_children=False, revoke=False):
    targets = _validate_targets(targets)
    # 逐 target 带各自 operator 约束解析后取并集:operator / before_day 路径收口到本人行;
    # 裸 session_ids 路径整删该 session(用户精确点选)。session_ids 仅用于活跃会话预警。
    session_ids, event_ids, skill_keys, profile_keys = set(), set(), set(), set()
    plain_session_ids = set()
    target_ops = set()
    for target in targets:
        if target.get("session_ids") is not None:
            plain_session_ids.update(target["session_ids"])
            continue
        if target.get("skill") is not None:
            skill_keys.update(_skill_keys_for_skill(conn, target["skill"]))
            continue
        operator = target.get("operator")
        agent = target.get("agent")
        runtime = target.get("runtime")
        if operator is not None:
            target_ops.add(operator)
        if target.get("before_day") is not None:
            sids = _session_ids_before_day(conn, target["before_day"], operator, agent, runtime)
        elif operator is not None:
            sids = _session_ids_by_operator(conn, operator, agent, runtime)
            if target.get("profile", True):
                profile_keys.update(_profile_keys_for_selector(conn, operator, agent, runtime))
        else:
            continue
        op_norm = _norm_op(operator)
        if cascade_children and sids:
            sids = _expand_child_sessions(conn, sids, op_norm)
        session_ids.update(sids)
        event_ids.update(_event_ids_for_sessions(conn, sids, op_norm))
        skill_keys.update(_skill_keys_for_sessions(conn, sids, op_norm))
    if plain_session_ids:
        if cascade_children:
            plain_session_ids = _expand_child_sessions(conn, plain_session_ids)
        session_ids.update(plain_session_ids)
        event_ids.update(_event_ids_for_sessions(conn, plain_session_ids))
        skill_keys.update(_skill_keys_for_sessions(conn, plain_session_ids))
    resolved = {
        "targets": targets,
        "session_ids": set(session_ids),
        "event_ids": event_ids,
        "skill_keys": skill_keys,
        "profile_keys": profile_keys,
        "target_operators": target_ops,
        "operator_keys": set(),
    }
    if revoke:
        event_rows = _fetch_event_rows(conn, event_ids)
        skill_rows = _fetch_skill_rows(conn, skill_keys)
        profile_rows = _fetch_profile_rows(conn, profile_keys)
        affected_ops = _operators_from_rows(event_rows, skill_rows, profile_rows) | set(target_ops)
        resolved["operator_keys"] = {r["operator"] for r in _fetch_operator_rows(conn, affected_ops)}
    resolved["preview_token"] = _resolution_token(resolved)
    return resolved


def _active_sessions(conn, session_ids):
    if not session_ids:
        return []
    rows = conn.execute(f"""
      SELECT e.* FROM events e
      JOIN (SELECT session_id, MAX(id) mid FROM events
            WHERE session_id IN ({_marks(session_ids)}) GROUP BY session_id) last
      ON e.id = last.mid
    """, list(session_ids)).fetchall()
    active = []
    for r in rows:
        if r["status"] in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) <= STALE_SECONDS:
            active.append({
                "session_id": r["session_id"],
                "operator": r["operator"],
                "runtime": r["runtime"],
                "agent": r["agent"],
                "status": r["status"],
                "last_seen": r["last_seen"] or r["recv"] or r["ts"],
            })
    active.sort(key=lambda x: (x["operator"] or "", x["session_id"] or ""))
    return active


def _active_sessions_all(conn):
    rows = conn.execute("""
      SELECT e.* FROM events e
      JOIN (SELECT session_id, MAX(id) mid FROM events
            WHERE session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id) last
      ON e.id = last.mid
    """).fetchall()
    active = []
    for r in rows:
        if r["status"] in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) <= STALE_SECONDS:
            active.append({
                "session_id": r["session_id"],
                "operator": r["operator"],
                "runtime": r["runtime"],
                "agent": r["agent"],
                "status": r["status"],
                "last_seen": r["last_seen"] or r["recv"] or r["ts"],
            })
    active.sort(key=lambda x: (x["operator"] or "", x["session_id"] or ""))
    return active


def _operators_from_rows(*row_lists):
    out = set()
    for rows in row_lists:
        for row in rows:
            op = (row.get("operator") or "").strip()
            if op:
                out.add(op)
    return out


def _candidate_operator_norms(operators):
    return {_norm_op(op) for op in operators if _norm_op(op)}


def _first_day_changes(conn, skill_keys):
    by_skill = {}
    delete_keys = set(skill_keys)
    for key in skill_keys:
        by_skill.setdefault(key[1], set()).add(key)
    changes = []
    for skill in sorted(by_skill):
        old_row = conn.execute("SELECT first_day FROM skills_seen WHERE name=?", (skill,)).fetchone()
        old_day = old_row["first_day"] if old_row else None
        new_day = None
        for row in conn.execute("SELECT session_id,skill,mode,day FROM skill_uses WHERE skill=?", (skill,)):
            if _skill_key(row) in delete_keys:
                continue
            day = row["day"]
            if day and (new_day is None or day < new_day):
                new_day = day
        if old_day != new_day:
            changes.append({"skill": skill, "from": old_day, "to": new_day})
    return changes


def _identity_clears(conn, event_ids, skill_keys, operators):
    event_ids = set(event_ids)
    skill_keys = set(skill_keys)
    cleared = []
    for norm in sorted(_candidate_operator_norms(operators)):
        identity = conn.execute("SELECT display FROM identities WHERE norm=?", (norm,)).fetchone()
        if not identity:
            continue
        remains = False
        for r in conn.execute("""SELECT id FROM events
          WHERE lower(trim(COALESCE(operator,'')))=?""", (norm,)):
            if int(r["id"]) not in event_ids:
                remains = True
                break
        if not remains:
            for r in conn.execute("""SELECT session_id,skill,mode FROM skill_uses
              WHERE lower(trim(COALESCE(operator,'')))=?""", (norm,)):
                if _skill_key(r) not in skill_keys:
                    remains = True
                    break
        if not remains:
            cleared.append(identity["display"])
    return cleared


def _preview_admin_resolution(conn, resolved, revoke=False):
    event_rows = _fetch_event_rows(conn, resolved["event_ids"])
    skill_rows = _fetch_skill_rows(conn, resolved["skill_keys"])
    profile_rows = _fetch_profile_rows(conn, resolved["profile_keys"])
    operator_rows = _fetch_operator_rows(conn, resolved.get("operator_keys") or []) if revoke else []
    affected_ops = (
        _operators_from_rows(event_rows, skill_rows, profile_rows, operator_rows)
        | set(resolved["target_operators"])
    )
    active = _active_sessions(conn, resolved["session_ids"] | {r["session_id"] for r in skill_rows if r.get("session_id")})
    counts = {
        "events": len(event_rows),
        "skill_uses": len(skill_rows),
        "profiles": len(profile_rows),
        "operators": len(operator_rows),
    }
    total_rows = counts["events"] + counts["skill_uses"] + counts["profiles"] + counts["operators"]
    operators = sorted(op for op in affected_ops if op)
    return {
        "ok": True,
        "preview_token": resolved["preview_token"],
        "counts": counts,
        "total_rows": total_rows,
        "operators": operators,
        "active_sessions": active,
        "requires_force": bool(active),
        "requires_confirm": total_rows > ADMIN_MAX_ROWS or len(operators) > 1,
        "max_rows": ADMIN_MAX_ROWS,
        "effects": {
            "first_day_changes": _first_day_changes(conn, resolved["skill_keys"]),
            "identities_cleared": _identity_clears(conn, resolved["event_ids"], resolved["skill_keys"], affected_ops),
            "profiles_cleared": [
                {"operator": r["operator"], "agent": r["ak"], "runtime": r["runtime"]}
                for r in profile_rows
            ],
        },
    }


def _recompute_derived(conn, skills, operators):
    for skill in sorted({s for s in skills if s}):
        row = conn.execute("""SELECT MIN(day) first_day FROM skill_uses
          WHERE skill=? AND day IS NOT NULL""", (skill,)).fetchone()
        first_day = row["first_day"] if row else None
        if first_day:
            conn.execute("""INSERT INTO skills_seen(name,first_day) VALUES(?,?)
              ON CONFLICT(name) DO UPDATE SET first_day=excluded.first_day""",
              (skill, first_day))
        else:
            conn.execute("DELETE FROM skills_seen WHERE name=?", (skill,))

    for norm in sorted(_candidate_operator_norms(operators)):
        candidates = []
        for r in conn.execute("""SELECT operator, MIN(COALESCE(recv,ts,'')) first_seen
          FROM events WHERE lower(trim(COALESCE(operator,'')))=?
          GROUP BY operator""", (norm,)):
            candidates.append((r["first_seen"] or "", r["operator"]))
        for r in conn.execute("""SELECT operator, MIN(COALESCE(first_seen,day,'')) first_seen
          FROM skill_uses WHERE lower(trim(COALESCE(operator,'')))=?
          GROUP BY operator""", (norm,)):
            candidates.append((r["first_seen"] or "", r["operator"]))
        candidates = [(ts, op) for ts, op in candidates if (op or "").strip()]
        if candidates:
            first_seen, display = sorted(candidates, key=lambda x: (x[0] or "9999", x[1] or ""))[0]
            conn.execute("""INSERT INTO identities(norm,display,created) VALUES(?,?,?)
              ON CONFLICT(norm) DO UPDATE SET display=excluded.display,created=excluded.created""",
              (norm, display, first_seen))
        else:
            conn.execute("DELETE FROM identities WHERE norm=?", (norm,))


def _delete_skill_rows(conn, skill_keys):
    deleted = 0
    for sid, skill, mode in sorted(skill_keys):
        deleted += conn.execute("""DELETE FROM skill_uses
          WHERE session_id=? AND skill=? AND mode=?""", (sid, skill, mode)).rowcount
    return deleted


def _delete_profile_rows(conn, profile_keys):
    deleted = 0
    for operator, ak, runtime in sorted(profile_keys):
        deleted += conn.execute("""DELETE FROM profiles
          WHERE operator=? AND ak=? AND runtime=?""", (operator, ak, runtime)).rowcount
    return deleted


def _purge(conn, resolved, actor, selector, revoke=False):
    event_rows = _fetch_event_rows(conn, resolved["event_ids"])
    skill_rows = _fetch_skill_rows(conn, resolved["skill_keys"])
    profile_rows = _fetch_profile_rows(conn, resolved["profile_keys"])
    operator_rows = _fetch_operator_rows(conn, resolved.get("operator_keys") or []) if revoke else []
    affected_skills = {r["skill"] for r in skill_rows if r.get("skill")}
    affected_ops = (
        _operators_from_rows(event_rows, skill_rows, profile_rows, operator_rows)
        | set(resolved["target_operators"])
    )
    batch_id = str(uuid.uuid4())
    counts = {
        "events": 0,
        "skill_uses": 0,
        "profiles": 0,
        "operators": 0,
    }
    if resolved["event_ids"]:
        counts["events"] = conn.execute(
            f"DELETE FROM events WHERE id IN ({_marks(resolved['event_ids'])})",
            list(resolved["event_ids"])).rowcount
    counts["skill_uses"] = _delete_skill_rows(conn, resolved["skill_keys"])
    counts["profiles"] = _delete_profile_rows(conn, resolved["profile_keys"])
    if revoke:
        for norm in _candidate_operator_norms(affected_ops):
            counts["operators"] += conn.execute(
                "DELETE FROM operators WHERE lower(trim(operator))=?", (norm,)).rowcount
    _recompute_derived(conn, affected_skills, affected_ops)
    payload = {
        "events": event_rows,
        "skill_uses": skill_rows,
        "profiles": profile_rows,
        "operators": operator_rows,
    }
    conn.execute("""INSERT INTO admin_trash(batch_id,created,actor,selector,payload,counts,restored)
      VALUES(?,?,?,?,?,?,0)""",
      (batch_id, now_iso(), actor, _json(selector), _json(payload), _json(counts)))
    _audit(conn, actor, "delete", selector, counts, batch_id)
    return {"ok": True, "batch_id": batch_id, "counts": counts, "deleted": counts["events"]}


def _insert_row(conn, table, row, omit=()):
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    data = {k: v for k, v in row.items() if k in existing and k not in omit}
    if not data:
        return 0
    cols = list(data.keys())
    sql = f"""INSERT OR IGNORE INTO {table}({','.join(cols)})
      VALUES ({','.join('?' for _ in cols)})"""
    return conn.execute(sql, [data[c] for c in cols]).rowcount


def _begin_admin_write(conn):
    conn.execute("BEGIN IMMEDIATE")


def _restore_admin_batch(conn, batch_id, actor):
    row = conn.execute("SELECT * FROM admin_trash WHERE batch_id=?", (batch_id,)).fetchone()
    if not row:
        raise HTTPException(404, "batch not found")
    if row["restored"]:
        raise HTTPException(409, "batch already restored")
    payload = json.loads(row["payload"] or "{}")
    report = {}
    affected_skills, affected_ops = set(), set()
    for table in ("events", "skill_uses", "profiles", "operators"):
        inserted = 0
        rows = payload.get(table) or []
        for item in rows:
            if table == "events":
                inserted += _insert_row(conn, table, item, omit=("id",))
            else:
                inserted += _insert_row(conn, table, item)
            if item.get("skill"):
                affected_skills.add(item["skill"])
            if item.get("operator"):
                affected_ops.add(item["operator"])
        report[table] = {"attempted": len(rows), "inserted": inserted, "skipped": len(rows) - inserted}
    _recompute_derived(conn, affected_skills, affected_ops)
    conn.execute("UPDATE admin_trash SET restored=1 WHERE batch_id=?", (batch_id,))
    _audit(conn, actor, "restore", {"batch_id": batch_id}, report, batch_id)
    return {"ok": True, "batch_id": batch_id, "restored": report}


def _maybe_prune_trash(conn):
    if TRASH_DAYS <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TRASH_DAYS)).isoformat()
    deleted = conn.execute("DELETE FROM admin_trash WHERE created < ?", (cutoff,)).rowcount
    if deleted:
        _audit(conn, "system", "purge_trash", {"cutoff": cutoff}, {"admin_trash": deleted}, None)
    return deleted


def _admin_inventory(conn, q="", limit=200, offset=0):
    needle = (q or "").strip().casefold()
    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))
    active_by_session = {r["session_id"]: r for r in _active_sessions_all(conn)}
    active_identity_keys = {
        (
            r.get("operator") or "",
            r.get("agent") or r.get("runtime") or "",
            r.get("runtime") or "",
        )
        for r in active_by_session.values()
    }
    active_operator_keys = {r.get("operator") or "" for r in active_by_session.values()}
    active_session_ids = set(active_by_session)
    active_skills = set()
    if active_session_ids:
        ordered_sids = sorted(active_session_ids)
        for r in conn.execute(
            f"SELECT DISTINCT skill FROM skill_uses WHERE session_id IN ({_marks(ordered_sids)})",
            ordered_sids,
        ):
            active_skills.add(r["skill"] or "")

    operators, identities, sessions, skill_rows = {}, {}, {}, {}

    def touch_operator(op):
        key = op or ""
        return operators.setdefault(key, {
            "kind": "operator", "operator": key, "name": key or "(empty)",
            "events": 0, "skill_uses": 0, "profiles": 0, "identities": 0,
            "last_seen": None, "active": False,
        })

    def update_last(item, ts):
        if ts and (not item.get("last_seen") or ts > item["last_seen"]):
            item["last_seen"] = ts

    event_ts = "COALESCE(NULLIF(last_seen,''),NULLIF(recv,''),NULLIF(ts,''),'')"
    skill_ts = "COALESCE(NULLIF(first_seen,''),NULLIF(day,''),'')"

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator, COUNT(*) events, MAX({event_ts}) last_seen
      FROM events GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["events"] += r["events"]
        update_last(item, r["last_seen"])
        if r["operator"] in active_operator_keys:
            item["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator, COUNT(*) skill_uses, MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["skill_uses"] += r["skill_uses"]
        update_last(item, r["last_seen"])
        if r["operator"] in active_operator_keys:
            item["active"] = True

    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator, COUNT(*) profiles, MAX(COALESCE(updated,'')) last_seen
      FROM profiles GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["profiles"] += r["profiles"]
        update_last(item, r["last_seen"])

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator,
             COALESCE(NULLIF(agent,''),NULLIF(runtime,''),'') agent,
             COALESCE(runtime,'') runtime,
             COUNT(*) events,
             MAX({event_ts}) last_seen
      FROM events
      GROUP BY COALESCE(operator,''), COALESCE(NULLIF(agent,''),NULLIF(runtime,''),''), COALESCE(runtime,'')
    """):
        ikey = (r["operator"], r["agent"], r["runtime"])
        ident = identities.setdefault(ikey, {
            "kind": "identity", "operator": ikey[0], "agent": ikey[1], "runtime": ikey[2],
            "name": f"{ikey[0] or '(empty)'} / {ikey[1] or ikey[2] or '(none)'}",
            "events": 0, "skill_uses": 0, "profiles": 0, "last_seen": None, "active": False,
        })
        ident["events"] += r["events"]
        update_last(ident, r["last_seen"])
        if ikey in active_identity_keys:
            ident["active"] = True

    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator,
             COALESCE(ak,'') agent,
             COALESCE(runtime,'') runtime,
             COUNT(*) profiles,
             MAX(COALESCE(updated,'')) last_seen
      FROM profiles
      GROUP BY COALESCE(operator,''), COALESCE(ak,''), COALESCE(runtime,'')
    """):
        ikey = (r["operator"], r["agent"], r["runtime"])
        ident = identities.setdefault(ikey, {
            "kind": "identity", "operator": ikey[0], "agent": ikey[1], "runtime": ikey[2],
            "name": f"{ikey[0] or '(empty)'} / {ikey[1] or ikey[2] or '(none)'}",
            "events": 0, "skill_uses": 0, "profiles": 0, "last_seen": None, "active": False,
        })
        ident["profiles"] += r["profiles"]
        update_last(ident, r["last_seen"])
        if ikey in active_identity_keys:
            ident["active"] = True

    for r in conn.execute(f"""
      SELECT stats.session_id, COALESCE(e.operator,'') operator,
             COALESCE(NULLIF(e.agent,''),NULLIF(e.runtime,''),'') agent,
             COALESCE(e.runtime,'') runtime,
             stats.events, stats.last_seen
      FROM (
        SELECT COALESCE(session_id,'') session_id, COUNT(*) events, MAX(id) mid, MAX({event_ts}) last_seen
        FROM events GROUP BY COALESCE(session_id,'')
      ) stats
      JOIN events e ON e.id = stats.mid
    """):
        sid = r["session_id"]
        sess = sessions.setdefault(sid, {
            "kind": "session", "session_id": sid, "operator": r["operator"],
            "agent": r["agent"], "runtime": r["runtime"], "name": sid,
            "events": 0, "skill_uses": 0, "last_seen": None, "active": False,
        })
        sess["events"] += r["events"]
        update_last(sess, r["last_seen"])
        if sid in active_by_session:
            sess["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(session_id,'') session_id, COALESCE(operator,'') operator,
             COALESCE(runtime,'') runtime, COUNT(*) skill_uses, MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(session_id,''), COALESCE(operator,''), COALESCE(runtime,'')
    """):
        sid = r["session_id"]
        sess = sessions.setdefault(sid, {
            "kind": "session", "session_id": sid, "operator": r["operator"],
            "agent": "", "runtime": r["runtime"], "name": sid,
            "events": 0, "skill_uses": 0, "last_seen": None, "active": False,
        })
        sess["skill_uses"] += r["skill_uses"]
        update_last(sess, r["last_seen"])
        if sid in active_by_session:
            sess["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(skill,'') skill,
             COUNT(*) skill_uses,
             SUM(CASE WHEN mode='equipped' THEN 0 ELSE 1 END) used,
             SUM(CASE WHEN mode='equipped' THEN 1 ELSE 0 END) equipped,
             COUNT(DISTINCT NULLIF(operator,'')) operators,
             MIN(NULLIF(day,'')) first_day,
             MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(skill,'')
    """):
        sk = r["skill"]
        item = skill_rows.setdefault(sk, {
            "kind": "skill", "skill": sk, "name": sk,
            "events": 0, "skill_uses": 0, "used": 0, "equipped": 0,
            "operators": 0, "first_day": None, "last_seen": None, "active": False,
        })
        item["skill_uses"] += r["skill_uses"]
        item["used"] += r["used"] or 0
        item["equipped"] += r["equipped"] or 0
        item["operators"] += r["operators"] or 0
        item["first_day"] = r["first_day"]
        update_last(item, r["last_seen"])
        if sk in active_skills:
            item["active"] = True

    for item in operators.values():
        item["identities"] = sum(1 for key in identities if key[0] == item["operator"])

    def filt(items):
        rows = list(items)
        if needle:
            rows = [r for r in rows if needle in _json(r).casefold()]
        rows.sort(key=lambda r: (not bool(r.get("active")), r.get("name") or ""))
        return rows[offset:offset + limit]

    return {
        "ok": True,
        "operators": filt(operators.values()),
        "identities": filt(identities.values()),
        "sessions": filt(sessions.values()),
        "skills": filt(skill_rows.values()),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/admin/inventory")
def admin_inventory(request: Request, q: str = "", limit: int = 200, offset: int = 0,
                    x_tf_admin_key: str = Header(default="")):
    check_admin(x_tf_admin_key, request, {"path": "/api/admin/inventory"})
    with _lock, closing(db()) as conn:
        _maybe_prune_trash(conn)
        data = _admin_inventory(conn, q, limit, offset)
        conn.commit()
        return JSONResponse(data)


@app.post("/api/admin/preview")
async def admin_preview(request: Request, x_tf_admin_key: str = Header(default="")):
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    targets = body.get("targets")
    with closing(db()) as conn:
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
    preview["actor"] = actor
    return JSONResponse(preview)


@app.delete("/api/admin/data")
async def admin_delete_data(request: Request, x_tf_admin_key: str = Header(default="")):
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    targets = body.get("targets")
    with _lock, closing(db()) as conn:
        _begin_admin_write(conn)
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        if body.get("preview_token") != resolved["preview_token"]:
            raise HTTPException(409, "preview_token mismatch; preview again")
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
        if preview["requires_force"] and not body.get("force"):
            _audit(conn, actor, "denied", body, {"reason": "active_sessions"}, None)
            conn.commit()
            raise HTTPException(400, "active sessions require force=true")
        if preview["requires_confirm"] and int(body.get("confirm_count") or -1) != preview["total_rows"]:
            _audit(conn, actor, "denied", body, {"reason": "confirm_count", "total_rows": preview["total_rows"]}, None)
            conn.commit()
            raise HTTPException(400, "confirm_count must match total_rows")
        result = _purge(conn, resolved, actor, body, bool(body.get("revoke")))
        _maybe_prune_trash(conn)
        conn.commit()
        return JSONResponse(result)


@app.get("/api/admin/trash")
def admin_trash(request: Request, x_tf_admin_key: str = Header(default="")):
    check_admin(x_tf_admin_key, request, {"path": "/api/admin/trash"})
    with _lock, closing(db()) as conn:
        _maybe_prune_trash(conn)
        rows = []
        for r in conn.execute("""SELECT batch_id,created,actor,selector,counts,restored
          FROM admin_trash ORDER BY created DESC LIMIT 200"""):
            item = _rowdict(r)
            for key in ("selector", "counts"):
                try:
                    item[key] = json.loads(item[key] or "{}")
                except Exception:
                    item[key] = {}
            item["restored"] = bool(item["restored"])
            rows.append(item)
        conn.commit()
        return JSONResponse({"ok": True, "trash": rows})


@app.post("/api/admin/restore")
async def admin_restore(request: Request, x_tf_admin_key: str = Header(default="")):
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    batch_id = body.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise HTTPException(400, "batch_id required")
    with _lock, closing(db()) as conn:
        _begin_admin_write(conn)
        result = _restore_admin_batch(conn, batch_id, actor)
        _maybe_prune_trash(conn)
        conn.commit()
        return JSONResponse(result)


@app.post("/api/admin/export")
async def admin_export(background_tasks: BackgroundTasks, request: Request,
                       x_tf_admin_key: str = Header(default="")):
    """Download a consistent SQLite snapshot of the whole DB.

    This is the single most damaging consequence of an admin-key leak: one call
    walks off with the ENTIRE database, including the protocol §5 sensitive
    fields (instructions/memory/input/output), irreversibly. So it is the most
    guarded: a POST (never a prefetchable/cacheable GET), behind the same rate
    limiter as every other admin route, requiring an explicit `confirm=EXPORT`,
    and audited as a high-risk action.

    Copying tf.db directly is unsafe in WAL mode: the live -wal file may hold
    committed-but-not-checkpointed pages, so a raw file copy can be torn or
    stale. `VACUUM INTO` writes a single self-contained snapshot under the
    writer lock, which we then stream and delete after the response is sent.
    """
    actor = check_admin(x_tf_admin_key, request, {"path": "/api/admin/export"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not (isinstance(body, dict) and body.get("confirm") == "EXPORT"):
        raise HTTPException(400, "whole-DB export requires confirm=EXPORT")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snap_path = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)) or ".",
                             f".tf-export-{stamp}-{uuid.uuid4().hex[:8]}.db")
    with _lock, closing(db()) as conn:
        conn.execute("VACUUM INTO ?", (snap_path,))
        _audit(conn, actor, "export", {"path": "/api/admin/export", "risk": "high"},
               {"snapshot": stamp, "high_risk": True}, None)
        conn.commit()
    background_tasks.add_task(lambda p: os.path.exists(p) and os.remove(p), snap_path)
    return FileResponse(snap_path, media_type="application/x-sqlite3",
                        filename=f"tf-{stamp}.db")


@app.delete("/v1/events")
async def delete_events(request: Request, x_tf_admin_key: str = Header(default="")):
    """Legacy cleanup kept for curl compatibility — DEPRECATED, prefer
    /api/admin/data. It used to bypass every cleanup guardrail; it now enforces
    the same ones that don't need a prior preview round-trip: active sessions
    require force=true, and deletions over TF_ADMIN_MAX_ROWS (or spanning >1
    operator) require confirm_count matching total_rows. The preview_token step
    is intentionally NOT required so a one-shot curl can: delete -> read the
    rejected total_rows -> delete again with confirm_count."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    actor = check_admin(x_tf_admin_key, request, {"legacy": True, **body})
    sids = list(body.get("session_ids") or [])
    if isinstance(body.get("session_id"), str):
        sids.append(body["session_id"])
    operator = body.get("operator")
    if not sids and not operator:
        raise HTTPException(400, "need session_ids or operator")
    if sids and not all(isinstance(s, str) for s in sids):
        raise HTTPException(400, "session_ids must be strings")
    if sids:
        targets = [{"session_ids": sids}]
        by = "session_ids"
    else:
        targets = [{
            "operator": operator,
            "agent": body.get("agent"),
            "runtime": body.get("runtime"),
            "profile": bool(body.get("profile")),
        }]
        by = "identity"
    selector = {"legacy": True, **body, "targets": targets}
    with _lock, closing(db()) as conn:
        _begin_admin_write(conn)
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
        if preview["requires_force"] and not body.get("force"):
            _audit(conn, actor, "denied", selector, {"reason": "active_sessions"}, None)
            conn.commit()
            raise HTTPException(400, "active sessions require force=true")
        if preview["requires_confirm"] and int(body.get("confirm_count") or -1) != preview["total_rows"]:
            _audit(conn, actor, "denied", selector, {"reason": "confirm_count", "total_rows": preview["total_rows"]}, None)
            conn.commit()
            raise HTTPException(400, f"confirm_count must match total_rows ({preview['total_rows']})")
        result = _purge(conn, resolved, actor, selector, bool(body.get("revoke")))
        conn.commit()
        return {"ok": True, "deleted": result["counts"]["events"],
                "cleared_profile": result["counts"]["profiles"], "by": by,
                "counts": result["counts"], "batch_id": result["batch_id"]}


_prune_state = {"n": 0}


def _maybe_prune(conn):
    """Retention (§6): every ~200 inserts, drop events older than the window."""
    _prune_state["n"] += 1
    if _prune_state["n"] % 200 != 1:
        return
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    deleted = conn.execute("DELETE FROM events WHERE day < ?", (cutoff,)).rowcount
    if deleted:
        _audit(conn, "system", "retention_prune", {"cutoff": cutoff}, {"events": deleted}, None)


# ---------------------------------------------------------------- read helpers
CLOUD_RUNTIMES = {"manus", "mulerun", "chatgpt"}
STALE_SECONDS = 180                                # = 3 heartbeat periods (§1)
# §1: blocked is a LIVE status — it still occupies a run, so it counts as active
# time and does not flip to idle. quality also surfaces a separate blocked count.
ACTIVE_ST = ("running", "started", "waiting", "blocked")
LIVE_ST = ACTIVE_ST


def _age(ts):
    try:
        return time.time() - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 1e9


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iter_sessions(conn):
    """Yield (key, session_id, [rows]) grouped by identity+session over the window."""
    win_start = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    # use server-authoritative recv time (fall back to ts/last_seen for legacy rows)
    rows = conn.execute("""SELECT operator, COALESCE(agent,runtime) k, runtime, session_id, status,
        COALESCE(recv, ts) rt_time, COALESCE(last_seen, recv, ts) ls FROM events WHERE day >= ?
        ORDER BY operator, k, session_id, id""", (win_start,)).fetchall()
    cur, buf = None, []
    for r in rows:
        sk = (r["operator"], r["k"], r["session_id"])
        if sk != cur:
            if buf:
                yield (buf[0]["operator"] + "\x00" + (buf[0]["k"] or ""), cur[2], buf)
            cur, buf = sk, []
        buf.append(r)
    if buf:
        yield (buf[0]["operator"] + "\x00" + (buf[0]["k"] or ""), cur[2], buf)


def metrics(conn):
    """Per identity: day-bucketed active time (today/week/series7/series90) AND
    quality (runs/done/error/avg_sec/auto_rate). One pass over the window."""
    now = datetime.now(timezone.utc)
    today = now.date()
    buckets = {}   # key -> {dayiso: seconds}
    qual = {}      # key -> {runs,done,error,active,auto}

    def add(key, a, b):
        if b <= a:
            return
        d = buckets.setdefault(key, {})
        cur = a
        while cur < b:
            day = cur.date()
            day_end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
            seg = min(b, day_end)
            d[day.isoformat()] = d.get(day.isoformat(), 0) + (seg - cur).total_seconds()
            cur = seg

    for key, _sid, rows in _iter_sessions(conn):
        q = qual.setdefault(key, {"runs": 0, "done": 0, "error": 0, "blocked": 0, "active": 0.0, "auto": 0})
        active_start = last_ls = None
        saw_wait = False
        sess_active = 0.0
        for r in rows:
            t = _parse(r["rt_time"]); last_ls = _parse(r["ls"]); st = r["status"]
            if st in ACTIVE_ST:                       # running/started/waiting/blocked
                if st == "waiting":
                    saw_wait = True
                elif st == "blocked":
                    q["blocked"] += 1
                if active_start is None:
                    active_start = t
            elif st in ("done", "error", "idle"):
                if active_start is not None:
                    add(key, active_start, t); sess_active += (t - active_start).total_seconds(); active_start = None
                if st in ("done", "error"):
                    q["runs"] += 1
                    q[("done" if st == "done" else "error")] += 1
                    if st == "done" and not saw_wait:
                        q["auto"] += 1
        if active_start is not None:   # still running -> count up to last_seen
            add(key, active_start, last_ls); sess_active += (last_ls - active_start).total_seconds()
        q["active"] += sess_active

    week_start = (today - timedelta(days=today.weekday())).isoformat()
    days7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    days90 = [(today - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS - 1, -1, -1)]
    dur = {}
    for key, d in buckets.items():
        dur[key] = {
            "today": round(d.get(today.isoformat(), 0)),
            "week": round(sum(v for day, v in d.items() if day >= week_start)),
            "series": [round(d.get(day, 0)) for day in days7],
            "series90": [round(d.get(day, 0)) for day in days90],
        }
    qout = {}
    for key, q in qual.items():
        runs = q["runs"]
        qout[key] = {
            "runs": runs, "success": q["done"], "error": q["error"], "blocked": q["blocked"],
            "avg_sec": round(q["active"] / runs) if runs else None,
            "auto_rate": round(q["auto"] / runs, 3) if runs else None,
        }
    return dur, qout


def load_profiles(conn):
    out = {}
    for r in conn.execute("SELECT operator,ak,runtime,json FROM profiles"):
        try:
            out[r["operator"] + "\x00" + r["ak"]] = json.loads(r["json"])
        except Exception:
            pass
    return out


def reuse_map(profiles):
    """skill name -> set(operators) ; then per identity, fraction of its skills
    that also appear in another operator's profile (cross-Pod reuse signal)."""
    owners = {}
    for key, p in profiles.items():
        op = key.split("\x00", 1)[0]
        for nm in _skill_names(p.get("skills")):
            owners.setdefault(nm, set()).add(op)
    out = {}
    for key, p in profiles.items():
        op = key.split("\x00", 1)[0]
        names = _skill_names(p.get("skills"))
        if not names:
            continue
        shared = sum(1 for nm in names if len(owners.get(nm, set()) - {op}) > 0)
        out[key] = round(shared / len(names), 3)
    return out


def leverage(conn):
    today = datetime.now(timezone.utc).date()
    wk = (today - timedelta(days=7)).isoformat()
    assets = conn.execute("SELECT COUNT(*) c FROM skills_seen").fetchone()["c"]
    week = conn.execute("SELECT COUNT(*) c FROM skills_seen WHERE first_day >= ?", (wk,)).fetchone()["c"]
    return {"assets": assets, "skills_week": week}


def skill_usage(conn):
    today = datetime.now(timezone.utc).date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    rows = conn.execute("""
      SELECT skill, mode,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      GROUP BY skill, mode
      ORDER BY sessions_30d DESC, sessions_total DESC, skill ASC, mode ASC
    """, (d7, d30, d30)).fetchall()
    return [{
        "name": r["skill"],
        "mode": r["mode"] or "used",
        "sessions_7d": int(r["sessions_7d"] or 0),
        "sessions_30d": int(r["sessions_30d"] or 0),
        "sessions_total": int(r["sessions_total"] or 0),
        "users_30d": int(r["users_30d"] or 0),
        "last_day": r["last_day"],
    } for r in rows]


def skills_overview(conn, days):
    if days not in (7, 30, 90):
        raise HTTPException(400, "days must be one of 7, 30, 90")
    today = datetime.now(timezone.utc).date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    d14 = (today - timedelta(days=13)).isoformat()
    daily_start = _day_cutoff(days)
    _items, catalog_by, catalog_meta = _catalog_context(conn)

    daily_where, daily_params = ["mode='used'", "day IS NOT NULL"], []
    if daily_start:
        daily_where.append("day >= ?")
        daily_params.append(daily_start)
    daily_rows = conn.execute(f"""
      SELECT day, skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE {' AND '.join(daily_where)}
      GROUP BY day, skill, runtime
      ORDER BY day ASC, skill ASC, runtime ASC
    """, daily_params).fetchall()
    daily = [{
        "day": r["day"],
        "skill": r["skill"],
        "runtime": r["runtime"] or "unknown",
        "sessions": int(r["sessions"] or 0),
        "source": _skill_source(r["skill"], catalog_by),
    } for r in daily_rows]

    operator_daily_where = ["mode='used'", "day IS NOT NULL", "trim(COALESCE(operator,'')) <> ''"]
    operator_daily_params = []
    if daily_start:
        operator_daily_where.append("day >= ?")
        operator_daily_params.append(daily_start)
    operator_daily_rows = conn.execute(f"""
      SELECT day, operator, COALESCE(runtime,'') runtime, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE {' AND '.join(operator_daily_where)}
      GROUP BY day, operator, runtime, skill
      ORDER BY day ASC, operator ASC, runtime ASC, skill ASC
    """, operator_daily_params).fetchall()
    operator_daily = [{
        "day": r["day"],
        "operator": r["operator"],
        "runtime": r["runtime"] or "unknown",
        "source": _skill_source(r["skill"], catalog_by),
        "sessions": int(r["sessions"] or 0),
    } for r in operator_daily_rows]

    base_rows = conn.execute("""
      SELECT skill,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill
    """, (d7, d30, d30)).fetchall()
    runtime_counts = {}
    for r in conn.execute("""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill, runtime
    """):
        runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    trend_days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    trend = {}
    for r in conn.execute("""
      SELECT skill, day, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ?
      GROUP BY skill, day
    """, (d14,)):
        trend.setdefault(r["skill"], {})[r["day"]] = int(r["sessions"] or 0)
    table = []
    for r in base_rows:
        skill = r["skill"]
        table.append({
            "name": skill,
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "users_30d": int(r["users_30d"] or 0),
            "runtime_counts": runtime_counts.get(skill, {}),
            "trend_14d": [trend.get(skill, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        })
    table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["name"]))

    operator_rows = conn.execute("""
      SELECT operator,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT skill) skill_count,
        COUNT(DISTINCT session_id) session_count,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator
    """, (d7, d30)).fetchall()
    operator_runtime_counts = {}
    for r in conn.execute("""
      SELECT operator, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, runtime
    """):
        operator_runtime_counts.setdefault(r["operator"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    operator_source_counts = {}
    for r in conn.execute("""
      SELECT operator, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, skill
    """):
        source = _skill_source(r["skill"], catalog_by)
        counts = operator_source_counts.setdefault(r["operator"], {})
        counts[source] = counts.get(source, 0) + int(r["sessions"] or 0)
    operator_trend = {}
    for r in conn.execute("""
      SELECT operator, day, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, day
    """, (d14,)):
        operator_trend.setdefault(r["operator"], {})[r["day"]] = int(r["sessions"] or 0)
    operator_table = []
    for r in operator_rows:
        operator = r["operator"]
        operator_table.append({
            "operator": operator,
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "skill_count": int(r["skill_count"] or 0),
            "session_count": int(r["session_count"] or 0),
            "runtime_counts": operator_runtime_counts.get(operator, {}),
            "source_counts": operator_source_counts.get(operator, {}),
            "trend_14d": [operator_trend.get(operator, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        })
    operator_table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["operator"]))

    company_names = {n for n, src in catalog_by.items() if src in CATALOG_COMPANY_TYPES}
    installed_names = _installed_skill_names(conn) & company_names
    used_30d_names = {r["skill"] for r in conn.execute("""
      SELECT DISTINCT skill FROM skill_uses
      WHERE mode='used' AND day >= ?
    """, (d30,)) if r["skill"] in company_names}
    funnel = {
        "available": bool(company_names),
        "catalog": _catalog_list(company_names, catalog_by),
        "installed": _catalog_list(installed_names, catalog_by),
        "used_30d": _catalog_list(used_30d_names, catalog_by),
        "idle": _catalog_list(installed_names - used_30d_names, catalog_by),
    }
    return {
        "days": days,
        "today": today.isoformat(),
        "daily": daily,
        "table": table,
        "operator_daily": operator_daily,
        "operator_table": operator_table,
        "funnel": funnel,
        "catalog": catalog_meta,
    }


def operator_detail_payload(conn, name):
    operator = (name or "").strip()
    if not operator:
        raise HTTPException(404, "operator not found")
    row = conn.execute("SELECT display FROM identities WHERE norm=?", (operator.casefold(),)).fetchone()
    if row:
        operator = row["display"]
    exists = conn.execute("""
      SELECT COUNT(*) c FROM skill_uses
      WHERE operator=? AND mode='used' AND trim(COALESCE(operator,'')) <> ''
    """, (operator,)).fetchone()["c"]
    if not exists:
        raise HTTPException(404, "operator not found")
    today = datetime.now(timezone.utc).date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    _items, catalog_by, catalog_meta = _catalog_context(conn)
    m = conn.execute("""
      SELECT
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT skill) skill_count,
        COUNT(DISTINCT session_id) session_count,
        MIN(day) first_day,
        MAX(day) last_day
      FROM skill_uses
      WHERE operator=? AND mode='used'
    """, (d7, d30, operator)).fetchone()
    daily = [dict(r) for r in conn.execute("""
      SELECT day, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used' AND day IS NOT NULL
      GROUP BY day, skill
      ORDER BY day ASC, skill ASC
    """, (operator,))]
    skill_runtime_counts = {}
    for r in conn.execute("""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY skill, runtime
    """, (operator,)):
        skill_runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    skill_rows = conn.execute("""
      SELECT skill,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        MAX(day) last_day
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY skill
    """, (d7, d30, operator)).fetchall()
    skill_table = []
    for r in skill_rows:
        skill = r["skill"]
        skill_table.append({
            "name": skill,
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "runtime_counts": skill_runtime_counts.get(skill, {}),
            "last_day": r["last_day"],
        })
    skill_table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["name"]))
    runtime = [{
        "runtime": r["runtime"] or "unknown",
        "used": int(r["sessions"] or 0),
    } for r in conn.execute("""
      SELECT COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY runtime
      ORDER BY sessions DESC, runtime ASC
    """, (operator,))]
    records = [dict(r) for r in conn.execute("""
      SELECT day, skill, runtime, session_id, first_seen
      FROM skill_uses
      WHERE operator=? AND mode='used'
      ORDER BY COALESCE(first_seen, day) DESC
      LIMIT 50
    """, (operator,))]
    return {
        "operator": operator,
        "today": today.isoformat(),
        "metrics": {
            "sessions_7d": int(m["sessions_7d"] or 0),
            "sessions_30d": int(m["sessions_30d"] or 0),
            "sessions_total": int(m["sessions_total"] or 0),
            "skill_count": int(m["skill_count"] or 0),
            "session_count": int(m["session_count"] or 0),
            "first_day": m["first_day"],
            "last_day": m["last_day"],
        },
        "daily": daily,
        "skills": skill_table,
        "runtime": runtime,
        "records": records,
        "catalog": catalog_meta,
    }


def skill_detail_payload(conn, name):
    name = _skill_use_name(name)
    if not name:
        raise HTTPException(404, "skill not found")
    exists = conn.execute("SELECT COUNT(*) c FROM skill_uses WHERE skill=?", (name,)).fetchone()["c"]
    if not exists:
        raise HTTPException(404, "skill not found")
    today = datetime.now(timezone.utc).date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    _items, catalog_by, catalog_meta = _catalog_context(conn)
    m = conn.execute("""
      SELECT
        SUM(CASE WHEN mode='used' AND day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN mode='used' AND day >= ? THEN 1 ELSE 0 END) sessions_30d,
        SUM(CASE WHEN mode='used' THEN 1 ELSE 0 END) sessions_total,
        COUNT(DISTINCT CASE WHEN mode='used' AND day >= ? THEN operator END) users_30d,
        MIN(CASE WHEN mode='used' THEN day END) first_day,
        MAX(CASE WHEN mode='used' THEN day END) last_day,
        SUM(CASE WHEN mode='equipped' AND day >= ? THEN 1 ELSE 0 END) equipped_7d,
        SUM(CASE WHEN mode='equipped' AND day >= ? THEN 1 ELSE 0 END) equipped_30d,
        SUM(CASE WHEN mode='equipped' THEN 1 ELSE 0 END) equipped_total,
        COUNT(DISTINCT CASE WHEN mode='equipped' AND day >= ? THEN operator END) equipped_users_30d
      FROM skill_uses
      WHERE skill=?
    """, (d7, d30, d30, d7, d30, d30, name)).fetchone()
    daily_map = {}
    for r in conn.execute("""
      SELECT day, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=? AND day IS NOT NULL
      GROUP BY day, mode
      ORDER BY day ASC
    """, (name,)):
        day = daily_map.setdefault(r["day"], {"day": r["day"], "used": 0, "equipped": 0})
        day[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    runtime_map = {}
    for r in conn.execute("""
      SELECT COALESCE(runtime,'') runtime, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=?
      GROUP BY runtime, mode
    """, (name,)):
        item = runtime_map.setdefault(r["runtime"] or "unknown", {"runtime": r["runtime"] or "unknown", "used": 0, "equipped": 0})
        item[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    operator_map = {}
    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=?
      GROUP BY operator, mode
    """, (name,)):
        item = operator_map.setdefault(r["operator"] or "unknown", {"operator": r["operator"] or "unknown", "used": 0, "equipped": 0})
        item[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    records = [dict(r) for r in conn.execute("""
      SELECT day, operator, runtime, mode, session_id, first_seen
      FROM skill_uses
      WHERE skill=?
      ORDER BY COALESCE(first_seen, day) DESC
      LIMIT 50
    """, (name,))]
    return {
        "name": name,
        "today": today.isoformat(),
        "source": _skill_source(name, catalog_by),
        "metrics": {
            "sessions_7d": int(m["sessions_7d"] or 0),
            "sessions_30d": int(m["sessions_30d"] or 0),
            "sessions_total": int(m["sessions_total"] or 0),
            "users_30d": int(m["users_30d"] or 0),
            "first_day": m["first_day"],
            "last_day": m["last_day"],
            "equipped_7d": int(m["equipped_7d"] or 0),
            "equipped_30d": int(m["equipped_30d"] or 0),
            "equipped_total": int(m["equipped_total"] or 0),
            "equipped_users_30d": int(m["equipped_users_30d"] or 0),
        },
        "daily": list(daily_map.values()),
        "runtime": sorted(runtime_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["runtime"])),
        "operators": sorted(operator_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["operator"])),
        "records": records,
        "catalog": catalog_meta,
    }


# ---------------------------------------------------------------- read: snapshot
def _snapshot(conn):
    sessions = conn.execute("""
      SELECT e.* FROM events e
      JOIN (SELECT operator,runtime,COALESCE(agent,runtime) ag,MAX(id) mid FROM events
            WHERE source='heartbeat' GROUP BY operator,runtime,ag) last
      ON e.id = last.mid ORDER BY e.operator ASC, e.id DESC LIMIT 200""").fetchall()
    feed = conn.execute("""SELECT * FROM events WHERE source='heartbeat'
      ORDER BY id DESC LIMIT 40""").fetchall()
    dur, qual = metrics(conn)
    profiles = load_profiles(conn)
    reuse = reuse_map(profiles)

    def card(r):
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
        d["fidelity"] = "coarse" if r["runtime"] in CLOUD_RUNTIMES else "full"
        ak = (r["agent"] if "agent" in r.keys() else None) or r["runtime"] or ""
        key = r["operator"] + "\x00" + ak
        dd = dur.get(key, {"today": 0, "week": 0, "series": [0] * 7, "series90": [0] * WINDOW_DAYS})
        d["today_active"], d["week_active"], d["active_series"] = dd["today"], dd["week"], dd["series"]
        d["active_days"] = dd["series90"]
        # merged profile (optional, reported by shim)
        p = profiles.get(key, {})
        for k in PROFILE_KEYS:
            if k in p:
                d[k] = p[k]
        # quality: computed + reuse, allow profile to add hints it can't compute
        q = dict(qual.get(key, {}))
        if key in reuse:
            q["reuse"] = reuse[key]
        if q:
            d["quality"] = q
        d["verified"] = bool(d.get("verified"))
        st = r["status"]
        if st in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) > STALE_SECONDS:
            st = "idle"
        d["status"] = st
        for big in ("input", "output"):
            if d.get(big) and len(d[big]) > 4000:
                d[big] = d[big][:4000] + "…[truncated]"
        return d

    cards = [card(r) for r in sessions]
    # collapse to ONE card per identity (operator + agent||runtime): keep the most
    # recently active session, so the same agent over many runs/sessions = one card.
    _best = {}
    for c in cards:
        k = (c["operator"], c.get("agent") or c.get("runtime") or "")
        tcur = c.get("last_seen") or c.get("ts") or ""
        prev = _best.get(k)
        if prev is None or tcur > (prev.get("last_seen") or prev.get("ts") or ""):
            _best[k] = c
    cards = list(_best.values())
    live = [c for c in cards if c["status"] in LIVE_ST]
    ops = {c["operator"] for c in cards}
    agents = {(c["operator"], (c.get("agent") or c["runtime"])) for c in cards}
    return {
        "now": now_iso(),
        "sessions": cards,
        "feed": [{"operator": r["operator"], "agent": r["agent"], "runtime": r["runtime"],
                  "status": r["status"], "current_step": r["current_step"],
                  "task": r["task"], "ts": r["ts"]} for r in feed],
        "leverage": leverage(conn),
        "skills": skill_usage(conn),
        "shim": {"version": _SHIM_MANIFEST["version"], "files": len(_SHIM_MANIFEST["files"])},
        "totals": {
            "live": len(live), "operators": len(ops), "agents": len(agents),
            "today_active": sum(v["today"] for v in dur.values()),
        },
    }


@app.get("/api/state")
def state():
    with closing(db()) as conn:
        return JSONResponse(_snapshot(conn))


@app.get("/api/skills")
def skills_stats(days: int = 30):
    with closing(db()) as conn:
        return JSONResponse(skills_overview(conn, days))


@app.get("/api/skill/{name}")
def skill_detail(name: str):
    with closing(db()) as conn:
        return JSONResponse(skill_detail_payload(conn, name))


@app.get("/api/operator/{name}")
def operator_detail(name: str):
    with closing(db()) as conn:
        return JSONResponse(operator_detail_payload(conn, name))


@app.get("/api/agent/{key}")
def agent_detail(key: str):
    """Single agent detail. key = 'operator::agentOrRuntime' (matches dashboard keyOf)."""
    with closing(db()) as conn:
        snap = _snapshot(conn)
    want = key.replace("::", "\x00", 1)
    for c in snap["sessions"]:
        if (c["operator"] + "\x00" + ((c.get("agent") or c["runtime"]))) == want:
            return JSONResponse(c)
    raise HTTPException(404, "agent not found")


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/")
def dashboard():
    return _spa_index()


def _spa_index():
    try:
        with open(os.path.abspath(FRONTEND_INDEX), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>frontend/dist/index.html not found</h1>", status_code=404)


def _plain_file(path, media_type="text/plain"):
    try:
        with open(path, encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type=media_type)
    except FileNotFoundError:
        return PlainTextResponse(f"{os.path.basename(path)} not found", status_code=404)


@app.get("/install.sh")
def install_sh():
    """Serve the installer from the dashboard domain, so teammates can install
    even when the GitHub repo is private:  curl -fsSL $SERVER/install.sh | bash -s -- ..."""
    return _plain_file(INSTALL_PATH, "text/x-shellscript")


@app.get("/llms.txt")
def llms_txt():
    return _plain_file(LLMS_PATH, "text/plain")


@app.get("/robots.txt")
def robots_txt():
    return _plain_file(ROBOTS_PATH, "text/plain")


@app.get("/shims/manifest")
def shim_manifest():
    """Serve the content-addressed shim manifest used by install/self-update."""
    return JSONResponse(_SHIM_MANIFEST)


@app.get("/shims/{path:path}")
def shim_file(path: str):
    """Serve shim client files (install.sh fetches these from $SERVER/shims/...)."""
    target = os.path.abspath(os.path.join(SHIMS_DIR, path))
    if not (target == SHIMS_DIR or target.startswith(SHIMS_DIR + os.sep)) or not os.path.isfile(target):
        raise HTTPException(status_code=404)
    media = _MEDIA.get(os.path.splitext(target)[1], "text/plain")
    with open(target, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type=media)


_SPA_BLOCKED_PREFIXES = {"api", "v1", "shims", "assets"}
_SPA_BLOCKED_PATHS = {"install.sh", "healthz", "llms.txt", "robots.txt"}


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve React BrowserRouter deep links without swallowing API/system routes."""
    first = full_path.split("/", 1)[0]
    leaf = full_path.rsplit("/", 1)[-1]
    if first in _SPA_BLOCKED_PREFIXES or full_path in _SPA_BLOCKED_PATHS or "." in leaf:
        raise HTTPException(status_code=404)
    return _spa_index()


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8788")))
