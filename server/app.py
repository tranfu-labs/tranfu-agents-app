"""
TRANFU//AGENTS — collector server.

Ingest:
  POST /v1/events        JSON heartbeat (all agents via shim / MCP reporter)
                         May carry OPTIONAL profile fields (models, config, mcp,
                         skills, integrations, about, tips, cf, instructions,
                         memory). instructions+memory are sensitive -> opt-in.

Read:
  GET  /api/state        snapshot the dashboard polls (sessions + profile +
                         computed quality + leverage + 90d activity)
  GET  /api/agent/{key}  single agent detail (key = "operator::agentOrRuntime")
  GET  /                 the dashboard
  GET  /healthz

Storage is SQLite (file at $TF_DB, default ./tf.db). No external services.
"""
import os, json, sqlite3, time, threading
from datetime import datetime, timezone, timedelta
from contextlib import closing
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

DB_PATH = os.environ.get("TF_DB", "tf.db")
INGEST_KEY = os.environ.get("TF_KEY", "")          # "" = no auth (dev only)
DASH_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")

# profile keys the shim MAY include on an event (all optional, opt-in)
PROFILE_KEYS = ("models", "config", "mcp", "skills", "integrations",
                "about", "tips", "cf", "instructions", "memory")

app = FastAPI(title="TRANFU//AGENTS")
_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT, day TEXT,
          operator TEXT, agent TEXT, runtime TEXT, session_id TEXT,
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

        -- first time each skill name was seen (for leverage: assets / new-this-week)
        CREATE TABLE IF NOT EXISTS skills_seen (
          name TEXT PRIMARY KEY, first_day TEXT
        );
        """)
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def check_auth(key):
    if INGEST_KEY and key != INGEST_KEY:
        raise HTTPException(status_code=401, detail="bad ingest key")


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


# ---------------------------------------------------------------- ingest
@app.post("/v1/events")
async def ingest_event(request: Request, x_tf_key: str = Header(default="")):
    check_auth(x_tf_key)
    e = await request.json()
    if not all(e.get(k) for k in ("operator", "runtime", "session_id", "status")):
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    ts = e.get("ts") or now_iso()
    op, rt = e["operator"], e["runtime"]
    ag = e.get("agent") or rt                      # agent identity label
    status, step = e["status"], e.get("current_step")

    # OPTIONAL profile payload — store latest per identity (opt-in fields)
    profile = {k: e[k] for k in PROFILE_KEYS if e.get(k) is not None}

    with _lock, closing(db()) as conn:
        if profile:
            row = conn.execute("SELECT json FROM profiles WHERE operator=? AND ak=? AND runtime=?",
                               (op, ag, rt)).fetchone()
            merged = json.loads(row["json"]) if row else {}
            merged.update(profile)
            conn.execute("""INSERT INTO profiles(operator,ak,runtime,json,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET json=excluded.json,updated=excluded.updated""",
              (op, ag, rt, json.dumps(merged, ensure_ascii=False), ts))
            for nm in _skill_names(profile.get("skills")):
                conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)", (nm, ts[:10]))

        last = conn.execute("""SELECT id,status,current_step FROM events
            WHERE operator=? AND runtime=? AND COALESCE(agent,runtime)=?
            ORDER BY id DESC LIMIT 1""", (op, rt, ag)).fetchone()
        if last and last["status"] == status and (last["current_step"] or "") == (step or ""):
            # pure heartbeat: nothing changed -> only refresh liveness, no new row, no feed
            conn.execute("UPDATE events SET last_seen=? WHERE id=?", (ts, last["id"]))
            conn.commit()
            return {"ok": True, "heartbeat": True}
        conn.execute("""INSERT INTO events
          (ts,day,last_seen,operator,agent,runtime,session_id,status,task,current_step,model,
           input,output,meta,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (ts, ts[:10], ts, op, e.get("agent"), rt, e["session_id"], status,
           e.get("task"), step, e.get("model"), e.get("input"), e.get("output"),
           json.dumps(e.get("meta")) if e.get("meta") else None, "heartbeat"))
        conn.commit()
    return {"ok": True, "logged": True}


# ---------------------------------------------------------------- read helpers
CLOUD_RUNTIMES = {"manus", "mulerun", "chatgpt"}
STALE_SECONDS = 180
WINDOW_DAYS = 90
LIVE_ST = ("running", "started", "waiting")


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
    rows = conn.execute("""SELECT operator, COALESCE(agent,runtime) k, runtime, session_id, status, ts,
        COALESCE(last_seen, ts) ls FROM events WHERE day >= ?
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
        q = qual.setdefault(key, {"runs": 0, "done": 0, "error": 0, "active": 0.0, "auto": 0})
        active_start = last_ls = None
        saw_wait = False
        sess_active = 0.0
        for r in rows:
            t = _parse(r["ts"]); last_ls = _parse(r["ls"]); st = r["status"]
            if st in ("running", "started", "waiting"):
                if st == "waiting":
                    saw_wait = True
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
            "runs": runs, "success": q["done"], "error": q["error"],
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
        st = r["status"]
        if st in ("running", "started") and _age(r["last_seen"] or r["ts"]) > STALE_SECONDS:
            st = "idle"
        d["status"] = st
        for big in ("input", "output"):
            if d.get(big) and len(d[big]) > 4000:
                d[big] = d[big][:4000] + "…[truncated]"
        return d

    cards = [card(r) for r in sessions]
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


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8788")))
