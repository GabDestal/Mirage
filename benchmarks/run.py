"""Run one preselected native case; artifact rows always retain incomplete outcomes."""

import argparse
import os
import json
import subprocess
import signal
import time
import hashlib
from uuid import uuid4
import sys
from pathlib import Path

from benchmarks.common import Bedrock, plain, save


def wait_job(client, incident_id, timeout=570):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/incidents/" + incident_id)
        response.raise_for_status()
        incident = response.json()
        job = incident.get("sandbox_job") or {}
        if job.get("status") in {"completed", "failed"}:
            return incident
        time.sleep(1)
    raise TimeoutError("bounded sandbox job")


def finish_workflow(gate, suite, task, injection, pre, original, model, manifest, output):
    """Logged synthetic operator journey; actual human acceptance stays unmeasured."""
    from benchmarks.agentdojo import REPAIR, REPAIRS, execute, grade, reconstruct, validate_state
    client = gate.core._http
    run = client.get("/runs/" + gate.run["id"]).json()
    incident_id = run.get("incident_id")
    details = {"incident_id": incident_id, "restart_id": None,
               "operator": "automated-synthetic-benchmark-operator",
               "human_approved_recovery": None, "simulated_operator_recovery": None}
    if not incident_id:
        details["unknown_reason"] = "no_incident_for_recovery"
        return original, details
    body = {"actor": details["operator"], "reason": "Synthetic native benchmark operator; no human acceptance claim"}
    try:
        incident = wait_job(client, incident_id)
        all_events = client.get("/events").json()
        events = [e for e in all_events if e.get("incident_id") == incident_id]
        save(output + ".incident-before-fix.json", {"incident": incident, "events": events})
        baseline_id = incident["sandbox_job"]["id"]
        effects = [e["payload"] for e in events if e["type"] == "detonation.effect"
                   and e["payload"]["detonation_id"] == baseline_id]
        proofs = [reconstruct(suite, task, injection, pre, original["world"], original["ledger"],
                              [e for e in effects if e["run_index"] == n]) for n in range(1, 4)]
        save(output + ".detonation-state.json", proofs)
        details["detonation_validation"] = [{k: p[k] for k in ["native_scores", "validation_result",
                                                             "unknown_reasons"]} for p in proofs]
        if not incident.get("verdict", {}).get("confirmed"):
            details["unknown_reason"] = "no_confirmed_incident"
            return original, details
        response = client.post(f"/incidents/{incident_id}/bisect?runs=2", json=body)
        response.raise_for_status()
        incident = wait_job(client, incident_id)
        details["cause_input_id"] = incident.get("cause_input_id")
        details["bisection"] = incident.get("bisection")
        # The same general instruction is used for every repair; no benchmark answers.
        save(REPAIRS / (gate.name + ".json"), {"actor": details["operator"],
             "system_sha256": hashlib.sha256(REPAIR.encode()).hexdigest(),
             "incident_id": incident_id, "system_suffix": REPAIR})
        response = client.post(f"/incidents/{incident_id}/verify?runs=3", json=body)
        response.raise_for_status()
        incident = wait_job(client, incident_id)
        events = [e for e in client.get("/events").json() if e.get("incident_id") == incident_id]
        verify_id = incident["sandbox_job"]["id"]
        effects = [e["payload"] for e in events if e["type"] == "detonation.effect"
                   and e["payload"]["detonation_id"] == verify_id]
        proofs = [reconstruct(suite, task, injection, pre, original["world"], original["ledger"],
                              [e for e in effects if e["run_index"] == n]) for n in range(1, 4)]
        save(output + ".verification-state.json", proofs)
        checks = [e["payload"] for e in events if e["type"] == "fix.verified"]
        details["engine_fix_check"] = checks[-1] if checks else None
        details["verification_validation"] = [{k: p[k] for k in ["native_scores", "validation_result",
                                                               "unknown_reasons"]} for p in proofs]
        if (not checks or not checks[-1].get("passed") or not all(
                p["validation_result"]["task_completed"] is True and
                p["validation_result"]["harm"] is False and not p["unknown_reasons"] for p in proofs)):
            details["unknown_reason"] = "verification_incomplete_or_failed"
            return original, details
        client.post(f"/runs/{gate.run['id']}/kill", json=body).raise_for_status()
        response = client.post(f"/runs/{gate.run['id']}/approve-restart", json=body)
        response.raise_for_status()
        details["restart_approval"] = response.json()
        gate.run = gate.core.open_run(gate.name, task.PROMPT)
        restarted = client.get("/runs/" + gate.run["id"]).json()
        if restarted.get("restarted_from") != run["id"]:
            raise ValueError("restart identity mismatch")
        details["restart_id"] = restarted["id"]
        fresh = pre.model_copy(deep=True)
        result = execute(suite, task, fresh, model, manifest["parameters"], manifest["max_steps"],
                         gate=gate, max_tools=manifest["max_tool_steps"],
                         timeout_s=manifest["timeout_s"], repair=True)
        final_scores = grade(suite, task, injection, pre, result)
        final_validation = validate_state(task, pre, result, final_scores)
        details["simulated_operator_recovery"] = (
            result["status"] == "completed" and final_validation["task_completed"] is True
            and final_validation["harm"] is False)
        if not details["simulated_operator_recovery"]:
            details["unknown_reason"] = "restart_did_not_establish_safe_task_completion"
        details["repair_suffix_sha256"] = hashlib.sha256(REPAIR.encode()).hexdigest()
        details["factory_receipts"] = str(REPAIRS / (gate.name + ".factory.jsonl"))
        save(output + ".lifecycle-events.json", client.get("/events").json())
        return result, details
    except Exception as exc:
        details["unknown_reason"] = "workflow_" + type(exc).__name__
        return original, details


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="benchmarks/manifest.json")
    parser.add_argument("--cases", default="benchmarks/manifest_agentdojo_v2.json")
    parser.add_argument("--case", required=True, help="case id from --cases")
    parser.add_argument("--model", required=True)
    parser.add_argument("--arm", default="unprotected", choices=["unprotected", "gate", "full"])
    parser.add_argument("--env-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    sys.path[:0] = [manifest["native_source"] + "/src", manifest["native_deps"]]
    from benchmarks.agentdojo import Gate, execute, grade, prepare, validate_state

    case = next(c for c in json.loads(Path(args.cases).read_text())["cases"] if c["id"] == args.case)
    args.attack = case["cohort"] == "attack"
    suite, task, injection, world = prepare(case, args.attack, manifest["benchmark_version"])
    pre = world.model_copy(deep=True)
    model = Bedrock(args.model, args.env_path)
    gate = None
    if args.arm != "unprotected":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
        _, _, _, clean_world = prepare(case, False, manifest["benchmark_version"])
        gate = Gate(suite, task, clean_world, model, {
            "case_id": case["case_id"], "name": "agentdojo-" + args.arm + "-" + uuid4().hex[:12]
        })
    def deadline(_signum, _frame):
        raise TimeoutError("invocation deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, manifest["timeout_s"])
    observation = {}
    try:
        try:
            result = execute(suite, task, world, model, manifest["parameters"], manifest["max_steps"],
                             gate=gate, max_tools=manifest["max_tool_steps"],
                             timeout_s=manifest["timeout_s"], observation=observation)
        except Exception as exc:
            # Tool/gateway/deadline failures retain the partial native world; no clean claim.
            result = {"world": world, "ledger": [], "traces": [], "messages": [], "output": "",
                      **observation,
                      "status": "unknown", "unknown_reason": type(exc).__name__,
                      "latency_s": None}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    workflow = None
    if args.arm == "full" and result["status"] == "frozen":
        result, workflow = finish_workflow(gate, suite, task, injection, pre, result, model,
                                          manifest, args.output)
    if gate and result["status"] == "completed":
        gate.core.complete(gate.run)
    try:
        scores = grade(suite, task, injection, pre, result)
    except Exception as exc:
        scores = {"utility": None, "attacker_success": None}
        result["status"], result["unknown_reason"] = "unknown", "grader_" + type(exc).__name__
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    evidence = f"/tmp/mirage-adv2-evidence/{case['id']}.{args.arm}.{uuid4().hex[:6]}.json"
    save(evidence, {"pre_world": pre, "post_world": result["world"],
                    "ledger": result["ledger"], "messages": result["messages"],
                    "traces": result["traces"], "output": result["output"],
                    "gate_decisions": gate.decisions if gate else [],
                    "runtime": gate.runtime if gate else None})
    run = gate.core._http.get("/runs/" + gate.run["id"]).json() if gate else {}
    try:
        validation = validate_state(task, pre, result, scores)
    except Exception as exc:
        validation = {"error": type(exc).__name__}
    row = {"benchmark": "agentdojo", "id": case["id"], "case_id": case["case_id"],
           "attack_id": case["attack"] + ":" + case["injection_task_id"] if args.attack else None,
           "split": case["split"], "cohort": "attack" if args.attack else "clean",
           "source_sha": manifest["source_sha"], "code_sha": code_sha,
           "model_id": args.model, "parameters": manifest["parameters"],
           "policy_version": manifest["policy_version"], "arm": args.arm,
           "status": result["status"], "unknown_reason": result["unknown_reason"],
           "native_scores": scores, "validation_method": "native_final_world_and_traces",
           "validation_result": validation,
           "blocked": result.get("blocked", []),
           "evidence_refs": [evidence], "incident_id": run.get("incident_id"), "restart_id": None,
           "run_id": run.get("id"), "runtime": gate.runtime if gate else None,
           "gate_unavailable": any("unavailable" in d.get("explanation", "").lower()
                                   for d in gate.decisions) if gate else None,
           "workflow": workflow,
           "recovery_subset": case["case_id"] in manifest["full_arm_subset"],
           "on_hit": os.getenv("MIRAGE_ON_HIT", "freeze"),
           "recovery_applicable": args.arm == "full" and args.attack,
           "calls": model.calls, "tokens": model.tokens, "latency_s": result["latency_s"],
           "base_sha": manifest["base_sha"], "accepted_base_sha": manifest["accepted_base_sha"],
           "engine_accepted_sha": manifest["engine_accepted_sha"],
           "engine_acceptance": manifest["engine_acceptance"],
           "code_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True))}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    if workflow:
        row["incident_id"] = workflow["incident_id"]
        row["restart_id"] = workflow["restart_id"]
        if workflow.get("unknown_reason"):
            row["status"], row["unknown_reason"] = "unknown", workflow["unknown_reason"]
    with Path(args.output).open("a") as handle:
        handle.write(json.dumps(plain(row)) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    main()
