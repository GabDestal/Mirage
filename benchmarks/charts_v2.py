"""Render the two v2 benchmark headline charts from saved summary JSON (reporting only).

Metrics are raw counts {"k": successes, "n": fixed denominator}; None = not run yet.
Errors/UNKNOWN stay in n and never count as k. Whiskers are Wilson 95% intervals.
Also writes v2-chart-source.json with every number drawn, for the doc table.
"""
import argparse
from html import escape
import json
from math import sqrt
from pathlib import Path

from benchmarkmaxxing_charts import MODELS

W, H = 1600, 900
INK, MUTED, FAINT, BASE = "#111111", "#6b6b6b", "#a3a3a3", "#d4d4d4"
GREY, ACCENT, WHISKER = "#c8c8c8", "#0f7b6c", "#9a9a9a"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
LABELS = {"openai.gpt-oss-20b-1:0": "GPT-OSS-20B", "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Haiku 4.5"}


def wilson(k, n, z=1.96):
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


class SVG:
    def __init__(self):
        self.parts = []

    def text(self, x, y, s, size=18, weight=400, color=INK, anchor="start"):
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
                          f'fill="{color}" text-anchor="{anchor}">{escape(str(s))}</text>')

    def rect(self, x, y, w, h, fill):
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>')

    def line(self, x1, y1, x2, y2, color=BASE, width=1):
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"/>')

    def save(self, path, title):
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                        f'role="img"><title>{escape(title)}</title><rect width="100%" height="100%" fill="#ffffff"/>'
                        f'<g font-family="{FONT}">' + "".join(self.parts) + "</g></svg>\n")


def ok(m):
    return bool(m and m.get("n"))


def frac(m):
    return f'{m["k"]}/{m["n"]}' if ok(m) else "not run"


def bar(svg, x, bw, m, color, label, top, base):
    """One labelled bar with a big value on top; a plain 'not run yet' when missing."""
    mid, span = x + bw / 2, base - top
    if ok(m):
        v, (lo, hi) = m["k"] / m["n"], wilson(m["k"], m["n"])
        svg.rect(x, base - v * span, bw, max(v * span, 3), color)
        svg.line(mid, base - hi * span, mid, base - lo * span, WHISKER, 1)
        for y in (base - hi * span, base - lo * span):
            svg.line(mid - 5, y, mid + 5, y, WHISKER, 1)
        svg.text(mid, base - hi * span - 16, f"{v:.0%}", 44, 600, INK, "middle")
    else:
        svg.text(mid, base - 14, "not run yet", 20, 400, FAINT, "middle")
    svg.text(mid, base + 36, label, 20, 500 if color == ACCENT else 400, INK, "middle")


def frame(svg, title, subtitle, lines):
    svg.text(80, 96, title, 44, 600)
    svg.text(80, 140, subtitle, 22, 400, MUTED)
    svg.text(80, 818, lines[0], 21, 400, MUTED)
    svg.text(80, 852, lines[1], 21, 500, INK)


def agentdojo(data, out):
    splits, model = data.get("splits", {}), data.get("model") or "GPT-OSS-20B"
    held = "held_out" in splits
    s = splits.get("held_out") or splits.get("dev") or {}
    u, g = s.get("unprotected", {}), s.get("gate", {})
    n = next((m["n"] for m in (u.get("attacker_success"), g.get("attacker_success")) if ok(m)), None)
    svg = SVG()
    where = "Held-out tasks" if held else "Tuning tasks only (held-out run not in yet)"
    frame(svg, "AgentDojo: prompt-injection attacks",
          f"{where} · {n} attacked tasks per bar" if n else f"{where} · results not in yet",
          ["Each task hides instructions from an attacker in data the agent reads, like a message or a web page.",
           result_line(u, g)])
    top, base = 300, 700
    for x0, key, head, hint in [(80, "attacker_success", "Attacks that succeeded", "lower is better"),
                                (840, "utility_under_attack", "User's task still completed", "higher is better")]:
        svg.text(x0, 214, head, 26, 600)
        svg.text(x0, 246, hint, 19, 400, MUTED)
        svg.line(x0, base, x0 + 680, base)
        for i, (arm, color, label) in enumerate([(u, GREY, model), (g, ACCENT, model + " + Mirage")]):
            bar(svg, x0 + 90 + i * 300, 200, arm.get(key), color, label, top, base)
    svg.save(out / "agentdojo-v2-headline.svg", "AgentDojo prompt-injection attacks, with and without Mirage")


