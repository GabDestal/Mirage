"""Write the seeded DEV/HELD-OUT split from AgentDojo's own Slack suite (before any run)."""

import json
import random
from pathlib import Path

from benchmarks.agentdojo import MANIFEST, get_suite

SEED, N_ATTACK, N_CLEAN = 26, 40, 20
OUT = Path(__file__).with_name("manifest_agentdojo_v2.json")


def main():
    suite = get_suite(MANIFEST["benchmark_version"], "slack")
    users, injections = sorted(suite.user_tasks), sorted(suite.injection_tasks)
    rng = random.Random(SEED)
    pairs = rng.sample([(u, i) for u in users for i in injections], N_ATTACK)
    clean = rng.sample(users, N_CLEAN)
    cases = [{"id": f"{u}:{i}", "suite": "slack", "case_id": u, "injection_task_id": i,
              "attack": "important_instructions", "cohort": "attack",
              "split": "dev" if n < N_ATTACK // 2 else "heldout"} for n, (u, i) in enumerate(pairs)]
    cases += [{"id": f"{u}:clean", "suite": "slack", "case_id": u, "injection_task_id": None,
               "attack": None, "cohort": "clean",
               "split": "dev" if n < N_CLEAN // 2 else "heldout"} for n, u in enumerate(clean)]
    OUT.write_text(json.dumps({"seed": SEED, "suite": "slack",
                               "benchmark_version": MANIFEST["benchmark_version"],
                               "cases": cases}, indent=2) + "\n")
    print(len(cases), "cases ->", OUT)


if __name__ == "__main__":
    main()
