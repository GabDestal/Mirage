"""`mirage detonate`: works without the UI and without the API server (CONTRACTS.md §6).

uv run python -m engine.cli detonate --incident inc_001 [--runs 3] [--remove-input in_03] [--json]
uv run python -m engine.cli bisect --incident inc_001 [--runs 2]
"""

import argparse
import sys

from engine.bisect import bisect
from engine.detonation.sandbox import detonate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mirage")
    sub = parser.add_subparsers(dest="command", required=True)
    det = sub.add_parser("detonate", help="Replay a frozen run in the Mirage sandbox")
    det.add_argument("--incident", required=True)
    det.add_argument("--runs", type=int, default=3)
    det.add_argument("--remove-input")
    det.add_argument("--json", action="store_true", help="print the DetonateResult as JSON")
    bis = sub.add_parser("bisect", help="Remove one input at a time to prove the cause")
    bis.add_argument("--incident", required=True)
    bis.add_argument("--runs", type=int, default=2, help="detonations per removed input")
    args = parser.parse_args(argv)

    if args.command == "bisect":
        _, cause = bisect(args.incident, args.runs)
        print(f"\nCause: {cause or 'no single input proven'}")
        return 0 if cause else 1

    log = (lambda *_: None) if args.json else print
    log(f"Detonating {args.incident} x{args.runs}"
        + (f" without {args.remove_input}" if args.remove_input else "") + " ...")
    _, verdict, result = detonate(args.incident, args.runs, args.remove_input, log=log)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(f"\nVerdict: {'CONFIRMED' if verdict.confirmed else 'not confirmed'} "
              f"({verdict.compromised_runs} compromised)")
        print(f"Blast radius: {verdict.blast_radius.summary}")
        print(f"Policies: {', '.join(verdict.policies_violated) or '-'}")
        print(f"attack_blocked={result.attack_blocked} "
              f"legit_task_completed={result.legit_task_completed} passed={result.passed}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
