"""Replay mode (CONTRACTS.md §7): play a recorded demo through the same API, no agents needed.

The fixture is cut into segments, one per operator step: detonate, find the cause, handoff,
check a fix, and each other human action (kill, unfreeze, restart...). A POST action plays the
next segment with its recorded timing; anything still pending in the current one shows at once,
so `seq` order never breaks. Works for a hand-written fixture and for a real recorded run (where
bisection's own detonations belong to the "find the cause" step). Runs and incidents are folded
from the events played so far (state.py), the same fold live mode uses.
"""

import math
import time
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
    def __init__(self, path, speed=1.0):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        events = [Event.model_validate_json(line) for line in lines if line.strip()]
        self.events = [e.model_copy(update={"seq": n}) for n, e in enumerate(events, start=1)]
        self.starts = segment_starts(self.events)
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
        return fold(self.visible())
