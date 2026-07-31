from types import SimpleNamespace

import pytest

from scripts import check_sub2api_contract as contract


def _args(**overrides):
    values = {
        "base_url": "https://sub2.test",
        "admin_key": "admin-secret-value",
        "timeout": 1,
        "user_id": 1,
        "api_key_id": None,
        "timezone": "Asia/Shanghai",
        "start_date": "2026-07-29",
        "end_date": "2026-07-30",
        "allow_empty_keys": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeChecker:
    missing_field = ""
    empty_keys = False
    empty_snapshot = False
    calls = []

    def __init__(self, *_args):
        type(self).calls = []

    def request(self, path, params=None, *, envelope=True):
        type(self).calls.append((path, params))
        if path == "/health":
            return {"status": "ok", "extra": True}
        if path.endswith("/system/version"):
            return {"version": "v0.1.166", "new_field": "allowed"}
        if path.endswith("/api-keys"):
            items = [] if self.empty_keys else [{
                "id": 7,
                "name": "key-a",
                "key": "sk-never-retain",
                "quota": 10,
                "quota_used": 2,
                "new_field": "allowed",
            }]
            return {"items": items, "total": len(items), "page": 1, "page_size": 100, "pages": 1}
        if path.endswith("/api-keys-trend"):
            return {
                "start_date": "2026-07-29",
                "end_date": "2026-07-30",
                "trend": [{"date": "2026-07-30", "api_key_id": 7, "key_name": "key-a", "requests": 2, "tokens": 30}],
            }
        if path.endswith("/snapshot-v2"):
            if self.empty_snapshot:
                return {
                    "start_date": "2026-07-29",
                    "end_date": "2026-07-30",
                    "granularity": "day",
                }
            return {
                "start_date": "2026-07-29",
                "end_date": "2026-07-30",
                "trend": [{"date": "2026-07-30", "requests": 2}],
                "models": [{"model": "gpt-5", "requests": 2, "total_tokens": 30, "actual_cost": 0.25}],
            }
        if path.endswith("/usage/stats"):
            data = {
                "total_requests": 2,
                "total_input_tokens": 10,
                "total_output_tokens": 20,
                "total_tokens": 30,
                "total_actual_cost": 0.25,
                "average_duration_ms": 1250,
            }
            data.pop(self.missing_field, None)
            return data
        if path.endswith("/ops/errors"):
            page = params["page"]
            return {
                "items": [{"api_key_id": 7}] if page == 1 else [],
                "total": 2,
                "page": page,
                "page_size": 1,
                "pages": 2,
            }
        raise AssertionError(path)


def test_contract_gate_accepts_v01166_and_additive_fields(monkeypatch):
    FakeChecker.missing_field = ""
    FakeChecker.empty_keys = False
    FakeChecker.empty_snapshot = False
    monkeypatch.setattr(contract, "Checker", FakeChecker)
    result = contract.check_contract(_args())
    assert result == {"version": "v0.1.166", "key_count": 1, "checked_key_id": 7}
    assert any(path.endswith("/snapshot-v2") for path, _params in FakeChecker.calls)
    error_calls = [(path, params) for path, params in FakeChecker.calls if path.endswith("/ops/errors")]
    assert [params["page"] for _path, params in error_calls] == [1, 2]
    assert all(params["api_key_id"] == 7 for _path, params in error_calls)


def test_contract_gate_rejects_missing_required_metric(monkeypatch):
    FakeChecker.missing_field = "total_actual_cost"
    FakeChecker.empty_keys = False
    FakeChecker.empty_snapshot = False
    monkeypatch.setattr(contract, "Checker", FakeChecker)
    with pytest.raises(contract.ContractError, match="total_actual_cost must be numeric"):
        contract.check_contract(_args())


def test_contract_gate_empty_inventory_policy(monkeypatch):
    FakeChecker.missing_field = ""
    FakeChecker.empty_keys = True
    FakeChecker.empty_snapshot = False
    monkeypatch.setattr(contract, "Checker", FakeChecker)
    with pytest.raises(contract.ContractError, match="inventory is empty"):
        contract.check_contract(_args())
    assert contract.check_contract(_args(allow_empty_keys=True))["key_count"] == 0


def test_contract_gate_accepts_empty_snapshot_with_valid_range(monkeypatch):
    FakeChecker.missing_field = ""
    FakeChecker.empty_keys = False
    FakeChecker.empty_snapshot = True
    monkeypatch.setattr(contract, "Checker", FakeChecker)
    assert contract.check_contract(_args())["checked_key_id"] == 7
