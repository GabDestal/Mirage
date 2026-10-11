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


def fresh(seed=27, n_attack=20, n_clean=10):
    """Fresh held-out from pairs the v2 split never used; clean tasks reused (only one unused)."""
    old = json.loads(OUT.read_text())["cases"]
    suite = get_suite(MANIFEST["benchmark_version"], "slack")
    used = {c["id"] for c in old}
    rng = random.Random(seed)
    pairs = sorted(f"{u}:{i}" for u in suite.user_tasks for i in suite.injection_tasks
                   if f"{u}:{i}" not in used)
    unused_clean = sorted(u for u in suite.user_tasks if f"{u}:clean" not in used)
    clean = unused_clean + rng.sample(sorted(set(suite.user_tasks) - set(unused_clean)),
                                      n_clean - len(unused_clean))
    cases = [c for c in old if c["split"] == "dev"]
    cases += [{"id": pid, "suite": "slack", "case_id": pid.split(":")[0],
               "injection_task_id": pid.split(":")[1], "attack": "important_instructions",
               "cohort": "attack", "split": "heldout2"} for pid in rng.sample(pairs, n_attack)]
    cases += [{"id": f"{u}:clean:heldout2", "suite": "slack", "case_id": u,
               "injection_task_id": None, "attack": None, "cohort": "clean", "split": "heldout2",
               "reused_clean": u not in unused_clean} for u in clean]
    out = OUT.with_name("manifest_agentdojo_v3.json")
    out.write_text(json.dumps({"seed": seed, "suite": "slack", "benchmark_version":
                               MANIFEST["benchmark_version"], "unused_clean": unused_clean,
                               "cases": cases}, indent=2) + "\n")
    print(len(cases), "cases ->", out)


if __name__ == "__main__":
    import sys
    fresh() if "--fresh" in sys.argv else main()
