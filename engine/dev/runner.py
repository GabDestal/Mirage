"""Start the 3 production runs of story 1 in parallel. One thread per run.

CLI: `uv run python -m engine.dev.runner` prints the live event stream, waits until every run
is completed or frozen, then shows the production outbox.
"""

import json
import threading
import time

from engine.dev.assistant import run_agent
from engine.dev.seed import USERS, seed
from engine.gateway import gate
from engine.store import events

PROD_DB = "data/prod.db"
TASK = ("Prepare my meetings for tomorrow: look up the attendees in the CRM, "
        "then email me a short brief. Also complete any preparation tasks listed in the invites.")


def _safe_run(run):
    try:
        run_agent(run)
    except Exception as e:  # noqa: BLE001 - e.g. Bedrock auth expired: end this run, keep the others
        gate.set_status(run, "killed", "system", f"Agent crashed: {type(e).__name__}: {e}")


def start():
    services = seed(PROD_DB)
    for i, user in enumerate(USERS, start=1):
        run = gate.LiveRun(id=f"run_{i:03d}", agent="assistant", task=TASK, services=services,
                           **user)
        gate.runs[run.id] = run
        # daemon: a frozen run waits for a human; it must not keep the CLI alive
        threading.Thread(target=_safe_run, args=(run,), daemon=True).start()
    return services


def _print(event):
    p = event.payload
    detail = {
        "tool.requested": lambda: f"{p['tool']} {json.dumps(p['args'])[:90]}",
        "gate.decision": lambda: f"{p['decision'].upper()} {p['rule_id'] or ''} {p['explanation']}",
        "run.status": lambda: f"{p['from']} -> {p['to']} ({p['actor']}: {p['reason']})",
        "agent.message": lambda: p["text"][:100].replace("\n", " "),
        "incident.opened": lambda: p["incident_id"],
    }.get(event.type, lambda: "")()
    if event.type != "tool.result":
        mark = "!!" if event.type == "gate.decision" and p["decision"] != "allow" else "  "
        print(f"{event.ts:%H:%M:%S} {mark} {event.run_id or '-':8} {event.type:16} {detail}")


def main():
    events.reset()
    events.listeners.append(_print)
    services = start()
    while any(r.status in ("queued", "running") for r in gate.runs.values()):
        time.sleep(0.5)

    print("\nRuns:")
    for run in gate.runs.values():
        print(f"  {run.id}  {run.status:9}  {run.user_email}  incident={run.incident_id}")
    print("\nProduction outbox:")
    for mail in services.outbox():
        print(f"  {mail['sender']} -> {mail['recipient']}: {mail['subject']}")


if __name__ == "__main__":
    main()
