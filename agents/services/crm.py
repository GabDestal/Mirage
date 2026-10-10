from agents.services.store import state


def search(query: str = "") -> list[dict]:
    q = query.lower()
    return [c for c in state()["contacts"] if q in json_text(c)]


def get(contact_id: str) -> dict | None:
    return next((c for c in state()["contacts"] if c["id"] == contact_id), None)


def update(contact_id: str, **fields) -> str:
    contact = get(contact_id)
    if contact is None:
        return f"no contact {contact_id}"
    contact.update(fields)
    return f"updated {contact_id}"


def export_all() -> list[dict]:
    return state()["contacts"]


def json_text(c: dict) -> str:
    return " ".join(str(v) for v in c.values()).lower()
