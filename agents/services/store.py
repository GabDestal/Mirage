import copy
import json
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "data" / "seed.json"
_state = None


def state() -> dict:
    global _state
    if _state is None:
        reset()
    return _state


def reset(seed: dict | None = None) -> None:
    global _state
    _state = copy.deepcopy(seed) if seed is not None else json.loads(SEED.read_text())
    _state.setdefault("outbox", [])
