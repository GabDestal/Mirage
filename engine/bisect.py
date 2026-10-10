"""Bisection: prove which input caused the compromise (PRODUCT.md §5).

For each untrusted input the run read, detonate the snapshot without it. The input whose removal
drops the attack to 0 is the cause. Same sandbox, same code verdict, so the grid is evidence.
Each removal reruns from the start (snapshot.without clears the recorded model replies).

shortcut: only untrusted inputs are tested (content anyone outside can write). The user's task
and internal CRM records are trusted; testing 40 contacts one by one would take minutes on stage.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from contracts.models import BisectionRow
from engine.detonation import snapshot
from engine.detonation.sandbox import detonate
from engine.store.events import emit

UNTRUSTED = {"calendar_event", "email", "web_page", "attachment"}


def bisect(incident_id, runs_per_input=2, log=print):
    """Emits one bisection.step per input (as each finishes, so the grid fills live), then
    bisection.completed. Returns (rows in input order, cause_id).
    MIRAGE_PARALLEL=N tests N inputs at once (each detonation also runs its replays at once)."""
    snap = snapshot.load(incident_id)
    candidates = [i for i in snap["inputs"] if i["kind"] in UNTRUSTED]
    log(f"Bisecting {incident_id}: {len(candidates)} untrusted inputs x{runs_per_input} runs")

    def test(inp):
        detonation, _, _ = detonate(incident_id, runs_per_input, removed_input_id=inp["id"],
                                    log=lambda *_: None)
        compromised = detonation.compromised_runs
        return BisectionRow(input_id=inp["id"], label=inp["label"],
                            compromised_runs=f"{compromised}/{runs_per_input}",
                            is_cause=compromised == 0)

    workers = max(1, int(os.getenv("MIRAGE_PARALLEL", "1")))
    done = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(test, inp) for inp in candidates]):
            row = future.result()
            done[row.input_id] = row
            emit("bisection.step", row.model_dump(mode="json"), incident_id=incident_id,
                 env="mirage")
            log(f"  without {row.input_id} ({row.label[:40]}): {row.compromised_runs} "
                "compromised" + ("  <- CAUSE" if row.is_cause else ""))
    rows = [done[inp["id"]] for inp in candidates]

    causes = [r.input_id for r in rows if r.is_cause]
    cause = causes[0] if len(causes) == 1 else None  # 0 or several: no single proven cause
    emit("bisection.completed", {"incident_id": incident_id, "cause_input_id": cause},
         incident_id=incident_id, env="mirage")
    return rows, cause