def result_line(u, g):
    a, b = u.get("attacker_success"), g.get("attacker_success")
    if not (ok(a) and ok(b)):
        return "Both arms are not in yet, so there is no comparison to read."
    c, d = u.get("utility_under_attack"), g.get("utility_under_attack")
    return (f"With Mirage, {b['k']} of {b['n']} attacks succeeded instead of {a['k']} of {a['n']}; "
            f"the user's task was still done in {d['k']} of {d['n']} (vs {c['k']} of {c['n']} without).")


def agentrx(data, out):
    models = data.get("models", [])
    n = next((m["n"] for x in models for m in (x.get("simple"), x.get("assisted")) if ok(m)), None)
    held = data.get("split", "").startswith("heldout")
    where = "Held-out task families" if held else "Tuning cases only (held-out run not in yet)"
    found = "; ".join(f'{x["label"]} {frac(x.get("simple"))} → {frac(x.get("assisted"))} with Mirage' for x in models)
    svg = SVG()
    frame(svg, "AgentRx: finding where a failed agent run went wrong",
          f"{where} · higher is better · {n} failed runs per bar" if n else f"{where} · results not in yet",
          ["Each case is a recorded agent run that failed; the model must name the exact step where it broke.",
           f"Broken step found: {found}." if found else "No results are in yet."])
    top, base = 260, 700
    svg.line(80, base, 1520, base)
    for j, x in enumerate(models[:2]):
        for i, (key, color, label) in enumerate([("simple", GREY, x["label"]), ("assisted", ACCENT, x["label"] + " + Mirage")]):
            bar(svg, 150 + j * 720 + i * 290, 220, x.get(key), color, label, top, base)
    if not models:
        svg.text(W / 2, (top + base) / 2, "not run yet", 28, 400, FAINT, "middle")
    svg.save(out / "agentrx-v3-critical-step.svg", "AgentRx critical-step accuracy, with and without Mirage evidence")


def load(path):
    return json.loads(path.read_text()) if path and path.exists() else {}


def from_agentdojo(raw, path):
    """W1 summary: {"<dev|heldout>/<arm>": {"attack": {n, attacker_success, utility}, "clean": {n, utility}}}."""
    splits = {}
    for key, s in raw.items():
        if "/" not in key:
            continue
        split, arm = key.split("/")
        a, c = s.get("attack", {}), s.get("clean", {})
        splits.setdefault({"heldout": "held_out"}.get(split, split), {})[arm] = {
            "attacker_success": {"k": a.get("attacker_success", 0), "n": a.get("n", 0)},
            "utility_under_attack": {"k": a.get("utility", 0), "n": a.get("n", 0)},
            "clean_utility": {"k": c.get("utility", 0), "n": c.get("n", 0)},
            "unknown": s.get("unknown"), "blocks": s.get("blocks")}
    ids = {json.loads(l).get("model_id") for p in path.parent.glob("*_rows.jsonl") for l in p.read_text().splitlines() if l}
    model = LABELS.get(ids.pop()) if len(ids) == 1 else None
    return {"splits": splits, "source": str(path), "model": model}


def from_agentrx(raw, path):
    """W3 summary: cohorts -> tables of {model_id, arm, critical_step_correct: {S, N, scored, U}}; held-out preferred."""
    cohorts = raw.get("cohorts", {})
    name = "families" if cohorts.get("families", {}).get("tables") else next(iter(cohorts), None)
    if name is None:
        return {"source": str(path)}
    models = {}
    for t in cohorts[name]["tables"]:
        m = t["critical_step_correct"]
        arm = "simple" if t["arm"] == "simple_diagnosis" else "assisted"
        label = LABELS.get(t["model_id"], MODELS.get(t["model_id"], t["model_id"]))
        models.setdefault(t["model_id"], {"label": label})[arm] = {"k": m["S"], "n": m["N"], "scored": m["scored"]}
    return {"models": list(models.values()), "split": cohorts[name]["split"], "source": str(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agentdojo", type=Path, default=Path("benchmarks/artifacts/agentdojo_v2/summary.json"))
    p.add_argument("--agentrx", type=Path, default=Path("benchmarks/artifacts/agentrx_v3/summary.json"))
    p.add_argument("--output", type=Path, default=Path("docs/benchmarkmaxxing"))
    a = p.parse_args()
    lo, hi = wilson(0, 10)
    assert lo == 0 and 0.27 < hi < 0.28 and wilson(5, 10)[0] < 0.5 < wilson(5, 10)[1]
    dojo, rx = from_agentdojo(load(a.agentdojo), a.agentdojo), from_agentrx(load(a.agentrx), a.agentrx)
    agentdojo(dojo, a.output)
    agentrx(rx, a.output)
    (a.output / "v2-chart-source.json").write_text(json.dumps({"agentdojo": dojo, "agentrx": rx}, indent=2) + "\n")
    print(json.dumps({"agentdojo": dojo, "agentrx": rx}))


if __name__ == "__main__":
    main()
