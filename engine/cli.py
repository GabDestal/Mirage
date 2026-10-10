"""`mirage detonate`: works without the UI and without the API server (CONTRACTS.md §6).

uv run python -m engine.cli detonate --incident inc_001 [--runs 3] [--json]   # check a fix
uv run python -m engine.cli detonate --incident inc_001 --from-freeze          # operator replay
uv run python -m engine.cli bisect --incident inc_001 [--runs 2]
uv run python -m engine.cli pr --incident inc_001 --url https://github.com/.../pull/42
uv run python -m engine.cli export-fixture [--out contracts/fixtures/calendar_demo.jsonl]
uv run python -m engine.cli metrics [--labels data/testset_labels.json]   # after engine.dev.testset
"""

import argparse
import sys

from engine.bisect import bisect
from engine.detonation.sandbox import DetonationError, detonate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mirage")
    sub = parser.add_subparsers(dest="command", required=True)
    det = sub.add_parser("detonate", help="Check a fix: rerun the current agent code in the "
                         "sandbox; passes when the attack is blocked n/n and the task done n/n")
    det.add_argument("--incident", required=True)
    det.add_argument("--runs", type=int, default=3)
    det.add_argument("--remove-input")
    det.add_argument("--json", action="store_true", help="print the DetonateResult as JSON")
    det.add_argument("--from-freeze", action="store_true",
                     help="operator replay: continue the frozen run as it was (no fix check)")
    bis = sub.add_parser("bisect", help="Remove one input at a time to prove the cause")
    bis.add_argument("--incident", required=True)
    bis.add_argument("--runs", type=int, default=2, help="detonations per removed input")
    pr = sub.add_parser("pr", help="Report the fix PR for an incident")
    pr.add_argument("--incident", required=True)
    pr.add_argument("--url", required=True)
    exp = sub.add_parser("export-fixture", help="Save the event log as a replay fixture")
    exp.add_argument("--out", default="contracts/fixtures/calendar_demo.jsonl")
    met = sub.add_parser("metrics", help="Detection metrics over the event log and test-set labels")
    met.add_argument("--labels", default="data/testset_labels.json")
    met.add_argument("--attacker", default="attacker@evil-corp-demo.com")
    args = parser.parse_args(argv)

    if args.command == "metrics":
        import json
        from pathlib import Path

        from engine import metrics
        from engine.store import events
        labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
        print(metrics.report(metrics.compute(events.read(), labels, args.attacker)))
        return 0

    if args.command == "export-fixture":
        return export_fixture(args.out)

    if args.command == "pr":
        from engine.handoff import pr_opened
        print(f"Recorded PR {pr_opened(args.incident, args.url)['url']} for {args.incident}.")
        return 0

    if args.command == "bisect":
        _, cause = bisect(args.incident, args.runs)
        print(f"\nCause: {cause or 'no single input proven'}")
        return 0 if cause else 1

    verify = not args.from_freeze and not args.remove_input
    log = (lambda *_: None) if args.json else print
    log(f"{'Checking the fix for' if verify else 'Detonating'} {args.incident} x{args.runs}"
        + (f" without {args.remove_input}" if args.remove_input else "") + " ...")
    try:
        _, verdict, result = detonate(args.incident, args.runs, args.remove_input, log=log,
                                      verify=verify)
    except DetonationError as e:
        print(f"\nDetonation FAILED, no verdict: {e}")
        return 2
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        if verify:
            print(f"\nFix: {'VERIFIED' if result.passed else 'NOT verified'} "
                  f"(attack blocked {result.attack_blocked}, "
                  f"legit task {result.legit_task_completed})")
        else:
            print(f"\nVerdict: {'CONFIRMED' if verdict.confirmed else 'not confirmed'} "
                  f"({verdict.compromised_runs} compromised)")
        print(f"Blast radius: {verdict.blast_radius.summary}")
        print(f"Policies: {', '.join(verdict.policies_violated) or '-'}")
        print(f"attack_blocked={result.attack_blocked} "
              f"legit_task_completed={result.legit_task_completed} passed={result.passed}")
    return 0 if result.passed else 1


def export_fixture(out):
    """Write the event log (data/mirage.db, or MIRAGE_DB) as a replay fixture, then load it back
    as a replay and list its operator steps, so a bad recording is caught now, not on stage."""
    from pathlib import Path

    from engine.api.replay import Replay, step_of
    from engine.store import events

    log = events.read()
    if not log:
        print("The event log is empty: run the demo first.")
        return 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("".join(e.model_dump_json() + "\n" for e in log), encoding="utf-8")
    replay = Replay(out)
    print(f"Wrote {len(log)} events to {out}. Replay steps (one POST each after the first):")
    for n, start in enumerate(replay.starts):
        first = replay.events[start]
        label = (first.payload.get("action") if first.type == "human.action"
                 else step_of(first) or "production")
        print(f"  {n}. {label}  (event {first.seq})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
