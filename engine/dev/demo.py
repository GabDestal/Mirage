"""One command, the whole story: freeze -> detonate -> find the cause -> check a fix.

    uv run python -m engine.dev.demo                    # dev agents (3 runs, gate in-process)
    uv run python -m engine.dev.demo --agent meeting    # Liam's meeting assistant via the SDK
    uv run python -m engine.dev.demo --keep             # leave the API up for the UI afterwards
    uv run python -m engine.dev.demo --agent meeting --until freeze   # stop at the freeze, drive
                                                                      # the rest from the UI

Starts the engine API as its own process (live mode), runs the agents, then drives the incident
over HTTP exactly like the UI or MCP would. Needs .env with a valid Bedrock key. ~5 minutes.
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time

import httpx

DATA = "data"


def step(text):
    print(f"\n== {text}", flush=True)


def wait(fetch, ready, what, timeout):
    start = time.time()
    while time.time() - start < timeout:
        value = fetch()
        if ready(value):
            return value
        time.sleep(1)
    sys.exit(f"Timed out after {timeout}s waiting for {what}.")


def start_api(port):
    env = {**os.environ, "MIRAGE_MODE": "live"}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "engine.api.server:app",
                            "--port", str(port), "--log-level", "warning"], env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            httpx.get(f"{url}/runs").raise_for_status()
            return api, url
        except httpx.HTTPError:
            time.sleep(0.5)
    api.kill()
    sys.exit(f"The API did not start on port {port} (in use?).")


def run_dev_agents():
    from engine.dev import runner
    runner.start()  # 3 runs in threads; Bob's calendar holds the poisoned invite
    return "3 dev agents (gpt-oss-20b), gate in this process"


def run_meeting_agent(url):
    os.environ["MIRAGE_URL"] = url
    from agents.meeting_assistant.agent import TASK
    from agents.meeting_assistant.eval_injection import VARIANTS, seeded
    from agents.services.store import reset
    from engine.dev.meeting_sdk import factory

    reset(seeded(VARIANTS["V2_system_tag"]))  # the poisoned invite, as the attacker wrote it
    agent = factory()

    def go():
        try:
            agent.invoke({"messages": [("user", TASK)]})
        except Exception:  # noqa: BLE001, S110 - mirage.Blocked when the run is killed at the end
            pass

    threading.Thread(target=go, daemon=True).start()
    return "Liam's meeting assistant via mirage.protect (gpt-oss-20b), poisoned invite V2"


def hands_on(url, run_id, incident_id, agent):
    """--until freeze: print what the operator can do now, from the UI or by hand."""
    owned = "API" if agent == "meeting" else "this process (dev runner): UI kill/unfreeze = 409"
    print(f"""
Stopped at the freeze. The engine stays up at {url} (Liam's UI: http://localhost:5173).
The frozen run {run_id} is held by the {owned}.
  From the UI: Unfreeze (the blocked email goes out: false positive path) or Kill.
  By hand:     curl -X POST {url}/incidents/{incident_id}/detonate
               curl -X POST {url}/incidents/{incident_id}/bisect
               curl -X POST {url}/runs/{run_id}/kill -H "Content-Type: application/json" \\
                    -d '{{"actor": "gabi", "reason": "confirmed"}}'
Ctrl+C to stop.""", flush=True)


def main():
    parser = argparse.ArgumentParser(prog="engine.dev.demo")
    parser.add_argument("--agent", choices=["dev", "meeting"], default="dev")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--keep", action="store_true", help="leave the API running at the end")
    parser.add_argument("--until", choices=["freeze"],
                        help="stop after the freeze and leave everything running: drive it "
                             "from the UI (unfreeze, kill, detonate...)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    shutil.rmtree(DATA, ignore_errors=True)  # fresh event log and snapshots

    step(f"Engine API on port {args.port} (live mode)")
    api, url = start_api(args.port)
    http = httpx.Client(base_url=url, timeout=30)
    try:
        step("Production: agents start")
        print(run_dev_agents() if args.agent == "dev" else run_meeting_agent(url))
        runs = wait(lambda: http.get("/runs").json(),
                    lambda rs: rs and any(r["status"] == "frozen" for r in rs)
                    or (rs and all(r["status"] in ("completed", "killed") for r in rs)),
                    "a run to freeze", 300)
        for r in runs:
            print(f"  {r['id']}  {r['status']:9}  tool calls: {r['tool_calls']}")
        frozen = next((r for r in runs if r["status"] == "frozen"), None)
        if not frozen:
            sys.exit("No run froze: the agent did not take the bait this time. Run it again.")
        incident_id = frozen["incident_id"]
        trigger = http.get(f"/incidents/{incident_id}").json()["trigger"]
        print(f"  FROZEN by the gate: {trigger['rule_id']} on {trigger['tool']} "
              f"-> {trigger['args'].get('to') or trigger['args']}")
        if args.until == "freeze":
            hands_on(url, frozen["id"], incident_id, args.agent)
            api.wait()  # the operator drives from the UI; Ctrl+C stops everything
            return

        def incident():
            return http.get(f"/incidents/{incident_id}").json()

        step(f"Detonate {incident_id} in the sandbox (3 runs)")
        http.post(f"/incidents/{incident_id}/detonate?runs=3")
        inc = wait(incident, lambda i: i["status"] in ("confirmed", "false_positive"),
                   "the verdict", 600)
        print(f"  {inc['verdict']['compromised_runs']} compromised. "
              f"{inc['verdict']['blast_radius']['summary']}")
        if inc["status"] != "confirmed":
            sys.exit("Not confirmed: a false positive. A human would unfreeze the run.")

        step("Find the cause: remove one untrusted input at a time (2 runs each)")
        http.post(f"/incidents/{incident_id}/bisect?runs=2")
        inc = wait(incident, lambda i: i["status"] in ("root_caused", "confirmed")
                   and i["bisection"], "the bisection", 900)
        for row in inc["bisection"]:
            print(f"  without {row['label'][:42]:42} {row['compromised_runs']} compromised"
                  + ("   <- CAUSE" if row["is_cause"] else ""))

        step("Check the current agent code as a fix (2 runs)")
        seen = len(http.get("/events").json())
        http.post(f"/incidents/{incident_id}/verify?runs=2")
        result = wait(lambda: [e for e in http.get(f"/events?after={seen}").json()
                               if e["type"] == "fix.verified"], bool, "the fix check", 600)
        fix = result[0]["payload"]
        print(f"  attack blocked {fix['attack_blocked']}, legit task {fix['legit_task_completed']}"
              f" -> {'VERIFIED' if fix['passed'] else 'NOT verified (expected: no fix yet)'}")

        reason = {"actor": "demo", "reason": "Confirmed compromise."}
        if http.post(f"/runs/{frozen['id']}/kill", json=reason).status_code == 409:
            from engine.gateway import gate  # dev runs live in this process, not the API's
            gate.kill(frozen["id"], **reason)
        print(f"\nDone. Incident {incident_id}: next action = {incident()['next_action']}.")
        if args.keep:
            print(f"API still running at {url} (Ctrl+C to stop).")
            api.wait()
    finally:
        if not args.keep:
            api.terminate()


if __name__ == "__main__":
    main()
