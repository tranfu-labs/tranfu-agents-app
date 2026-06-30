from datetime import datetime, timezone, timedelta

from conftest import ev


ADMIN_HEADERS = {"X-TF-Admin-Key": "adminkey"}


def enable_admin(app_mod):
    app_mod.ADMIN_KEY = "adminkey"


def table_count(app_mod, table, where="", params=()):
    with app_mod.db() as conn:
        sql = f"SELECT COUNT(*) c FROM {table}" + (f" WHERE {where}" if where else "")
        return conn.execute(sql, params).fetchone()["c"]


def skill_first_day(app_mod, name):
    with app_mod.db() as conn:
        row = conn.execute("SELECT first_day FROM skills_seen WHERE name=?", (name,)).fetchone()
        return row["first_day"] if row else None


def preview(client, targets, **extra):
    body = {"targets": targets}
    body.update(extra)
    r = client.post("/api/admin/preview", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def delete_from_preview(client, targets, preview_payload, **extra):
    body = {"targets": targets, "preview_token": preview_payload["preview_token"]}
    body.update(extra)
    return client.request("DELETE", "/api/admin/data", json=body, headers=ADMIN_HEADERS)


def set_skill_day(app_mod, session_id, skill, day):
    with app_mod.db() as conn:
        conn.execute("""UPDATE skill_uses SET day=?, first_seen=?
          WHERE session_id=? AND skill=?""",
          (day, f"{day}T12:00:00+00:00", session_id, skill))
        conn.execute("""INSERT INTO skills_seen(name,first_day) VALUES(?,?)
          ON CONFLICT(name) DO UPDATE SET first_day=excluded.first_day""",
          (skill, day))
        conn.commit()


def test_admin_key_required_and_denied_is_deduped(client, app_mod):
    # admin 未配置时也算验钥失败,但仍 403;失败审计按来源+窗口去重 -> 同窗口多次只写一条
    assert client.get("/api/admin/inventory", headers=ADMIN_HEADERS).status_code == 403
    assert table_count(app_mod, "admin_audit", "action='denied'") == 1

    enable_admin(app_mod)
    bad = client.get("/api/admin/inventory", headers={"X-TF-Admin-Key": "wrong"})
    assert bad.status_code == 403
    # 同一来源同一窗口的第二次失败被降噪,不再追加审计行
    assert table_count(app_mod, "admin_audit", "action='denied'") == 1


def test_preview_is_dry_run_and_token_mismatch_conflicts(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="s1", status="done", skill="alpha", current_step="done")
    before = table_count(app_mod, "events"), table_count(app_mod, "skill_uses")

    p = preview(client, [{"session_ids": ["s1"]}])
    assert p["counts"]["events"] == 1
    assert p["counts"]["skill_uses"] == 1
    assert (table_count(app_mod, "events"), table_count(app_mod, "skill_uses")) == before

    ev(client, session_id="s1", status="error", current_step="late")
    r = delete_from_preview(client, [{"session_ids": ["s1"]}], p)
    assert r.status_code == 409


def test_delete_by_session_cascades_to_skills_and_restore_recovers(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="s1", status="done", skill="alpha", current_step="done")

    targets = [{"session_ids": ["s1"]}]
    p = preview(client, targets)
    r = delete_from_preview(client, targets, p)
    assert r.status_code == 200, r.text
    batch_id = r.json()["batch_id"]
    assert table_count(app_mod, "events") == 0
    assert table_count(app_mod, "skill_uses") == 0
    assert skill_first_day(app_mod, "alpha") is None
    assert client.get("/api/skill/alpha").status_code == 404
    assert client.get("/api/admin/trash", headers=ADMIN_HEADERS).json()["trash"][0]["batch_id"] == batch_id

    restored = client.post("/api/admin/restore", json={"batch_id": batch_id}, headers=ADMIN_HEADERS)
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"]["events"]["inserted"] == 1
    assert restored.json()["restored"]["skill_uses"]["inserted"] == 1
    assert table_count(app_mod, "events") == 1
    assert table_count(app_mod, "skill_uses") == 1
    assert client.get("/api/skill/alpha").status_code == 200


def test_restore_reports_key_conflicts_as_skipped(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="s1", status="done", skill="alpha", current_step="done")
    targets = [{"session_ids": ["s1"]}]
    p = preview(client, targets)
    batch_id = delete_from_preview(client, targets, p).json()["batch_id"]
    day = app_mod.stats_day()
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO skill_uses(session_id,skill,mode,operator,runtime,day,first_seen)
          VALUES('s1','alpha','used','alice','codex',?,?)""",
          (day, f"{day}T12:00:00+00:00"))
        conn.commit()

    restored = client.post("/api/admin/restore", json={"batch_id": batch_id}, headers=ADMIN_HEADERS)
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"]["events"]["inserted"] == 1
    assert restored.json()["restored"]["skill_uses"]["skipped"] == 1


def test_delete_by_skill_only_removes_skill_usage_not_events(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="s1", status="done", skill="typo-skill", current_step="done")
    before_events = table_count(app_mod, "events")

    targets = [{"skill": "typo-skill"}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 0
    assert p["counts"]["skill_uses"] == 1
    r = delete_from_preview(client, targets, p)
    assert r.status_code == 200, r.text
    assert table_count(app_mod, "events") == before_events
    assert table_count(app_mod, "skill_uses", "skill='typo-skill'") == 0
    assert skill_first_day(app_mod, "typo-skill") is None


def test_skills_seen_first_day_recomputed_after_deleting_first_use(client, app_mod):
    enable_admin(app_mod)
    old_day = (app_mod.stats_today() - timedelta(days=10)).isoformat()
    new_day = (app_mod.stats_today() - timedelta(days=3)).isoformat()
    ev(client, session_id="old", status="done", skill="alpha", current_step="old")
    ev(client, session_id="new", status="done", skill="alpha", current_step="new")
    set_skill_day(app_mod, "old", "alpha", old_day)
    set_skill_day(app_mod, "new", "alpha", new_day)
    with app_mod.db() as conn:
        conn.execute("UPDATE skills_seen SET first_day=? WHERE name='alpha'", (old_day,))
        conn.commit()

    targets = [{"session_ids": ["old"]}]
    p = preview(client, targets)
    assert p["effects"]["first_day_changes"] == [{"skill": "alpha", "from": old_day, "to": new_day}]
    r = delete_from_preview(client, targets, p)
    assert r.status_code == 200, r.text
    assert skill_first_day(app_mod, "alpha") == new_day


def test_operator_delete_clears_profiles_and_identities_but_keeps_token_by_default(client, app_mod):
    enable_admin(app_mod)
    tok = client.post("/v1/enroll", json={"operator": "zoe"}).json()["token"]
    ev(client, operator="zoe", runtime="codex", agent="code", session_id="s1",
       status="done", current_step="profile", skill="alpha",
       skills={"local": [{"name": "alpha"}]}, headers={"X-TF-Token": tok})

    targets = [{"operator": "zoe"}]
    p = preview(client, targets)
    r = delete_from_preview(client, targets, p)
    assert r.status_code == 200, r.text
    assert table_count(app_mod, "profiles") == 0
    assert table_count(app_mod, "identities", "norm='zoe'") == 0
    assert table_count(app_mod, "operators", "operator='zoe'") == 1

    tok2 = client.post("/v1/enroll", json={"operator": "zoe"}).json()["token"]
    ev(client, operator="zoe", runtime="codex", session_id="s2",
       status="done", current_step="again", headers={"X-TF-Token": tok2})
    p2 = preview(client, targets, revoke=True)
    r2 = delete_from_preview(client, targets, p2, revoke=True)
    assert r2.status_code == 200, r2.text
    batch_id = r2.json()["batch_id"]
    assert table_count(app_mod, "operators", "operator='zoe'") == 0
    restored = client.post("/api/admin/restore", json={"batch_id": batch_id}, headers=ADMIN_HEADERS)
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"]["operators"]["inserted"] == 1
    assert table_count(app_mod, "operators", "operator='zoe'") == 1


def _insert_event(app_mod, session_id, operator, runtime="codex", status="done",
                  parent_session_id=None, day=None):
    day = day or app_mod.stats_day()
    ts = f"{day}T12:00:00+00:00"
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO events(ts,recv,day,last_seen,operator,runtime,
            session_id,parent_session_id,status,source)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          (ts, ts, day, ts, operator, runtime, session_id, parent_session_id, status, "heartbeat"))
        conn.commit()


def _insert_skill_use(app_mod, session_id, skill, operator, mode="used", runtime="codex", day=None):
    day = day or app_mod.stats_day()
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO skill_uses(session_id,skill,mode,operator,runtime,day,first_seen)
          VALUES(?,?,?,?,?,?,?)""",
          (session_id, skill, mode, operator, runtime, day, f"{day}T12:00:00+00:00"))
        conn.commit()


