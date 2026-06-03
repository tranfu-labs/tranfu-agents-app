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
import os, json, sqlite3, time, threading, hashlib, secrets
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
          ".json": "application/json", ".md": "text/markdown"}

# profile keys the shim MAY include on an event (all optional, opt-in)
PROFILE_KEYS = ("models", "config", "mcp", "skills", "integrations",
                "about", "tips", "cf", "instructions", "memory")
# sensitive fields gated behind read-side auth (dropped if read access is open)
SENSITIVE_KEYS = ("input", "output", "instructions", "memory")

# §8 size limits
MAX_BODY = 256 * 1024          # reject the whole POST above this -> 413
MAX_CONTENT = 16 * 1024        # stored input/output, each
MAX_META = 4 * 1024            # stored meta json
WINDOW_DAYS = 90               # retention + read window

app = FastAPI(title="TRANFU//AGENTS")
_lock = threading.Lock()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


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

        -- per-operator token bindings (TATP v0.1 §4). Stores sha256(token) only.
        CREATE TABLE IF NOT EXISTS operators (
          operator TEXT PRIMARY KEY, token_hash TEXT, created TEXT
        );
        """)
        # tolerate upgrades from an older schema (add columns if missing)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
        for col, decl in (("recv", "TEXT"), ("v", "TEXT"),
                          ("parent_session_id", "TEXT"), ("verified", "INTEGER DEFAULT 0")):
            if col not in cols:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def check_auth(key):
    if INGEST_KEY and key != INGEST_KEY:
        raise HTTPException(status_code=401, detail="bad ingest key")


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


# ---------------------------------------------------------------- enroll (§4)
@app.post("/v1/enroll")
async def enroll(request: Request, x_tf_key: str = Header(default="")):
    """Admin issues a per-operator token. Guarded by the team write key.
    The plaintext token is returned ONCE; the server stores only its sha256."""
    check_auth(x_tf_key)
    body = await request.json()
    operator = (body.get("operator") or "").strip()
    if not operator:
        raise HTTPException(400, "operator required")
    token = "ttk_" + secrets.token_urlsafe(24)
    with _lock, closing(db()) as conn:
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
    if not all(e.get(k) for k in ("operator", "runtime", "session_id", "status")):
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    ts = e.get("ts") or now_iso()
    recv = now_iso()                               # server-authoritative time (§6)
    op, rt = e["operator"], e["runtime"]
    ag = e.get("agent") or rt                      # agent identity label
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
        verified = 1 if verify_operator(conn, op, x_tf_token) else 0

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
        clauses, params = ["operator=?"], [operator]
        if agent:
            clauses.append("COALESCE(agent,runtime)=?"); params.append(agent)
        if runtime:
            clauses.append("runtime=?"); params.append(runtime)
        deleted = conn.execute(
            f"DELETE FROM events WHERE {' AND '.join(clauses)}", params).rowcount
        cleared_profile = 0
        if body.get("profile") and agent:
            cleared_profile = conn.execute(
                "DELETE FROM profiles WHERE operator=? AND ak=?"
                + (" AND runtime=?" if runtime else ""),
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
        "totals": {
            "live": len(live), "operators": len(ops), "agents": len(agents),
            "today_active": sum(v["today"] for v in dur.values()),
        },
    }


@app.get("/api/state")
def state():
    with closing(db()) as conn:
        return JSONResponse(_snapshot(conn))


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
