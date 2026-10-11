"""Render the two v2 benchmark headline charts from saved summary JSON (reporting only).

Input metrics are raw counts {"k": successes, "n": fixed denominator}; null = not run.
UNKNOWN outcomes stay in n and never count as k. Intervals are Wilson 95%.
"""
import argparse
from html import escape
import json
from math import sqrt
from pathlib import Path

from benchmarkmaxxing_charts import MODELS

W, H = 1600, 900
INK, MUTED, FAINT, GRID = "#111111", "#6b6b6b", "#9a9a9a", "#ececec"
GREY, ACCENT = "#c2c2c2", "#0f7b6c"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
DOJO_METRICS = [("attacker_success", "Attack success", "lower is better"),
                ("utility_under_attack", "Utility under attack", "higher is better"),
                ("clean_utility", "Clean utility", "higher is better")]


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

    def line(self, x1, y1, x2, y2, color=GRID, width=1):
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"/>')

    def save(self, path, title):
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                        f'role="img"><title>{escape(title)}</title><rect width="100%" height="100%" fill="#ffffff"/>'
                        f'<g font-family="{FONT}">' + "".join(self.parts) + "</g></svg>\n")


def pct(m):
    return f'{m["k"] / m["n"]:.0%}'


def header(svg, title, subtitle, arms):
    svg.text(80, 86, title, 40, 600)
    svg.text(80, 128, subtitle, 22, 400, MUTED)
    x = W - 80
    for label, color in reversed(arms):
        x -= svg_width(label, 18) + 22
        svg.rect(x, 62, 14, 14, color)
        svg.text(x + 22, 75, label, 18, 500)
        x -= 36


def svg_width(s, size):
    return len(s) * size * 0.55  # shortcut: rough Helvetica width, fine for short legend labels


def axis(svg, x0, x1, top, base, size):
    for t in (0, 25, 50, 75, 100):
        y = base - (base - top) * t / 100
        svg.line(x0, y, x1, y, GRID if t else "#bdbdbd")
        svg.text(x0 - 12, y + size * 0.35, f"{t}%", size, 400, FAINT, "end")


def bars(svg, cx, metrics, colors, bw, gap, top, base, size):
    """Draw one group of side-by-side bars centred on cx; metrics may hold None (not run)."""
    span = base - top
    for i, (m, color) in enumerate(zip(metrics, colors)):
        x = cx - (len(metrics) * bw + (len(metrics) - 1) * gap) / 2 + i * (bw + gap)
        if m is None or not m.get("n"):
            svg.text(x + bw / 2, base - 10, "not run", size * 0.8, 400, FAINT, "middle")
            continue
        v, (lo, hi) = m["k"] / m["n"], wilson(m["k"], m["n"])
        svg.rect(x, base - v * span, bw, max(v * span, 2), color)
        mid = x + bw / 2
        svg.line(mid, base - hi * span, mid, base - lo * span, "#3a3a3a", 1.5)
        for y in (base - hi * span, base - lo * span):
            svg.line(mid - 6, y, mid + 6, y, "#3a3a3a", 1.5)
        svg.text(mid, base - hi * span - 10, pct(m), size, 600, INK, "middle")


def n_label(metrics):
    ns = sorted({m["n"] for m in metrics if m and m.get("n")})
    return "n=" + " / ".join(map(str, ns)) if ns else "n=0"


def dojo_panel(svg, split, x0, x1, top, base, big):
    size = 20 if big else 14
    axis(svg, x0, x1, top, base, 16 if big else 13)
    gw = (x1 - x0) / len(DOJO_METRICS)
    for j, (key, label, hint) in enumerate(DOJO_METRICS):
        cx = x0 + gw * (j + 0.5)
        ms = [split.get(arm, {}).get(key) for arm in ("unprotected", "gate")]
        bars(svg, cx, ms, (GREY, ACCENT), 96 if big else 30, 14 if big else 6, top, base, size)
        if big:
            svg.text(cx, base + 34, label, 20, 600, INK, "middle")
            svg.text(cx, base + 58, hint, 16, 400, MUTED, "middle")
            svg.text(cx, base + 82, n_label(ms), 16, 400, MUTED, "middle")
        else:
            svg.text(cx, base + 24, label.replace("Utility under attack", "Attacked utility"), 14, 600, INK, "middle")
            svg.text(cx, base + 42, n_label(ms), 13, 400, MUTED, "middle")


def dojo_subtitle(held):
    u, g = held.get("unprotected", {}), held.get("gate", {})
    parts = []
    for key, label, _ in DOJO_METRICS[:2]:
        if u.get(key) and g.get(key):
            parts.append(f"{label.lower()} {pct(u[key])} → {pct(g[key])}")
    return ("Held-out: " + ", ".join(parts) + " with the Mirage gate") if parts else "Held-out results not landed yet"


