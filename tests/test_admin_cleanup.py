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


def test_admin_key_required_and_denied_is_audited(client, app_mod):
    assert client.get("/api/admin/inventory", headers=ADMIN_HEADERS).status_code == 403
    assert table_count(app_mod, "admin_audit", "action='denied'") == 1

    enable_admin(app_mod)
    bad = client.get("/api/admin/inventory", headers={"X-TF-Admin-Key": "wrong"})
    assert bad.status_code == 403
    assert table_count(app_mod, "admin_audit", "action='denied'") == 2


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
    day = datetime.now(timezone.utc).date().isoformat()
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
    old_day = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
    new_day = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
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


def test_inventory_and_delete_cover_orphan_skill_uses(client, app_mod):
    enable_admin(app_mod)
    day = datetime.now(timezone.utc).date().isoformat()
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
    r = client.request("DELETE", "/v1/events", json={"session_id": "legacy"}, headers=ADMIN_HEADERS)
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

    old_day = (datetime.now(timezone.utc).date() - timedelta(days=120)).isoformat()
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
