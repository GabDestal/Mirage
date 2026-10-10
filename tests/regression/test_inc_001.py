"""Regression for Mirage incident inc_001: the calendar-invite injection must stay blocked.

Reruns the current meeting_assistant code 3 times in the sandbox against the frozen snapshot.
Calls Bedrock, so it skips without AWS_BEARER_TOKEN_BEDROCK.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from engine import cli
from engine.detonation import snapshot

HERE = Path(__file__).parent
load_dotenv()


@pytest.mark.skipif(not os.getenv("AWS_BEARER_TOKEN_BEDROCK"), reason="calls Bedrock")
def test_inc_001_fix_is_verified(monkeypatch):
    monkeypatch.setenv("MIRAGE_SNAPSHOTS", str(HERE))
    monkeypatch.setattr(snapshot, "SNAP_DIR", HERE)  # read at import; conftest points it at tmp
    assert cli.main(["detonate", "--incident", "inc_001"]) == 0
