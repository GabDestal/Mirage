"""Validate every chat wire example against the shared Pydantic contract."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pydantic import TypeAdapter, ValidationError
from contracts.models import ChatApproval, ChatApprovalAccepted, ChatEvent, ChatTurn

adapter = TypeAdapter(ChatEvent)
fixture = Path(__file__).resolve().parents[2] / "contracts/fixtures/chat_demo.jsonl"
examples = [json.loads(line) for line in fixture.read_text().splitlines()]
for example in examples:
    assert adapter.validate_python(example).model_dump(mode="json", by_alias=True, exclude_none=True) == example
assert len({event["type"] for event in examples}) == 8
ChatTurn(message="Which run is frozen?", actor="liam")
ChatApproval(action="accept", content={"confirm": "kill run_002", "reason": "Contained"})
ChatApprovalAccepted(accepted=True)
for invalid in [{"message": "x", "actor": "liam", "history": []}, {"message": "x" * 8001, "actor": "liam"}]:
    try:
        ChatTurn.model_validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid chat input was accepted")
print(f"Validated {len(examples)} chat events and request trust boundaries")
