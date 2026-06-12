"""
TRANFU//AGENTS — collector server. Implements TATP v0.1 (see ../PROTOCOL.md).

Ingest:
  POST /v1/enroll        admin (X-TF-Key) issues a per-operator token (one-time)
  POST /v1/events        JSON heartbeat (all agents via shim / MCP reporter)
                         May carry OPTIONAL profile fields (models, config, mcp,
                         skills, integrations, about, tips, cf, instructions,
                         memory). instructions+memory are sensitive -> opt-in and
                         gated by read-side auth (see PROTOCOL.md §5).
  DELETE /v1/events      admin (X-TF-Key) cleanup — drop events by session_ids or
                         by identity (operator[/agent/runtime]); optional profile
                         clear. For pruning test/junk sessions off the board.

Read:
  GET  /api/state        snapshot the dashboard polls (sessions + profile +
                         computed quality + leverage + 90d activity)
  GET  /api/agent/{key}  single agent detail (key = "operator::agentOrRuntime")
  GET  /                 the dashboard
  GET  /healthz

Storage is SQLite (WAL) at $TF_DB, default ./tf.db. No external services.
"""
import os, json, sqlite3, time, threading, hashlib, secrets, urllib.request
from datetime import datetime, timezone, timedelta
from contextlib import closing
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

DB_PATH = os.environ.get("TF_DB", "tf.db")
INGEST_KEY = os.environ.get("TF_KEY", "")          # "" = no auth (dev only)
# per-operator attribution: when on, every event MUST carry a valid X-TF-Token
# whose bound operator matches the body's `operator` (TATP v0.1 §4).
REQUIRE_TOKEN = os.environ.get("TF_REQUIRE_TOKEN", "0") == "1"
# read-side auth gate for content capture (TATP v0.1 §5). Sensitive fields are
# stored ONLY when read access is protected: either the app read-key is set, or
# the operator asserts an edge gate (Cloudflare Access / Caddy) via TF_READ_AUTH=1.
READ_AUTH_OK = bool(os.environ.get("TF_READ_KEY")) or os.environ.get("TF_READ_AUTH", "0") == "1"
DASH_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHIMS_DIR = os.path.join(REPO_ROOT, "shims")
INSTALL_PATH = os.path.join(REPO_ROOT, "install.sh")
_MEDIA = {".sh": "text/x-shellscript", ".py": "text/x-python",
          ".js": "text/javascript", ".mjs": "text/javascript",
          ".json": "application/json", ".md": "text/markdown"}
_EXECUTABLE_SHIMS = {
    "tf_client.sh", "tf_hooks.py", "tf_claude_hooks.py",
    "wrapper/tf-run", "wrapper/tf-hermes-hook.sh",
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

app = FastAPI(title="TRANFU//AGENTS")
_lock = threading.Lock()
_catalog_lock = threading.Lock()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default


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


def check_auth(key):
    if INGEST_KEY and key != INGEST_KEY:
        raise HTTPException(status_code=401, detail="bad ingest key")


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
    check_auth(x_tf_key)
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


# ---------------------------------------------------------------- delete (admin)
@app.delete("/v1/events")
async def delete_events(request: Request, x_tf_key: str = Header(default="")):
    """Admin cleanup, guarded by the team write key (same gate as ingest).
    Delete by ONE of:
      {"session_ids": ["s1","s2"]} / {"session_id": "s1"}  -> drop those sessions
      {"operator": "...", "agent": "...", "runtime": "...", -> drop a whole identity
       "profile": true}                                        (profile:true also
                                                                clears its card profile)
    Returns the number of event rows deleted (deleted may be 0 — no-op safe)."""
    check_auth(x_tf_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    sids = list(body.get("session_ids") or [])
    if isinstance(body.get("session_id"), str):
        sids.append(body["session_id"])
    operator = body.get("operator")
    if not sids and not operator:
        raise HTTPException(400, "need session_ids or operator")
    if sids and not all(isinstance(s, str) for s in sids):
        raise HTTPException(400, "session_ids must be strings")

    with _lock, closing(db()) as conn:
        if sids:
            marks = ",".join("?" * len(sids))
            deleted = conn.execute(
                f"DELETE FROM events WHERE session_id IN ({marks})", sids).rowcount
            conn.commit()
            return {"ok": True, "deleted": deleted, "by": "session_ids"}
        agent, runtime = body.get("agent"), body.get("runtime")
        clauses, params = ["lower(trim(operator))=lower(trim(?))"], [operator]
        if agent:
            clauses.append("COALESCE(agent,runtime)=?"); params.append(agent)
        if runtime:
            clauses.append("lower(trim(runtime))=lower(trim(?))"); params.append(runtime)
        deleted = conn.execute(
            f"DELETE FROM events WHERE {' AND '.join(clauses)}", params).rowcount
        cleared_profile = 0
        if body.get("profile") and agent:
            cleared_profile = conn.execute(
                "DELETE FROM profiles WHERE lower(trim(operator))=lower(trim(?)) AND ak=?"
                + (" AND lower(trim(runtime))=lower(trim(?))" if runtime else ""),
                ([operator, agent, runtime] if runtime else [operator, agent])).rowcount
        conn.commit()
        return {"ok": True, "deleted": deleted,
                "cleared_profile": cleared_profile, "by": "identity"}


_prune_state = {"n": 0}


def _maybe_prune(conn):
    """Retention (§6): every ~200 inserts, drop events older than the window."""
    _prune_state["n"] += 1
    if _prune_state["n"] % 200 != 1:
        return
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    conn.execute("DELETE FROM events WHERE day < ?", (cutoff,))


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
    if days not in (0, 7, 30, 90):
        raise HTTPException(400, "days must be one of 7, 30, 90, 0")
    today = datetime.now(timezone.utc).date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    d14 = (today - timedelta(days=13)).isoformat()
    daily_start = None if days == 0 else _day_cutoff(days)
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
        "daily": daily,
        "table": table,
        "funnel": funnel,
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
    try:
        with open(os.path.abspath(DASH_PATH), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>dashboard/index.html not found</h1>", status_code=404)


@app.get("/install.sh")
def install_sh():
    """Serve the installer from the dashboard domain, so teammates can install
    even when the GitHub repo is private:  curl -fsSL $SERVER/install.sh | bash -s -- ..."""
    try:
        with open(INSTALL_PATH, encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type="text/x-shellscript")
    except FileNotFoundError:
        return PlainTextResponse("install.sh not found", status_code=404)


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


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8788")))
