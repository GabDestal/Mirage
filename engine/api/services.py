"""Service panels (GET /services/{outbox|calendar|crm}?env=prod|mirage), folded from the event log.

prod:   outbox = emails the gate let run (normal) and the ones it froze or blocked (blocked: never
        sent). calendar / crm = what the agents read.
mirage: outbox = what the main detonation would have sent (malicious if it broke a rule).
        calendar / crm = the frozen run's inputs (its snapshot).
The input bisection proved to be the cause is flagged malicious. Works in live and replay mode,
and sees agents in any process, because it only reads events.
"""

from contracts.models import ServiceItem, ServiceView
from engine.api.state import fold

KIND = {"calendar": "calendar_event", "crm": "crm_record"}


def _service_of(tool):
    if "calendar" in tool:
        return "calendar"
    if "contact" in tool or "crm" in tool:
        return "crm"
    return None


def _records(result):
    """The records inside a tool result: a list, or the one list inside a dict."""
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        lists = [v for v in result.values() if isinstance(v, list)]
        return [r for r in lists[0] if isinstance(r, dict)] if len(lists) == 1 else []
    return []


def _text(record, *keys):
    return next((str(record[k]) for k in keys if record.get(k)), "")


def _is_cause(record, title, causes):
    """The record is the proven cause: same label, or its text starts like the cause's preview."""
    text = _text(record, "description", "body", "notes", "email")
    return any(title == c.label or (c.preview and text.startswith(c.preview[:80])) for c in causes)


def _record_item(service, record, ts, causes):
    if service == "calendar":
        title = _text(record, "title", "summary") or "(untitled event)"
        people = record.get("attendees") or []
        subtitle = " · ".join(x for x in [_text(record, "start"), _text(record, "organizer"),
                                         f"{len(people)} attendees" if people else ""] if x)
    else:
        title = _text(record, "name", "email") or "(contact)"
        subtitle = " · ".join(x for x in [_text(record, "email"), _text(record, "company")] if x)
    key = _text(record, "id", "email") or title
    return ServiceItem(id=f"{service}:{key}", title=title, subtitle=subtitle, ts=ts,
                       flag="malicious" if _is_cause(record, title, causes) else "normal")


def _email_item(item_id, args, ts, flag, note=""):
    if args.get("send_on") and flag != "blocked":
        note = f"scheduled for {args['send_on']}" + (f" · {note}" if note else "")
    return ServiceItem(id=item_id, title=str(args.get("subject") or "(no subject)"),
                       subtitle=f"to {args.get('to')}" + (f" · {note}" if note else ""),
                       ts=ts, flag=flag)


def view(events, service, env) -> ServiceView:
    _, incidents = fold(events)
    causes = [i for inc in incidents.values() for i in inc.inputs if i.id == inc.cause_input_id]
    requested, decisions, items, seen = {}, {}, [], set()

    def add(item):
        if item.id not in seen:
            seen.add(item.id)
            items.append(item)
        elif item.flag == "normal":  # a held call a human released, which then ran: it was sent
            items[:] = [item if i.id == item.id else i for i in items]

    main_detonations = set()
    for e in events:
        p = e.payload
        if e.type == "tool.requested":
            requested[p["call_id"]] = p
        elif e.type == "gate.decision":
            decisions[p["call_id"]] = p
            if env == "prod" and service == "outbox" and "to" in p["args"] \
                    and p["decision"] in ("freeze", "block"):
                add(_email_item(p["call_id"], p["args"], e.ts, "blocked",
                                f"{p['decision']} {p['rule_id'] or ''}".strip()))
        elif e.type == "tool.result" and env == "prod" and p.get("error") is None:
            args = requested.get(p["call_id"], {}).get("args", {})
            if service == "outbox" and "to" in args:
                released = p["call_id"] in seen  # it was held first, then a human released it
                note = ("after a human unfroze the run" if args.get("send_on")
                        else "sent after a human unfroze the run") if released else ""
                add(_email_item(p["call_id"], args, e.ts, "normal",
                                note))
            elif _service_of(p["tool"]) == service:
                for record in _records(p["result"]):
                    add(_record_item(service, record, e.ts, causes))
        elif e.type == "detonation.started" and not p.get("removed_input_id") \
                and p.get("purpose", "detonate") == "detonate":
            main_detonations.add(p["detonation_id"])
        elif e.type == "detonation.effect" and env == "mirage" and service == "outbox" \
                and p["detonation_id"] in main_detonations and "to" in p["args"] \
                and p.get("error") is None:
            add(_email_item(f"{p['detonation_id']}:{p['run_index']}:{p['step']}", p["args"],
                            e.ts, "malicious" if p["violates"] else "normal",
                            f"replay {p['run_index']}"))

    if env == "mirage" and service in KIND:  # the frozen runs' inputs (their snapshots)
        for inc in incidents.values():
            for i in inc.inputs:
                if i.kind == KIND[service]:
                    add(ServiceItem(id=f"{service}:{inc.id}:{i.id}", title=i.label,
                                    subtitle=i.preview[:120], ts=inc.opened_at,
                                    flag="malicious" if i.id == inc.cause_input_id else "normal"))
    return ServiceView(service=service, env=env, items=items)
