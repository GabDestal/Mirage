from agents.services.store import state


def inbox() -> list[dict]:
    return state()["inbox"]


def send(to: str, subject: str, body: str) -> str:
    outbox = state()["outbox"]
    outbox.append({"to": to, "subject": subject, "body": body})
    return f"sent email #{len(outbox)} to {to}"
