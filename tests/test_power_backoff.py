"""The engine loop backs off on a hot or nearly flat edge phone."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mw_run", Path(__file__).resolve().parents[1] / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

CFG = {"loop": {"hot_temp_c": 45.0, "low_battery_pct": 15}}


def _battery(tmp_path, temp="300", status="Charging", capacity="80"):
    (tmp_path / "temp").write_text(temp)
    (tmp_path / "status").write_text(status)
    (tmp_path / "capacity").write_text(capacity)
    return tmp_path


def test_healthy_phone_no_backoff(tmp_path):
    assert run.power_backoff_reason(CFG, _battery(tmp_path)) is None


def test_hot_phone_backs_off(tmp_path):
    assert "46.0" in run.power_backoff_reason(CFG, _battery(tmp_path, temp="460"))


def test_flat_battery_backs_off_only_when_discharging(tmp_path):
    assert run.power_backoff_reason(CFG, _battery(tmp_path, status="Discharging", capacity="12"))
    assert run.power_backoff_reason(CFG, _battery(tmp_path, status="Charging", capacity="12")) is None


def test_no_battery_sysfs_is_noop(tmp_path):
    assert run.power_backoff_reason(CFG, tmp_path / "missing") is None
