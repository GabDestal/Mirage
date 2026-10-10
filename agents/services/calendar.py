from agents.services.store import state


def events(day: str | None = None) -> list[dict]:
    return [e for e in state()["calendar"] if day is None or e["start"].startswith(day)]
