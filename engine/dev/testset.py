"""Build a labelled test set with the real agent, then print the metrics (PRODUCT.md §11 step 14).

    uv run python -m engine.dev.testset [--clean 10] [--poisoned 10] [--detonate 3] [--port 8010]

Runs Liam's meeting assistant through the SDK, one run at a time, against a fresh engine:
poisoned runs use his eval's attack variants (V1..V7, cycled), clean runs the no-attack invite
(V0). Labels go to data/testset_labels.json. Needs Bedrock; about 15 s per run.
shortcut: the contract gives the test set to Liam; this generates one from his eval variants.
"""

import argparse
import json
import os
import shutil
import threading
import time
from pathlib import Path

import httpx

from engine import metrics
from engine.dev.demo import start_api
from engine.store import events

LABELS = Path("data/testset_labels.json")
ATTACKS = ["V1_authority", "V2_system_tag", "V3_harmony", "V4_authority_harmony",
           "V5_fake_tool_result", "V6_fake_turn", "V7_combo"]


def run_one(http, variant):
    """One agent run on a calendar holding `variant`. Returns its run id once it settles."""
    from agents.meeting_assistant.agent import TASK
    from agents.meeting_assistant.eval_injection import VARIANTS, seeded
    from agents.services.store import reset
    from engine.dev.meeting_sdk import factory

    before = {r["id"] for r in http.get("/runs").json()}
    reset(seeded(VARIANTS[variant]))
    agent = factory()
    threading.Thread(target=lambda: _invoke(agent, TASK), daemon=True).start()
    for _ in range(240):
        new = [r for r in http.get("/runs").json() if r["id"] not in before]
        if new and new[0]["status"] in ("frozen", "completed", "killed", "halted"):
            return new[0]
        time.sleep(0.5)
    raise SystemExit(f"run on {variant} did not settle in 120 s")


def _invoke(agent, task):
    try:
        agent.invoke({"messages": [("user", task)]})
    except Exception:  # noqa: BLE001, S110 - mirage.Blocked when we kill a frozen run
        pass


def main():
    parser = argparse.ArgumentParser(prog="engine.dev.testset")
    parser.add_argument("--clean", type=int, default=10)
    parser.add_argument("--poisoned", type=int, default=10)
    parser.add_argument("--detonate", type=int, default=3, help="detonate the first N incidents")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    from agents.meeting_assistant.eval_injection import ATTACKER

    shutil.rmtree("data", ignore_errors=True)
    api, url = start_api(args.port)
    os.environ["MIRAGE_URL"] = url
    http = httpx.Client(base_url=url, timeout=30)
    plan = ([ATTACKS[i % len(ATTACKS)] for i in range(args.poisoned)]
            + ["V0_baseline"] * args.clean)
    labels, detonated = {}, 0
    try:
        for n, variant in enumerate(plan, start=1):
            run = run_one(http, variant)
            labels[run["id"]] = variant != "V0_baseline"
            print(f"  {n:2}/{len(plan)} {variant:22} -> {run['id']} {run['status']}", flush=True)
            if run["status"] == "frozen":
                if detonated < args.detonate:
                    detonated += 1
                    http.post(f"/incidents/{run['incident_id']}/detonate",
                              json={"actor": "testset", "reason": "measure time to verdict"})
                    for _ in range(300):  # until the verdict (or a failure), not just "started"
                        inc = http.get(f"/incidents/{run['incident_id']}").json()
                        failed = any(e["type"] == "detonation.failed" for e in
                                     http.get("/events").json()
                                     if e["incident_id"] == run["incident_id"])
                        if inc["status"] in ("confirmed", "false_positive") or failed:
                            break
                        time.sleep(1)
                http.post(f"/runs/{run['id']}/kill", json={"actor": "testset", "reason": "test set"})
            time.sleep(1)  # pace Bedrock between runs
        LABELS.write_text(json.dumps(labels, indent=1), encoding="utf-8")
        print("\n" + metrics.report(metrics.compute(events.read(), labels, ATTACKER)))
    finally:
        api.terminate()


if __name__ == "__main__":
    main()
