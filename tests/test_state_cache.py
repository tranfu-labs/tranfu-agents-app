import inspect
import threading
import time


def _clear_state_cache(app_mod):
    with app_mod._state_cache_lock:
        app_mod._state_cache.update({"at": 0.0, "data": None, "computing": False})


def test_state_snapshot_cache_hits_within_ttl(app_mod, monkeypatch):
    calls = {"n": 0}

    def fake_snapshot(conn):
        calls["n"] += 1
        return {"calls": calls["n"]}

    monkeypatch.setattr(app_mod, "_snapshot", fake_snapshot)
    monkeypatch.setattr(app_mod, "STATE_TTL_SECONDS", 60.0)
    _clear_state_cache(app_mod)

    first = app_mod._state_compute_or_cache()
    second = app_mod._state_compute_or_cache()

    assert first == {"calls": 1}
    assert second == first
    assert calls["n"] == 1


def test_state_snapshot_cache_recomputes_after_ttl(app_mod, monkeypatch):
    calls = {"n": 0}

    def fake_snapshot(conn):
        calls["n"] += 1
        return {"calls": calls["n"]}

    monkeypatch.setattr(app_mod, "_snapshot", fake_snapshot)
    monkeypatch.setattr(app_mod, "STATE_TTL_SECONDS", 1.5)
    _clear_state_cache(app_mod)

    assert app_mod._state_compute_or_cache() == {"calls": 1}
    with app_mod._state_cache_lock:
        app_mod._state_cache["at"] = app_mod.time.monotonic() - 2.0

    assert app_mod._state_compute_or_cache() == {"calls": 2}
    assert calls["n"] == 2


def test_state_snapshot_cache_zero_ttl_disables_reuse(app_mod, monkeypatch):
    calls = {"n": 0}

    def fake_snapshot(conn):
        calls["n"] += 1
        return {"calls": calls["n"]}

    monkeypatch.setenv("TF_STATE_TTL", "0")
    monkeypatch.setattr(app_mod, "STATE_TTL_SECONDS", app_mod._env_float("TF_STATE_TTL", "1.5"))
    monkeypatch.setattr(app_mod, "_snapshot", fake_snapshot)
    _clear_state_cache(app_mod)

    assert app_mod._state_compute_or_cache() == {"calls": 1}
    assert app_mod._state_compute_or_cache() == {"calls": 2}
    assert calls["n"] == 2


def test_state_snapshot_cache_singleflight_on_cold_miss(app_mod, monkeypatch):
    calls = {"n": 0}

    def fake_snapshot(conn):
        time.sleep(0.05)
        calls["n"] += 1
        return {"calls": calls["n"]}

    monkeypatch.setattr(app_mod, "_snapshot", fake_snapshot)
    monkeypatch.setattr(app_mod, "STATE_TTL_SECONDS", 60.0)
    _clear_state_cache(app_mod)
    barrier = threading.Barrier(6)
    results = []

    def worker():
        barrier.wait()
        results.append(app_mod._state_compute_or_cache())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert results == [{"calls": 1}] * 5
    assert calls["n"] == 1


def test_state_and_healthz_handlers_are_async(app_mod):
    assert inspect.iscoroutinefunction(app_mod.state)
    assert inspect.iscoroutinefunction(app_mod.state_stream)
    assert inspect.iscoroutinefunction(app_mod.healthz)
