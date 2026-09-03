"""tf-doctor checks the daily Skill update schedule without exposing data."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path


DOCTOR_PATH = Path(__file__).parent.parent / "shims" / "wrapper" / "tf-doctor"
loader = importlib.machinery.SourceFileLoader("tf_doctor_test_module", str(DOCTOR_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
doctor = importlib.util.module_from_spec(spec)
loader.exec_module(doctor)


def test_skill_auto_update_check_reports_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    (tmp_path / "tf_skill_update.py").write_text("# runner\n", encoding="utf-8")

    class Result:
        stdout = json.dumps({
            "enabled": True,
            "status": "installed",
            "scheduler": "launchd",
            "tfs_found": True,
            "last_result": "updated",
            "backup_run": "20260903T120000Z",
        })

    monkeypatch.setattr(doctor.subprocess, "run", lambda *_args, **_kwargs: Result())

    result = doctor.check_skill_auto_update()

    assert result["status"] == doctor.PASS
    assert "launchd" in result["detail"]
    assert "20260903T120000Z" in result["detail"]


def test_skill_auto_update_check_warns_when_runner_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)

    result = doctor.check_skill_auto_update()

    assert result["status"] == doctor.WARN
    assert "tf_skill_update.py" in result["detail"]
