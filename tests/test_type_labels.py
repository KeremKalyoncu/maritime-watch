"""R17: an AIS gap is 'signal lost', never a 'distress call' on the public map."""

import importlib.util
from pathlib import Path

from src.model import TYPE_TR, IncidentType

_spec = importlib.util.spec_from_file_location("mw_run_types", Path(__file__).resolve().parents[1] / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def test_ais_gap_is_signal_lost_not_distress():
    assert run._TYPE_FOR["ais-gap"] == "signal-lost"
    assert IncidentType("signal-lost") is IncidentType.SIGNAL_LOST
    assert TYPE_TR["signal-lost"] == "AIS sinyali kesildi"


def test_real_distress_sources_still_distress():
    assert run._TYPE_FOR["ais-sart"] == "distress"


def test_every_mapped_type_has_a_turkish_label():
    for t in run._TYPE_FOR.values():
        assert t in TYPE_TR, t


def test_map_knows_the_new_type():
    js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
    assert '"signal-lost": "AIS sinyali kesildi"' in js
    assert '"signal-lost": "AIS signal lost"' in js
