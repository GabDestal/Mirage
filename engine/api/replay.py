"""Replay mode (CONTRACTS.md §7): play a recorded demo through the same API, no agents needed.

The fixture is cut into segments, one per operator step: detonate, find the cause, handoff,
check a fix, and each other human action (kill, unfreeze, restart...). A POST action plays the
next segment with its recorded timing; anything still pending in the current one shows at once,
so `seq` order never breaks. Works for a hand-written fixture and for a real recorded run (where
bisection's own detonations belong to the "find the cause" step). Runs and incidents are folded
from the events played so far (state.py), the same fold live mode uses.
Managed mode auto-plays the baseline, gates human stages, and pauses only the recording on STOP.
"""

import math
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import Event
from engine.api.state import fold

STEP_OF = {"bisection.step": "bisect", "handoff.created": "handoff", "fix.verified": "verify"}
AUDITED = {"handoff": "handoff", "detonate": "detonate", "find_cause": "bisect", "verify": "verify"}


def step_of(event):
    """The operator step an event starts or belongs to; None if it just follows the current one."""
    p = event.payload
    if event.type == "detonation.started":
        return ("verify" if p.get("purpose") == "verify"
                else "bisect" if p.get("removed_input_id") else "detonate")
    if event.type == "human.action":  # an audit record opens the step it records (one click)
        return AUDITED.get(p.get("action"), f"human-{event.seq}")
    return STEP_OF.get(event.type)


def segment_starts(events):
    starts, current = [0], None
    for i, e in enumerate(events):
        step = step_of(e)
        if step and step != current:
            if i:
                starts.append(i)
            current = step
    return starts


