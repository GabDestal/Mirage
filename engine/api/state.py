"""Runs and incidents, folded from the event log. One source of truth for both modes.

Live mode folds the whole SQLite log, so the API sees runs from every process (SDK agents, the
dev runner, `mirage detonate`) and keeps them across restarts. Replay mode folds the events
played so far.
"""

from contracts.models import BisectionRow, Incident, Run, Verdict

NEXT_ACTION = {"open": "detonate", "confirmed": "find_cause", "root_caused": "send_fix",
               "fix_verified": "open_pr"}  # any other status: "none"
INCIDENT_STATUS = {"detonation.started": "detonating", "detonation.failed": "open",
                   "bisection.step": "bisecting", "bisection.completed": "root_caused",
                   "handoff.created": "fix_pending", "fix.verified": "fix_verified",
                   "pr.opened": "pr_open"}


def fold(events):
    """(runs, incidents) as contract models, keyed by id."""
    runs, incidents, gates = {}, {}, {}
    for e in events:
        p = e.payload
        run = runs.get(e.run_id)
        if e.type == "run.started":
            runs[e.run_id] = Run(id=e.run_id, agent=p.get("agent", "agent"), env=e.env,
                                 task=p["task"], status=p.get("status", "running"),
                                 started_at=e.ts, restarted_from=p.get("restarted_from"))
        elif e.type == "run.status" and run:
            run.status = p["to"]
            run.incident_id = e.incident_id or run.incident_id
            if p["to"] in ("completed", "killed", "halted"):
                run.ended_at = e.ts
        elif e.type == "tool.requested" and run:
            run.tool_calls += 1
        elif e.type == "gate.decision":
            gates[p["call_id"]] = p
        elif e.type == "incident.opened":
            incidents[p["incident_id"]] = Incident(
                id=p["incident_id"], run_id=e.run_id, status="open", opened_at=e.ts,
                trigger=gates[p["trigger_call_id"]], inputs=p.get("inputs", []),
                snapshot_id=f"snap_{p['incident_id'].removeprefix('inc_')}")
        elif (inc := incidents.get(e.incident_id)) is not None:
            if e.type == "detonation.started" and (p.get("removed_input_id")
                                                   or p.get("purpose") == "verify"):
                continue  # bisection's or a fix check's own detonation, not a new verdict
            if e.type == "fix.verified" and not p.get("passed", True):
                continue  # the fix failed: the incident stays where it was
            inc.status = INCIDENT_STATUS.get(e.type, inc.status)
            if e.type == "verdict.ready":
                inc.verdict = Verdict.model_validate(p)
                inc.status = "confirmed" if p["confirmed"] else "false_positive"
            elif e.type == "bisection.step":
                inc.bisection.append(BisectionRow.model_validate(p))
            elif e.type == "bisection.completed":
                inc.cause_input_id = p["cause_input_id"]
                if not p["cause_input_id"]:  # no single proven cause: offer "find cause" again
                    inc.status = "confirmed"
            elif e.type == "pr.opened":
                inc.pr_url = p["url"]
    for inc in incidents.values():
        inc.next_action = NEXT_ACTION.get(inc.status, "none")
    return runs, incidents