def test_operator_delete_scopes_to_own_rows_in_shared_session(client, app_mod):
    # 脏数据:一个 session 由 A、B 共用 -> 删 A 只解析出 A 的行,B 完全不动
    enable_admin(app_mod)
    _insert_event(app_mod, "shared", "alice")
    _insert_event(app_mod, "shared", "bob")
    _insert_skill_use(app_mod, "shared", "alpha", "alice")
    _insert_skill_use(app_mod, "shared", "beta", "bob")

    targets = [{"operator": "alice"}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 1
    assert p["counts"]["skill_uses"] == 1
    assert p["operators"] == ["alice"]            # 预览只反映 A 自己

    assert delete_from_preview(client, targets, p).status_code == 200
    # B 的 event 与 skill_use 全部保留
    assert table_count(app_mod, "events", "session_id='shared' AND operator='bob'") == 1
    assert table_count(app_mod, "events", "session_id='shared' AND operator='alice'") == 0
    assert table_count(app_mod, "skill_uses", "session_id='shared' AND operator='bob'") == 1
    assert table_count(app_mod, "skill_uses", "session_id='shared' AND operator='alice'") == 0


def test_sentinel_session_delete_keeps_other_operators(client, app_mod):
    # 哨兵 session:codex-doctor 式多人共用同一 session_id -> 删一人留其余
    enable_admin(app_mod)
    for op in ("alice", "bob", "carol"):
        _insert_event(app_mod, "codex-doctor", op)
    targets = [{"operator": "bob"}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 1
    assert p["operators"] == ["bob"]
    assert delete_from_preview(client, targets, p).status_code == 200
    assert table_count(app_mod, "events", "session_id='codex-doctor'") == 2
    assert table_count(app_mod, "events", "session_id='codex-doctor' AND operator='bob'") == 0


def test_session_ids_delete_still_purges_whole_shared_session(client, app_mod):
    # 回归:按 session_ids 显式删,仍整删该 session 全部行(不被 operator 过滤误伤)
    enable_admin(app_mod)
    _insert_event(app_mod, "shared", "alice")
    _insert_event(app_mod, "shared", "bob")
    _insert_skill_use(app_mod, "shared", "alpha", "alice")
    _insert_skill_use(app_mod, "shared", "beta", "bob")

    targets = [{"session_ids": ["shared"]}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 2
    assert p["counts"]["skill_uses"] == 2
    # 整删共用 session 牵涉 >1 operator,过确认闸
    assert delete_from_preview(client, targets, p, confirm_count=p["total_rows"]).status_code == 200
    assert table_count(app_mod, "events", "session_id='shared'") == 0
    assert table_count(app_mod, "skill_uses", "session_id='shared'") == 0


def test_skill_selector_unchanged_on_shared_session(client, app_mod):
    # 回归:skill 选择器行为不变,只触该 skill 的 skill_uses,不动 events、不按 operator 收口
    enable_admin(app_mod)
    _insert_event(app_mod, "shared", "alice")
    _insert_event(app_mod, "shared", "bob")
    _insert_skill_use(app_mod, "shared", "alpha", "alice")
    _insert_skill_use(app_mod, "other", "alpha", "bob")

    targets = [{"skill": "alpha"}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 0
    assert p["counts"]["skill_uses"] == 2         # 两个 operator 的 alpha 都触及
    assert delete_from_preview(client, targets, p, confirm_count=p["total_rows"]).status_code == 200
    assert table_count(app_mod, "skill_uses", "skill='alpha'") == 0
    assert table_count(app_mod, "events", "session_id='shared'") == 2


def test_cascade_children_scopes_to_operator(client, app_mod):
    # 级联后代时仍按 operator 收口:父子会话各有 A、B 行,删 A 不借后代卷入 B
    enable_admin(app_mod)
    _insert_event(app_mod, "p", "alice")
    _insert_event(app_mod, "p", "bob")
    _insert_event(app_mod, "c", "alice", parent_session_id="p")
    _insert_event(app_mod, "c", "bob", parent_session_id="p")

    targets = [{"operator": "alice"}]
    p = preview(client, targets, cascade_children=True)
    assert p["counts"]["events"] == 2             # 父+子里 alice 各一行
    assert p["operators"] == ["alice"]
    assert delete_from_preview(client, targets, p, cascade_children=True).status_code == 200
    assert table_count(app_mod, "events", "operator='alice'") == 0
    assert table_count(app_mod, "events", "operator='bob'") == 2


def test_inventory_and_delete_cover_orphan_skill_uses(client, app_mod):
    enable_admin(app_mod)
    day = app_mod.stats_day()
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO skill_uses(session_id,skill,mode,operator,runtime,day,first_seen)
          VALUES('orphan','alpha','used','ghost','codex',?,?)""",
          (day, f"{day}T12:00:00+00:00"))
        conn.commit()

    inventory = client.get("/api/admin/inventory?q=orphan", headers=ADMIN_HEADERS).json()
    assert any(row["session_id"] == "orphan" and row["skill_uses"] == 1 for row in inventory["sessions"])
    targets = [{"session_ids": ["orphan"]}]
    p = preview(client, targets)
    assert p["counts"]["events"] == 0
    assert p["counts"]["skill_uses"] == 1
    assert delete_from_preview(client, targets, p).status_code == 200
    assert table_count(app_mod, "skill_uses") == 0


def test_cascade_children_and_before_day_validation(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="parent", status="done", current_step="p")
    ev(client, session_id="child", parent_session_id="parent", status="done", current_step="c")

    targets = [{"session_ids": ["parent"]}]
    p = preview(client, targets, cascade_children=True)
    assert p["counts"]["events"] == 2
    r = delete_from_preview(client, targets, p, cascade_children=True)
    assert r.status_code == 200, r.text
    assert table_count(app_mod, "events") == 0

    bad = client.post("/api/admin/preview", json={"targets": [{"before_day": "2026-01-01"}]},
                      headers=ADMIN_HEADERS)
    assert bad.status_code == 400


def test_active_force_and_confirm_count_guards(client, app_mod):
    enable_admin(app_mod)
    ev(client, operator="alice", session_id="live", status="running", current_step="x")
    targets = [{"session_ids": ["live"]}]
    p = preview(client, targets)
    assert p["requires_force"] is True
    assert delete_from_preview(client, targets, p).status_code == 400

    r = delete_from_preview(client, targets, p, force=True)
    assert r.status_code == 200, r.text

    app_mod.ADMIN_MAX_ROWS = 0
    ev(client, operator="bob", session_id="big", status="done", current_step="x")
    targets = [{"session_ids": ["big"]}]
    p2 = preview(client, targets)
    assert p2["requires_confirm"] is True
    assert delete_from_preview(client, targets, p2).status_code == 400
    ok = delete_from_preview(client, targets, p2, confirm_count=p2["total_rows"])
    assert ok.status_code == 200, ok.text


def test_legacy_delete_routes_through_cascade_and_trash(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="legacy", status="running", skill="alpha", current_step="x")
    # 活跃会话:遗留端点现也要求 force(护栏对齐),无 force 先被拒
    blocked = client.request("DELETE", "/v1/events", json={"session_id": "legacy"}, headers=ADMIN_HEADERS)
    assert blocked.status_code == 400
    r = client.request("DELETE", "/v1/events", json={"session_id": "legacy", "force": True}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 1
    assert r.json()["counts"]["skill_uses"] == 1
    assert table_count(app_mod, "events") == 0
    assert table_count(app_mod, "skill_uses") == 0
    assert table_count(app_mod, "admin_trash") == 1


def test_trash_prune_and_retention_prune_are_audited_without_trash(client, app_mod):
    enable_admin(app_mod)
    ev(client, session_id="old-trash", status="done", skill="alpha", current_step="x")
    targets = [{"session_ids": ["old-trash"]}]
    p = preview(client, targets)
    delete_from_preview(client, targets, p)
    app_mod.TRASH_DAYS = 1
    old_created = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with app_mod.db() as conn:
        conn.execute("UPDATE admin_trash SET created=?", (old_created,))
        conn.commit()

    trash = client.get("/api/admin/trash", headers=ADMIN_HEADERS).json()["trash"]
    assert trash == []
    assert table_count(app_mod, "admin_audit", "action='purge_trash'") == 1

    old_day = (app_mod.stats_today() - timedelta(days=120)).isoformat()
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO events(ts,recv,day,last_seen,operator,runtime,session_id,status,source)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (f"{old_day}T00:00:00+00:00", f"{old_day}T00:00:00+00:00", old_day,
           f"{old_day}T00:00:00+00:00", "alice", "codex", "too-old", "done", "heartbeat"))
        conn.commit()
    app_mod._prune_state["n"] = 0
    ev(client, session_id="fresh", status="done", current_step="fresh")
    assert table_count(app_mod, "events", "session_id='too-old'") == 0
    assert table_count(app_mod, "admin_trash") == 0
    assert table_count(app_mod, "admin_audit", "action='retention_prune'") == 1


# ------------------------------------------------------------ 认证加固 / 防爆破

BAD = {"X-TF-Admin-Key": "wrong"}


def _clear_block(app_mod):
    """模拟封锁窗口到期(不真实 sleep),保留 streak 以验证退避增长。"""
    with app_mod._rate_lock:
        for e in app_mod._rate_state.values():
            e["blocked_until"] = 0.0


def test_rate_limit_locks_after_threshold(client, app_mod):
    enable_admin(app_mod)
    app_mod.ADMIN_RATE_MAX = 3
    for _ in range(3):                       # 阈值内:仍是 403
        assert client.get("/api/admin/inventory", headers=BAD).status_code == 403
    r = client.get("/api/admin/inventory", headers=BAD)   # 越过阈值 -> 429
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    # 封锁期内即便带正确钥匙也 429(不验钥、不写审计)
    assert client.get("/api/admin/inventory", headers=ADMIN_HEADERS).status_code == 429


def test_lockout_recovers_after_expiry(client, app_mod):
    enable_admin(app_mod)
    app_mod.ADMIN_RATE_MAX = 1
    assert client.get("/api/admin/inventory", headers=BAD).status_code == 403
    assert client.get("/api/admin/inventory", headers=BAD).status_code == 429
    with app_mod._rate_lock:                 # 模拟封锁+窗口到期
        for e in app_mod._rate_state.values():
            e["blocked_until"] = 0.0
            e["win_start"] = 0.0
    assert client.get("/api/admin/inventory", headers=ADMIN_HEADERS).status_code == 200


def test_lockout_backoff_grows_and_caps(client, app_mod):
    enable_admin(app_mod)
    app_mod.ADMIN_RATE_MAX = 0               # 任何失败立即封锁
    app_mod.ADMIN_LOCK_BASE = 10
    app_mod.ADMIN_LOCK_MAX = 100
    r1 = client.get("/api/admin/inventory", headers=BAD)
    assert r1.status_code == 429
    first = int(r1.headers["retry-after"])
    _clear_block(app_mod)
    r2 = client.get("/api/admin/inventory", headers=BAD)
    assert r2.status_code == 429
    second = int(r2.headers["retry-after"])
    assert second > first                     # 指数退避:第二轮更长
    assert second <= app_mod.ADMIN_LOCK_MAX + 1


def test_denied_audit_deduped_per_window(client, app_mod):
    enable_admin(app_mod)
    app_mod.ADMIN_RATE_MAX = 100             # 不触封锁,只看降噪
    for _ in range(8):
        assert client.get("/api/admin/inventory", headers=BAD).status_code == 403
    assert table_count(app_mod, "admin_audit", "action='denied'") == 1


def test_xff_ignored_without_trust_proxy(client, app_mod):
    enable_admin(app_mod)
    app_mod.TRUST_PROXY = False
    app_mod.ADMIN_RATE_MAX = 2
    for i in range(3):                        # 伪造各异 XFF 不改变分桶
        client.get("/api/admin/inventory",
                   headers={**BAD, "X-Forwarded-For": f"10.0.0.{i}"})
    r = client.get("/api/admin/inventory", headers={**BAD, "X-Forwarded-For": "10.0.0.9"})
    assert r.status_code == 429              # 同一连接 IP 桶已封锁


def test_xff_buckets_separately_with_trust_proxy(client, app_mod):
    enable_admin(app_mod)
    app_mod.TRUST_PROXY = True
    app_mod.ADMIN_RATE_MAX = 1
    a = {**BAD, "X-Forwarded-For": "1.1.1.1"}
    b = {**BAD, "X-Forwarded-For": "2.2.2.2"}
    assert client.get("/api/admin/inventory", headers=a).status_code == 403
    assert client.get("/api/admin/inventory", headers=b).status_code == 403  # 独立桶
    assert client.get("/api/admin/inventory", headers=a).status_code == 429
    assert client.get("/api/admin/inventory", headers=b).status_code == 429


def test_export_requires_post_and_confirm(client, app_mod):
    enable_admin(app_mod)
    # GET 不再暴露(只剩 POST);api 前缀被 SPA 兜底拦下 -> 404
    assert client.get("/api/admin/export", headers=ADMIN_HEADERS).status_code in (404, 405)
    assert client.post("/api/admin/export", headers=ADMIN_HEADERS).status_code == 400
    r = client.post("/api/admin/export", json={"confirm": "EXPORT"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert table_count(app_mod, "admin_audit", "action='export'") == 1


def test_legacy_delete_enforces_max_rows_confirm(client, app_mod):
    enable_admin(app_mod)
    app_mod.ADMIN_MAX_ROWS = 0
    ev(client, operator="carol", session_id="leg2", status="done", current_step="x")
    blocked = client.request("DELETE", "/v1/events",
                             json={"session_id": "leg2"}, headers=ADMIN_HEADERS)
    assert blocked.status_code == 400
    ok = client.request("DELETE", "/v1/events",
                        json={"session_id": "leg2", "confirm_count": 1}, headers=ADMIN_HEADERS)
    assert ok.status_code == 200, ok.text


def test_security_headers_present(client, app_mod):
    r = client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers   # 非 HTTPS 不发 HSTS


def test_enroll_is_rate_limited(client, app_mod):
    app_mod.INGEST_KEY = "ingestkey"
    app_mod.ADMIN_RATE_MAX = 2
    bad = {"X-TF-Key": "nope"}
    assert client.post("/v1/enroll", json={"operator": "x"}, headers=bad).status_code == 401
    assert client.post("/v1/enroll", json={"operator": "x"}, headers=bad).status_code == 401
    assert client.post("/v1/enroll", json={"operator": "x"}, headers=bad).status_code == 429
    # 写侧高频上报路径不受影响(豁免)
    ok = client.post("/v1/events",
                     json={"v": "0.1", "operator": "alice", "runtime": "codex",
                           "session_id": "s1", "status": "running"},
                     headers={"X-TF-Key": "ingestkey"})
    assert ok.status_code == 200, ok.text
