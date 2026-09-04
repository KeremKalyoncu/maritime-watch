"""The eval harness must run and clear its F1 floor."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parent.parent / "eval" / "run_eval.py"
)
run_eval = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_eval)


def test_eval_sections_pass():
    for name, (p, r, f), *_ in (run_eval.eval_news(), run_eval.eval_extract(), run_eval.eval_anomaly()):
        assert f >= 0.75, f"{name} F1 {f:.2f} below floor"


def test_eval_main_writes_report(tmp_path, monkeypatch):
    assert run_eval.main() == 0
    assert (Path(run_eval.__file__).parent / "REPORT.md").exists()