class Replay:
    def __init__(self, path, speed=1.0, *, managed=False):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        events = [Event.model_validate_json(line) for line in lines if line.strip()]
        self.recorded = events
        self.managed = managed
        self.lock = threading.RLock()
        self.speed = speed
        self.restart()

    def restart(self):
        with self.lock:
            self.events = [e.model_copy(deep=True, update={"seq": n})
                           for n, e in enumerate(self.recorded, start=1)]
            if self.managed:
                for e in self.events:
                    if e.type == "handoff.created":
                        e.payload = {key: value for key, value in e.payload.items()
                                     if key in ("incident_id", "claude_code_url", "codex_url")}
                        e.payload["prompt"] = (
                            f"Recorded demo only: incident {e.incident_id}. Inspect the recorded "
                            "calendar injection, effects ledger and bisection evidence. This is "
                            "not a live coding handoff: there is no usable live snapshot, incident "
                            "token or capability. Do not run mirage detonate against this incident. "
                            "No fix has been written or tested by this handoff; the next verification "
                            "and PR are recorded examples, not evidence about current code.")
                    elif e.type == "pr.opened":
                        e.payload["url"] = ("https://example.invalid/recorded-demo/pr/"
                                            f"{e.payload.get('number', 42)}")
            self.starts = segment_starts(self.events)
            if self.managed:
                # Baseline detonation is automatic; PR evidence is its own operator step.
                self.starts = [0]
                current = None
                for i, e in enumerate(self.events):
                    step = self._managed_step(e)
                    if step and step != current:
                        if i:
                            self.starts.append(i)
                        current = step
            self.unlocked = [time.monotonic()]  # when each played segment started
            self.paused_at = None

    def pause(self, body, *, lift=False):
        """STOP pauses this recording's clock, without touching production tokens or runs."""
        with self.lock:
            if lift != (self.paused_at is not None):
                raise ValueError("Recorded demo is already playing" if lift else "Recorded demo is stopped")
            now = time.monotonic()
            played = self.visible()
            ts = played[-1].ts if played else self.events[0].ts
            action = "lift_stop" if lift else "global_stop"
            added = [Event(seq=0, ts=ts, env="prod", type="human.action", payload={
                "actor": body.actor, "action": action, "target": "all", "reason": body.reason,
                "ts": datetime.now(UTC).isoformat()}),
                Event(seq=0, ts=ts, env="prod",
                      type="global.stop_lifted" if lift else "global.stop",
                      payload={"actor": body.actor, "reason": body.reason})]
            position = len(played)
            self.events[position:position] = added
            self.starts = [i + len(added) if i >= position and i != 0 else i for i in self.starts]
            self.events = [e.model_copy(update={"seq": n})
                           for n, e in enumerate(self.events, start=1)]
            if lift:
                self.unlocked[-1] += now - self.paused_at
                self.paused_at = None
            else:
                self.paused_at = now

    @staticmethod
    def _managed_step(event):
        step = "pr" if event.type == "pr.opened" else step_of(event)
        return None if step == "detonate" else step

    def advance_for(self, incident_id, step, body=None, *, pr_url=None, runs=None):
        """Managed mode: only the matching action can unlock a completed stage's successor."""
        with self.lock:
            if self.paused_at is not None:
                raise ValueError("Recorded demo is stopped; lift STOP before advancing")
            k = len(self.unlocked)
            if k >= len(self.starts):
                raise ValueError("Recorded demo is complete; reset to play again")
            start = self.starts[k]
            head = self.events[start]
            target = head.incident_id or head.payload.get("target")
            if self._managed_step(head) != step or target != incident_id:
                raise ValueError("Action does not match the next recorded incident stage")
            played = self.visible()
            if not played or played[-1].seq != start:
                raise ValueError("Current recorded stage is still playing; wait for its result")
            end = self.starts[k + 1] if k + 1 < len(self.starts) else len(self.events)
            segment = self.events[start:end]
            if runs is not None:
                counts = {e.payload["n_runs"] for e in segment if e.type == "detonation.started"}
                if step == "bisect":
                    counts.update(int(e.payload["compromised_runs"].split("/")[1])
                                  for e in segment if e.type == "bisection.step")
                if counts != {runs}:
                    raise ValueError("Requested run count does not match the recorded evidence")
            result = {"incident_id": incident_id,
                      "status": "bisecting" if step == "bisect" else "verifying"}
            if step == "handoff":
                result = next((e.payload.copy() for e in segment if e.type == "handoff.created"), None)
                if result is None:
                    raise ValueError("Fixture has no recorded handoff for this stage")
            if step == "pr" and pr_url != head.payload.get("url"):
                raise ValueError("Only the recorded demo PR URL can be acknowledged; no PR is created")
            if step != "pr":
                now = datetime.now(UTC).isoformat()
                audit = Event(seq=0, ts=head.ts, env="prod", incident_id=incident_id,
                              type="human.action", payload={
                                  "actor": body.actor if body else "unknown",
                                  "action": "find_cause" if step == "bisect" else step,
                                  "target": incident_id,
                                  "reason": body.reason if body else "(no reason given)", "ts": now})
                if head.type == "human.action":
                    self.events[start] = audit
                else:
                    self.events.insert(start, audit)
                    self.starts = [i + 1 if i > start else i for i in self.starts]
                self.events = [e.model_copy(update={"seq": n})
                               for n, e in enumerate(self.events, start=1)]
            self.unlocked.append(time.monotonic())
            if step == "pr":
                return head.payload.copy()
            return result

    def advance(self):
        """Play the next segment. Returns its first event, or None when the demo is over."""
        if len(self.unlocked) >= len(self.starts):
            return None
        self.unlocked.append(time.monotonic())
        return self.events[self.starts[len(self.unlocked) - 1]]

    def visible(self, after=0) -> list[Event]:
        with self.lock:
            return self._visible(after)

    def _visible(self, after=0) -> list[Event]:
        k = len(self.unlocked) - 1
        start = self.starts[k]
        end = self.starts[k + 1] if k + 1 < len(self.starts) else len(self.events)
        # speed=inf: each segment shows at once (math.inf * 0 would be nan on a coarse clock)
        elapsed = (math.inf if math.isinf(self.speed)
                   else ((self.paused_at if self.paused_at is not None else time.monotonic())
                         - self.unlocked[k]) * self.speed)
        pending = []
        for e in self.events[start:end]:
            if (e.ts - self.events[start].ts).total_seconds() <= elapsed:
                pending.append(e)
            elif self.managed:
                break  # never publish a cursor past an event that has not played yet
        played = self.events[:start] + pending
        return [e for e in played if e.seq > after]

    def state(self):
        with self.lock:
            runs, incidents = fold(self.visible())
            if self.managed and self.paused_at is not None:
                # Historical evidence stays intact; halted here means the recording is paused.
                runs = {key: run.model_copy(update={"status": "halted"})
                        if run.status in ("running", "queued", "frozen") else run
                        for key, run in runs.items()}
            return runs, incidents
