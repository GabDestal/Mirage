"""Outreach-only CRM features on top of the shared fake services: new contacts, activity log, scheduled follow-ups."""
from agents.services import crm
from agents.services.store import state


def create_contact(name: str, email: str, company: str, stage: str, notes: str) -> dict:
    contacts = state()["contacts"]
    contact = {"id": f"c_{len(contacts) + 1:03d}", "name": name, "email": email,
               "company": company, "stage": stage, "notes": notes}
    contacts.append(contact)
    return contact


def log_activity(contact_id: str, kind: str, summary: str) -> str:
    if crm.get(contact_id) is None:
        return f"no contact {contact_id}"
    state().setdefault("activities", []).append({"contact_id": contact_id, "kind": kind, "summary": summary})
    return f"logged {kind} for {contact_id}"


def activities(contact_id: str) -> list[dict]:
    return [a for a in state().get("activities", []) if a["contact_id"] == contact_id]


def schedule_email(contact_id: str, to: str, send_on: str, subject: str, body: str) -> str:
    contact = crm.get(contact_id)
    if contact is None:
        raise ValueError(f"no contact {contact_id}")
    if not to.strip() or to != contact.get("email"):
        raise ValueError(f"cannot schedule {contact_id}: recipient must match the contact's nonempty CRM email")
    scheduled = state().setdefault("scheduled", [])
    scheduled.append({"contact_id": contact_id, "to": to, "send_on": send_on,
                      "subject": subject, "body": body})
    return f"scheduled email #{len(scheduled)} to {to} on {send_on}"
