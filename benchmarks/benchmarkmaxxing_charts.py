"""Render frozen, sanitized benchmark receipts; never run a model or grader.

stdlib SVG keeps publication independent of plotting packages and provider work.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import subprocess


BASE = "2640720f45a987c507f74a905f25d06948b86921"
W2 = "7a6e7149d3c93a41aebf18c1fedd6d89f9a88d86"
ROOT = Path("/tmp/mirage-benchmaxing/run_1d89fe10e4c5")
MODELS = {
    "openai.gpt-oss-20b-1:0": "GPT-OSS 20B",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Haiku 4.5",
    "us.anthropic.claude-opus-4-8": "Opus 4.8 reference",
}
ARMS = {"simple_diagnosis": "Simple", "evidence_assisted_diagnosis": "Assisted",
        "unprotected": "Unprotected", "gate": "Gate", "full": "Full engine"}
SAFE_KEYS = ("benchmark", "case_id", "attack_id", "split", "cohort", "source_sha",
             "code_sha", "model_id", "parameters", "policy_version", "arm", "status",
             "unknown_reason", "calls", "tokens", "latency_s", "evidence_refs")


def pin(data, name, **extra):
    return {"path": name, "sha256": sha256(data).hexdigest(), **extra}


def load_report(path, sources):
    data = path.read_bytes()
    sources.append(pin(data, str(path), input_mtime_utc=datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc).isoformat()))
    return json.loads(data)


def project(row):
    return {k: row.get(k) for k in SAFE_KEYS}


def summary(values):
    known = [float(v) for v in values if v is not None]
    n, u = len(values), len(values) - len(known)
    s = sum(known)
    assert n and all(0 <= v <= 1 for v in known)
    binary = all(v in (0, 1) for v in known)
    result = {"N": n, "scored": len(known), "U": u, "score_sum": s,
              "coverage": len(known) / n, "bounds": [s / n, (s + u) / n],
              "values": values, "S": int(s) if binary else None,
              "F": len(known) - int(s) if binary else None}
    if binary:
        assert result["S"] + result["F"] + u == n
    assert 0 <= result["bounds"][0] <= result["bounds"][1] <= 1
    return result


def token_count(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        return value.get("totalTokens", value.get("total_tokens"))
    return None


def compute(rows):
    values = {"calls": [r.get("calls") for r in rows],
              "tokens": [token_count(r.get("tokens")) for r in rows],
              "latency_s": [r.get("latency_s") for r in rows]}
    return {k: {"known_sum": sum(v for v in vs if v is not None),
                "known_rows": sum(v is not None for v in vs), "N": len(rows)}
            for k, vs in values.items()}


def aggregate(rows, metrics):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["split"], row["model_id"], row["arm"])].append(row)
    return [{"cohort": key[0], "split": key[1], "model_id": key[2], "arm": key[3],
             "case_ids": [r["case_id"] for r in group], "compute": compute(group),
             "metrics": {m: summary([r["values"].get(m) for r in group]) for m in metrics}}
            for key, group in groups.items()]


class SVG:
    def __init__(self, width):
        self.width, self.parts = width, []

    def text(self, x, y, value, size=16, weight=400, color="#25303b"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(str(value))}</text>')

    def rect(self, x, y, w, h, fill, stroke="none"):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}"/>')

    def save(self, path, height, title):
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" viewBox="0 0 {self.width} {height}" role="img" aria-labelledby="title"><title id="title">{escape(title)}</title><defs><pattern id="unknown" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#edf0f3"/><path d="M0 8L8 0" stroke="#a7afb9" stroke-width="1"/></pattern></defs><rect width="100%" height="100%" fill="white"/><g font-family="Arial, Helvetica, sans-serif">' + "".join(self.parts) + '</g></svg>\n')


def figure1(groups, output, timestamp):
    chart, y = SVG(1380), 50
    chart.text(40, y, "AgentRx: native diagnosis outcomes", 29, 700)
    chart.text(40, y + 30, "v1 pilot • fixed selected denominators • no positive assisted gain demonstrated", 18)
    chart.text(40, y + 59, "Success / known failure / UNKNOWN; bounds allow every missing outcome to succeed.", 16)
    chart.rect(40, 128, 18, 18, "#2c668c"); chart.text(66, 143, "Success")
    chart.rect(180, 128, 18, 18, "#d79852"); chart.text(206, 143, "Known failure")
    chart.rect(364, 128, 18, 18, "url(#unknown)"); chart.text(390, 143, "UNKNOWN")
    y = 205
    previous = None
    for g in groups:
        cohort = (g["cohort"], g["split"])
        if cohort != previous:
            if previous is not None:
                y += 30
            label = ("Same-case DEVELOPMENT: tau:2 and tau:3" if g["split"] == "development" else
                     "Conditional Opus reference: same v1 six families • not executed" if "opus_reference" in g["cohort"] else
                     "Six untouched structural task families within seen domains (v1 evaluation)")
            chart.text(40, y, label, 21, 700); y += 30
            chart.text(40, y, g["cohort"] + " / " + g["split"], 15)
            y += 34
            chart.text(600, y, "0%", 15)
            chart.text(778, y, "50%", 15)
            chart.text(935, y, "100%", 15)
            chart.text(1010, y, "S / F / U", 15, 700)
            chart.text(1100, y, "Scored/N", 15, 700)
            chart.text(1190, y, "Bounds", 15, 700)
            y += 25
            previous = cohort
        label = MODELS.get(g["model_id"], g["model_id"]) + " • " + ARMS[g["arm"]]
        chart.text(40, y + 17, label, 18, 700)
        c = g["compute"]
        chart.text(40, y + 39, f'{c["calls"]["known_sum"]:g} calls; {c["tokens"]["known_sum"]:,.0f} known tokens; {c["latency_s"]["known_sum"]:.1f}s', 15)
        for j, (metric, data) in enumerate(g["metrics"].items()):
            yy, x = y + j * 32, 600
            chart.text(378, yy + 17, "Critical step" if metric == "critical_step_correct" else "Cause category", 16)
            for count, color in [(data["S"], "#2c668c"), (data["F"], "#d79852"), (data["U"], "url(#unknown)")]:
                w = count / data["N"] * 370
                chart.rect(x, yy, w, 23, color); x += w
            chart.rect(600, yy, 370, 23, "none", "#89939e")
            lo, hi = data["bounds"]
            chart.text(1010, yy + 17, f'{data["S"]}/{data["F"]}/{data["U"]}', 16)
            chart.text(1100, yy + 17, f'{data["scored"]}/{data["N"]}', 16)
            chart.text(1190, yy + 17, f'[{lo:.0%}, {hi:.0%}]', 16)
        y += 88
    for line in ["Assistance adds static → dynamic → checker stages before diagnosis; compute is not matched.",
                 "UNKNOWN includes stage/parse failures; no native grader or missing label is altered. No statistical intervals.",
                 "Static-trace diagnosis does not establish replay, recovery, restart or broad domain generalization.",
                 f"Frozen receipt snapshot: {timestamp} • exact pins, rows and arithmetic: chart-source.json / chart-source-table.md"]:
        chart.text(40, y, line, 16); y += 26
    chart.save(output / "agentrx-outcomes.svg", y + 25, "AgentRx v1 outcomes with UNKNOWN and fixed-denominator bounds")


RISK_METRICS = ("raw_utility", "raw_oracle", "raw_fallback", "state_task_completed", "native_safety", "state_safety", "joint_safe_completion")


def figure2(groups, output, timestamp, pending):
    chart, y = SVG(1510), 50
    chart.text(40, y, "HarnessRisk: raw utility and demonstrated final state", 29, 700)
    chart.text(40, y + 30, "Focus: final development revision and original held-out cohorts • all 51 historical cells retained in source table", 18)
    chart.text(40, y + 59, "Each cell: score sum / fixed N; UNKNOWN count U. Filled length = lower bound; hatch = missing-outcome range.", 16)
    chart.text(40, y + 85, "Raw native output may include incomplete runs; it is never credited as actual completion. Native scores retain partial values.", 16)
    y = 180
    labels = ["Raw utility", "Raw oracle", "Raw fallback", "Actual task", "Native safety", "State safety", "Joint safe task"]
    previous = None
    visible = [g for g in groups if g["cohort"] == "resource_budget_v5" or
               (g["cohort"] in ("native_recovery", "frontier_reference") and g["split"] == "held_out")]
    for g in visible:
        key = (g["cohort"], g["split"])
        if key != previous:
            if previous is not None:
                y += 22
            chart.text(40, y, g["cohort"] + " / " + g["split"], 20, 700); y += 27
            for i, label in enumerate(labels):
                chart.text(435 + i * 151, y, label, 16, 700)
            y += 20
            previous = key
        chart.text(40, y + 17, MODELS.get(g["model_id"], g["model_id"]) + " • " + ARMS[g["arm"]], 17)
        for i, metric in enumerate(RISK_METRICS):
            data, x = g["metrics"][metric], 435 + i * 151
            lo, hi = data["bounds"]
            chart.rect(x, y, 126, 23, "#f5f6f7", "#89939e")
            chart.rect(x, y, 126 * lo, 23, "#2c668c")
            chart.rect(x + 126 * lo, y, 126 * (hi - lo), 23, "url(#unknown)")
            chart.text(x, y + 43, f'{data["score_sum"]:.2f}/{data["N"]}  U{data["U"]}', 16)
        y += 61
    y += 24
    for item in pending:
        chart.text(40, y, f'{item["cohort"]}: {item["scored"]}/{item["N"]} scored; {item["U"]} UNKNOWN; bounds [0%, 100%].', 19, 700)
        y += 30
    for line in ["Phase2 primary full-engine recovery and the disclosed operator extension are distinct; neither has a provider receipt here.",
                 "Actual task = saved final-file predicates. Native safety = 1 − reconciled native attack success; state safety = 1 − known harm.",
                 "Joint safe task requires demonstrated task completion and known safety; initial compromise is already present in recovery fixtures.",
                 "GPT-OSS resource v5: raw utility 1, oracle 0.3333, fallback 1, actual task 0. Haiku: actual task 1 in both arms.",
                 "These development results establish no Mirage advantage or approved restart. Missing-outcome bounds are not confidence intervals.",
                 f"Frozen snapshot: {timestamp} • all original rows, parameters, code/source pins and compute: chart-source.json"]:
        chart.text(40, y, line, 16); y += 26
    chart.save(output / "harnessrisk-utility-safety.svg", y + 25, "HarnessRisk raw native utility versus state-validated utility and safety")


def table(agentrx, risk, output):
    lines = ["# Inspectable chart source table", "", "Generated solely from saved result rows; all bounds are missing-outcome bounds, not statistical intervals.", "", "| Benchmark | Cohort / split | Model | Arm | Metric | N | Scored | Sum | S / F / U | Bounds |", "|---|---|---|---|---|---:|---:|---:|---|---|"]
    for name, groups in [("AgentRx", agentrx), ("HarnessRisk", risk)]:
        for g in groups:
            for m, d in g["metrics"].items():
                counts = f'{d["S"]}/{d["F"]}/{d["U"]}' if d["S"] is not None else f'partial/partial/{d["U"]}'
                lines.append(f'| {name} | {g["cohort"]} / {g["split"]} | {MODELS[g["model_id"]]} | {ARMS[g["arm"]]} | {m} | {d["N"]} | {d["scored"]} | {d["score_sum"]:g} | {counts} | [{d["bounds"][0]:.4f}, {d["bounds"][1]:.4f}] |')
    (output / "chart-source-table.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentrx", nargs="+", type=Path, default=[ROOT / "phase2/agentrx/report.json", ROOT / "phase2/agentrx/families/report.json", ROOT / "phase2/agentrx/opus-reference/report.json"])
    parser.add_argument("--output", type=Path, default=Path("docs/benchmarkmaxxing"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    sources, rx = [], []
    for path in args.agentrx:
        report = load_report(path, sources)
        assert len(report["rows"]) == report["fixed_cells"]
        assert sum(r["calls"] for r in report["rows"]) == report["actual_calls"]
        for r in report["rows"]:
            row = project(r)
            row["values"] = {m: r["native_scores"].get(m) for m in ("critical_step_correct", "root_cause_correct")}
            rx.append(row)
        # Reconcile to producer aggregates without loading any scorer-only labels.
        for t in report["tables"]:
            values = [r["native_scores"].get(t["metric"]) for r in report["rows"] if r["model_id"] == t["model_id"] and r["arm"] == t["arm"]]
            s = summary(values)
            assert (s["N"], s["U"], s["score_sum"]) == (t["N"], t["U"], t["S_or_score_sum"])
    data = subprocess.check_output(["git", "show", f"{W2}:docs/BENCHMARKMAXXING_RESULTS.json"])
    sources.append(pin(data, "docs/BENCHMARKMAXXING_RESULTS.json", committed_code_sha=W2))
    report = json.loads(data)
    risk = []
    for r in report["rows"]:
        if r["benchmark"] != "HarnessRisk":
            continue
        row, native, metrics = project(r), r["native_scores"], r["metric_values"]
        row["native_scores"] = {k: v for k, v in native.items() if isinstance(v, (int, float, bool)) or v is None}
        row["reconciled_metric_values"] = metrics
        row["values"] = {"raw_utility": native.get("utility_score"), "raw_oracle": native.get("utility_oracle_score"), "raw_fallback": native.get("utility_final_answer_fallback_score"),
                         "state_task_completed": metrics.get("state_task_completed"),
                         "native_safety": None if metrics.get("attack_success_rate") is None else 1 - metrics["attack_success_rate"],
                         "state_safety": None if metrics.get("state_harm") is None else 1 - metrics["state_harm"],
                         "joint_safe_completion": metrics.get("joint_safe_completion")}
        risk.append(row)
    assert len(risk) == 51
    rg = aggregate(rx, ("critical_step_correct", "root_cause_correct"))
    hg = sorted(aggregate(risk, RISK_METRICS), key=lambda g: (
        g["cohort"] != "resource_budget_v5", g["cohort"], g["split"],
        list(MODELS).index(g["model_id"]), list(ARMS).index(g["arm"])))
    # Explicit dispatch contract for not-yet-executed phase2 cohorts; no illustrative values.
    pending = [{"cohort": "Phase2 primary full-engine recovery", "N": 12, "scored": 0, "U": 12},
               {"cohort": "Phase2 separate operator extension", "N": 4, "scored": 0, "U": 4}]
    contract = {"message_id": "msg_5af7f1e97fd8", "received_at": "2026-10-11T07:05:14Z", "from": "coordinator", "pending": pending}
    sources.append(pin(json.dumps(contract, sort_keys=True).encode(), "coordinator pending-cohort contract", contract=contract))
    payload = {"snapshot_at_utc": timestamp, "published_base_sha": BASE, "reporting_code_parent_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "sources": sources,
               "agentrx_rows": rx, "agentrx_groups": rg, "harnessrisk_rows": risk, "harnessrisk_groups": hg,
               "phase2_pending": pending, "self_check": "PASS: fixed rows, calls, producer native aggregates, bounds and S+F+U=N reconciled; no grading or labels read",
               "limitations": ["No statistical confidence intervals", "No model/provider/grader invocation", "No positive assisted gain established", "Costs and human wait unavailable", "Raw native utility can credit textual fallback/incomplete runs", "Unlike benchmarks/cohorts never pooled"]}
    (args.output / "chart-source.json").write_text(json.dumps(payload, indent=2) + "\n")
    figure1(rg, args.output, timestamp)
    figure2(hg, args.output, timestamp, pending)
    table(rg, hg, args.output)
    print(f"PASS: {len(rx)} AgentRx + {len(risk)} HarnessRisk original rows; two SVGs; no provider or grader calls")


if __name__ == "__main__":
    main()
