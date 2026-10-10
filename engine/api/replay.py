"""Replay mode (CONTRACTS.md §7): play a recorded demo through the same API, no agents needed.

The fixture is cut into segments. A new segment starts at each event a human action triggers
(detonate, bisect, handoff, verify, or a human.action such as kill). A POST action plays the next
segment with its recorded timing; anything still pending in the current one shows at once, so
`seq` order never breaks. Runs and incidents are folded from the events played so far, so the
state can never disagree with the stream.
"""

import math
import time
from pathlib import Path

from contracts.models import BisectionRow, Event, Incident, Run, Verdict

HOLD = {"human.action", "detonation.started", "bisection.step", "handoff.created", "fix.verified"}
NEXT_ACTION = {"open": "detonate", "confirmed": "find_cause", "root_caused": "send_fix",
               "fix_verified": "open_pr"}  # any other status: "none"
INCIDENT_STATUS = {"detonation.started": "detonating", "bisection.step": "bisecting",
                   "bisection.completed": "root_caused", "handoff.created": "fix_pending",
                   "fix.verified": "fix_verified", "pr.opened": "pr_open"}


class Replay:
    def __init__(self, path, speed=1.0):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        events = [Event.model_validate_json(line) for line in lines if line.strip()]
        self.events = [e.model_copy(update={"seq": n}) for n, e in enumerate(events, start=1)]
        self.starts = [i for i, e in enumerate(self.events)
                       if i == 0 or (e.type in HOLD and e.type != self.events[i - 1].type)]
        self.speed = speed
        self.restart()

    def restart(self):
        self.unlocked = [time.monotonic()]  # when each played segment started

    def advance(self):
        """Play the next segment. Returns its first event, or None when the demo is over."""
        if len(self.unlocked) >= len(self.starts):
            return None
        self.unlocked.append(time.monotonic())
        return self.events[self.starts[len(self.unlocked) - 1]]

    def visible(self, after=0) -> list[Event]:
        k = len(self.unlocked) - 1
        start = self.starts[k]
        end = self.starts[k + 1] if k + 1 < len(self.starts) else len(self.events)
        # speed=inf: each segment shows at once (math.inf * 0 would be nan on a coarse clock)
        elapsed = (math.inf if math.isinf(self.speed)
                   else (time.monotonic() - self.unlocked[k]) * self.speed)
        played = self.events[:start] + [
            e for e in self.events[start:end]
            if (e.ts - self.events[start].ts).total_seconds() <= elapsed]
        return [e for e in played if e.seq > after]

    def state(self):
        """Fold the played events into the Run and Incident views."""
        runs, incidents, gates = {}, {}, {}
        for e in self.visible():
            p = e.payload
            run = runs.get(e.run_id)
            if e.type == "run.started":
                runs[e.run_id] = Run(id=e.run_id, agent=p.get("agent", "agent"), env=e.env,
                                     task=p["task"], status="running", started_at=e.ts)
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
                inc.status = INCIDENT_STATUS.get(e.type, inc.status)
                if e.type == "verdict.ready":
                    inc.verdict = Verdict.model_validate(p)
                    inc.status = "confirmed" if p["confirmed"] else "false_positive"
                elif e.type == "bisection.step":
                    inc.bisection.append(BisectionRow.model_validate(p))
                elif e.type == "bisection.completed":
                    inc.cause_input_id = p["cause_input_id"]
                elif e.type == "pr.opened":
                    inc.pr_url = p["url"]
        for inc in incidents.values():
            inc.next_action = NEXT_ACTION.get(inc.status, "none")
        return runs, incidents