def agentdojo(data, out):
    splits = data.get("splits", {})
    held, dev = splits.get("held_out", {}), splits.get("dev", {})
    svg = SVG()
    header(svg, "AgentDojo: Mirage gate vs unprotected agent", dojo_subtitle(held),
           [("Unprotected", GREY), ("Mirage gate", ACCENT)])
    top, base = 230, 680
    svg.text(80, 196, "Held-out split (run once, frozen config)", 20, 600)
    dojo_panel(svg, held, 150, 1080, top, base, True)
    svg.text(1150, 196, "Dev split (used for tuning)", 18, 600, MUTED)
    dojo_panel(svg, dev, 1200, 1530, top, base, False)
    caveats = data.get("caveats") or [
        "Fixed denominators: every error and UNKNOWN counts as not-success. Whiskers are Wilson 95% intervals.",
        f'Source: {data.get("source", "benchmarks/artifacts/agentdojo_v2")} · model {data.get("model") or "per row in rows JSONL"}']
    for i, line in enumerate(caveats[:2]):
        svg.text(80, 830 + i * 28, line, 16, 400, MUTED)
    svg.save(out / "agentdojo-v2-headline.svg", "AgentDojo attack success and utility, unprotected vs Mirage gate")


def agentrx(data, out):
    models = data.get("models", [])
    svg = SVG()
    deltas = [f'{m["label"]} {pct(m["simple"])} → {pct(m["assisted"])}' for m in models
              if m.get("simple") and m.get("assisted") and m["simple"].get("n") and m["assisted"].get("n")]
    header(svg, "AgentRx v3: critical-step accuracy", ("Simple → assisted: " + ", ".join(deltas)) if deltas
           else "AgentRx v3 results not landed yet", [("Simple diagnosis", GREY), ("Evidence-assisted", ACCENT)])
    x0, x1, top, base = 150, 1520, 210, 680
    axis(svg, x0, x1, top, base, 16)
    gw = (x1 - x0) / max(len(models), 1)
    for j, m in enumerate(models):
        cx = x0 + gw * (j + 0.5)
        ms = [m.get("simple"), m.get("assisted")]
        bars(svg, cx, ms, (GREY, ACCENT), 110, 16, top, base, 20)
        for i, a in enumerate(ms):
            if a and a.get("n") and a.get("scored") is not None:
                svg.text(cx + (i - 0.5) * 126, base + 24, f'scored {a["scored"]}/{a["n"]}', 14, 400, FAINT, "middle")
        svg.text(cx, base + 56, m["label"], 20, 600, INK, "middle")
        svg.text(cx, base + 80, n_label(ms), 16, 400, MUTED, "middle")
    if not models:
        svg.text(W / 2, (top + base) / 2, "not run", 24, 400, FAINT, "middle")
    caveats = data.get("caveats") or [
        "Accuracy over the fixed case set: unscored (UNKNOWN) cases count as wrong. Whiskers are Wilson 95% intervals.",
        f'Source: {data.get("source", "benchmarks/artifacts/agentrx_v3")} · split {data.get("split", "see summary JSON")}']
    for i, line in enumerate(caveats[:2]):
        svg.text(80, 830 + i * 28, line, 16, 400, MUTED)
    svg.save(out / "agentrx-v3-critical-step.svg", "AgentRx v3 critical-step accuracy, simple vs assisted")


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
            "clean_utility": {"k": c.get("utility", 0), "n": c.get("n", 0)}}
    return {"splits": splits, "source": str(path), "model": raw.get("model")}


def from_agentrx(raw, path):
    """W3 summary: cohorts -> tables of {model_id, arm, critical_step_correct: {S, N, scored, U}}; held-out preferred."""
    cohorts = raw.get("cohorts", {})
    name = "families" if "families" in cohorts else next(iter(cohorts), None)
    if name is None:
        return {"source": str(path)}
    models = {}
    for t in cohorts[name]["tables"]:
        m = t["critical_step_correct"]
        arm = "simple" if t["arm"] == "simple_diagnosis" else "assisted"
        models.setdefault(t["model_id"], {"label": MODELS.get(t["model_id"], t["model_id"]).replace(" reference", "")})[arm] = {
            "k": m["S"], "n": m["N"], "scored": m["scored"]}
    return {"models": list(models.values()), "split": cohorts[name]["split"], "source": str(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agentdojo", type=Path, default=Path("benchmarks/artifacts/agentdojo_v2/summary.json"))
    p.add_argument("--agentrx", type=Path, default=Path("benchmarks/artifacts/agentrx_v3/summary.json"))
    p.add_argument("--output", type=Path, default=Path("docs/benchmarkmaxxing"))
    a = p.parse_args()
    lo, hi = wilson(0, 10)
    assert lo == 0 and 0.27 < hi < 0.28 and wilson(5, 10)[0] < 0.5 < wilson(5, 10)[1]
    agentdojo(from_agentdojo(load(a.agentdojo), a.agentdojo), a.output)
    agentrx(from_agentrx(load(a.agentrx), a.agentrx), a.output)
    print("wrote agentdojo-v2-headline.svg, agentrx-v3-critical-step.svg")


if __name__ == "__main__":
    main()
