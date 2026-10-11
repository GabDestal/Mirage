"""Run one preselected native case; artifact rows always retain incomplete outcomes."""

import argparse
import json
import subprocess
import signal
import sys
from pathlib import Path

from benchmarks.common import Bedrock, plain, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="benchmarks/manifest.json")
    parser.add_argument("--case", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--attack", action="store_true")
    parser.add_argument("--arm", default="unprotected", choices=["unprotected", "gate", "full"])
    parser.add_argument("--env-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    sys.path[:0] = [manifest["native_source"] + "/src", manifest["native_deps"]]
    from benchmarks.agentdojo import execute, grade, prepare

    case = next(c for c in manifest["cases"] if c["case_id"] == args.case)
    suite, task, injection, world = prepare(case, args.attack, manifest["benchmark_version"])
    pre = world.model_copy(deep=True)
    model = Bedrock(args.model, args.env_path)
    if args.arm != "unprotected":
        raise RuntimeError("Protected execution waits for accepted engine integration")
    def deadline(_signum, _frame):
        raise TimeoutError("invocation deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, manifest["timeout_s"])
    try:
        result = execute(suite, task, world, model, manifest["parameters"], manifest["max_steps"],
                         max_tools=manifest["max_tool_steps"], timeout_s=manifest["timeout_s"])
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        scores = grade(suite, task, injection, pre, result)
    except Exception as exc:
        scores = {"utility": None, "attacker_success": None}
        result["status"], result["unknown_reason"] = "unknown", "grader_" + type(exc).__name__
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    evidence = args.output + ".evidence.json"
    save(evidence, {"pre_world": pre, "post_world": result["world"],
                    "ledger": result["ledger"], "messages": result["messages"],
                    "traces": result["traces"], "output": result["output"]})
    row = {"benchmark": "agentdojo", "case_id": args.case,
           "attack_id": case["attack"] + ":" + case["injection_task_id"] if args.attack else None,
           "split": case["split"], "cohort": "attack" if args.attack else "clean",
           "source_sha": manifest["source_sha"], "code_sha": code_sha,
           "model_id": args.model, "parameters": manifest["parameters"],
           "policy_version": manifest["policy_version"], "arm": args.arm,
           "status": result["status"], "unknown_reason": result["unknown_reason"],
           "native_scores": scores, "validation_method": "native_final_world_and_traces",
           "validation_result": scores if result["status"] == "completed" else None,
           "evidence_refs": [evidence], "incident_id": None, "restart_id": None,
           "calls": model.calls, "tokens": model.tokens, "latency_s": result["latency_s"],
           "base_sha": manifest["base_sha"], "accepted_base_sha": manifest["accepted_base_sha"],
           "engine_accepted_sha": manifest["engine_accepted_sha"],
           "engine_acceptance": manifest["engine_acceptance"],
           "code_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True))}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output).open("a") as handle:
        handle.write(json.dumps(plain(row)) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    main()
