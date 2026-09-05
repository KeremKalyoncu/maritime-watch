import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg(tmp_path):
    """The real config.yaml, not a hand-copy of it.

    A separate fixture dict drifts: it kept a `course_change_deg` that no longer
    existed, and every threshold the deployment actually runs on went untested.
    """
    c = yaml.safe_load((ROOT / "config.yaml").read_text("utf-8"))
    c["_root"] = str(tmp_path)
    c["secrets"] = {"aisstream_key": "", "telegram_token": "", "telegram_chat_id": ""}
    return c
