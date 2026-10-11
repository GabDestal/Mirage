"""Runs and incidents, folded from the event log. One source of truth for both modes.

Live mode folds the whole SQLite log, so the API sees runs from every process (SDK agents, the
dev runner, `mirage detonate`) and keeps them across restarts. Replay mode folds the events
played so far.
"""

from contracts.models import BisectionRow, Incident, RepairJob, Run, SandboxJob, Verdict

NEXT_ACTION = {"open": "detonate", "confirmed": "find_cause", "root_caused": "send_fix",
               "fix_verified": "open_pr"}  # any other status: "none"
INCIDENT_STATUS = {"detonation.started": "detonating",
                   "bisection.step": "bisecting", "bisection.completed": "root_caused",
                   "handoff.created": "fix_pending", "fix.verified": "fix_verified",
                   "pr.opened": "pr_open", "recovery.prepared": "merged"}


def repair_jobs(events):
    """Public repair progress is durable; private prompts and ledgers are never projected."""
    jobs = {}
    for event in events:
        if event.type == "repair.job.updated":
            job = RepairJob.model_validate(event.payload)
            jobs[job.id] = job
    return jobs


def fold(events):
    """(runs, incidents) as contract models, keyed by id."""
    runs, incidents, gates, before_detonation = {}, {}, {}, {}
    bisection_active = set()
    for e in events:
        p = e.payload
        run = runs.get(e.run_id)
        if e.type == "run.started":
            runs[e.run_id] = Run(id=e.run_id, agent=p.get("agent", "agent"), env=e.env,
                                 task=p["task"], status=p.get("status", "running"),
                                 started_at=e.ts, restarted_from=p.get("restarted_from"),
                                 rule_revision=p.get("rule_revision"))
        elif e.type == "run.status" and run:
            if p["from"] == "frozen" and p["to"] == "running" and run.incident_id in incidents:
                incidents[run.incident_id].status = "closed"  # a human judged it a false positive
            run.status = p["to"]
            run.status_reason = p.get("reason")
            run.incident_id = e.incident_id or run.incident_id
            if p["to"] in ("completed", "failed", "killed", "halted"):
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
            if "sandbox_job" in p:
                inc.sandbox_job = SandboxJob.model_validate(p["sandbox_job"])
                p = {key: value for key, value in p.items() if key != "sandbox_job"}
            if e.type == "bisection.step" or (e.type == "detonation.started"
                                             and p.get("removed_input_id")):
                if inc.id not in bisection_active:
                    inc.bisection = []
                    inc.cause_input_id = None
                    bisection_active.add(inc.id)
                inc.status = "bisecting"
            if e.type == "detonation.started":
                if p.get("removed_input_id") or p.get("purpose") == "verify":
                    continue  # bisection/fix checks do not replace the baseline verdict
                before_detonation[(inc.id, p.get("detonation_id"))] = inc.status
            if e.type == "detonation.failed":
                if p.get("purpose") != "verify" and inc.status == "detonating":
                    inc.status = before_detonation.get((inc.id, p.get("detonation_id")),
                        "confirmed" if inc.verdict and inc.verdict.confirmed else "open")
                continue  # a scheduling/verification failure cannot erase proven progress
            if e.type == "fix.verified" and not p.get("passed", True):
                continue  # the fix failed: the incident stays where it was
            if e.type == "bisection.completed":
                if inc.id not in bisection_active:
                    inc.bisection = []  # this attempt failed/finished before producing a row
                bisection_active.discard(inc.id)
            inc.status = INCIDENT_STATUS.get(e.type, inc.status)
            if e.type == "verdict.ready":
                inc.verdict = Verdict.model_validate(p)
                inc.status = "confirmed" if p["confirmed"] else "false_positive"
                inc.bisection = []
                inc.cause_input_id = None
                bisection_active.discard(inc.id)
            elif e.type == "bisection.step":
                inc.bisection = [r for r in inc.bisection if r.input_id != p["input_id"]]
                inc.bisection.append(BisectionRow.model_validate(p))
            elif e.type == "bisection.completed":
                inc.cause_input_id = p["cause_input_id"]
                if not p["cause_input_id"]:  # no single proven cause: offer "find cause" again
                    inc.status = "confirmed"
            elif e.type == "pr.opened":
                inc.pr_url = p["url"]
    for inc in incidents.values():
        inc.next_action = NEXT_ACTION.get(inc.status, "none")
        order = {i.id: n for n, i in enumerate(inc.inputs)}  # rows may finish in any order
        inc.bisection.sort(key=lambda r: (order.get(r.input_id, len(order)), r.input_id))
    return runs, incidents
