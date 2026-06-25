"""数据库连接 / schema / 迁移 / 工具(由 refactor-server-app-by-domain 引入)。

跨 spec 域共享:event 表是 ingest 写、board 读、admin 删的共同载体;profiles /
agent_shim_versions / skill_uses / identities / catalog_cache / admin_trash / admin_audit
均集中在此创建。

`DB_PATH` 是可变开关,留在 server/app.py;`db()` 函数体内延迟 import 读取,避免循环。
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta


# ---- 共用工具 -------------------------------------------------------------
def now_iso():
    # 通过 server.app 延迟读 datetime,保留原有「app.datetime 是单一时间源」语义
    # (tests/test_skills_stats_page.py 等会 monkeypatch app_mod.datetime)。
    from server import app
    return app.datetime.now(timezone.utc).isoformat()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clip(s, n):
    """Truncate an over-long string for storage, marking the cut."""
    if isinstance(s, str) and len(s) > n:
        return s[:n] + "…[truncated]"
    return s


# ---- 连接 -----------------------------------------------------------------
def db():
    from server import app  # 延迟读取可变 DB_PATH
    conn = sqlite3.connect(app.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # readers don't block the writer
    conn.execute("PRAGMA busy_timeout=4000")
    return conn


# ---- schema + migration --------------------------------------------------
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

        -- sticky shim version per agent identity. Separate from `profiles` so
        -- profile full-replacement (mcp/skills/etc.) cannot accidentally erase
        -- it on heartbeats that omit the field. Updated only when an event
        -- carries a non-empty shim_version; never cleared by absence.
        CREATE TABLE IF NOT EXISTS agent_shim_versions (
          operator TEXT, ak TEXT, runtime TEXT,
          shim_version TEXT, updated TEXT,
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
            if col not in cols:  # pragma: no cover  — 老 schema 升级路径,init_db 在空 DB 不进
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
        if prof:  # pragma: no cover  — 历史 profiles 身份归一化迁移,空 DB 不进
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


# ---- 审计 + 保留 ---------------------------------------------------------
def _audit(conn, actor, action, selector=None, counts=None, batch_id=None):
    conn.execute("""INSERT INTO admin_audit(ts,actor,action,selector,counts,batch_id)
      VALUES(?,?,?,?,?,?)""",
      (now_iso(), actor or "", action, _json(selector or {}), _json(counts or {}), batch_id))


_prune_state = {"n": 0}


def _maybe_prune(conn):
    """Retention (§6): every ~200 inserts, drop events older than the window."""
    from server import app  # 延迟读 datetime(可被 monkeypatch)与 WINDOW_DAYS
    _prune_state["n"] += 1
    if _prune_state["n"] % 200 != 1:
        return
    cutoff = (app.datetime.now(timezone.utc).date() - timedelta(days=app.WINDOW_DAYS - 1)).isoformat()
    deleted = conn.execute("DELETE FROM events WHERE day < ?", (cutoff,)).rowcount
    if deleted:
        _audit(conn, "system", "retention_prune", {"cutoff": cutoff}, {"events": deleted}, None)


def _maybe_prune_trash(conn):
    from server import app  # 延迟读 datetime + TRASH_DAYS
    if app.TRASH_DAYS <= 0:
        return 0
    cutoff = (app.datetime.now(timezone.utc) - timedelta(days=app.TRASH_DAYS)).isoformat()
    deleted = conn.execute("DELETE FROM admin_trash WHERE created < ?", (cutoff,)).rowcount
    if deleted:
        _audit(conn, "system", "purge_trash", {"cutoff": cutoff}, {"admin_trash": deleted}, None)
    return deleted
