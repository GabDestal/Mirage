"""Render the v2 benchmark charts from saved summary JSON and rows (reporting only).

Metrics are raw counts {"k": successes, "n": fixed denominator}; None = not run yet.
Errors/UNKNOWN stay in n and never count as k. No error bars on the images by design;
v2-chart-source.json keeps every number drawn.
"""
import argparse
from html import escape
import json
from pathlib import Path

from benchmarkmaxxing_charts import MODELS

W, H = 1600, 900
INK, MUTED, FAINT, BASE = "#111111", "#6b6b6b", "#a3a3a3", "#d4d4d4"
GREY, ACCENT = "#c8c8c8", "#0f7b6c"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
LABELS = {"openai.gpt-oss-20b-1:0": "GPT-OSS-20B", "openai.gpt-oss-120b-1:0": "GPT-OSS-120B",
          "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Haiku 4.5", "us.anthropic.claude-opus-4-8": "Opus 4.8"}
ORDER = list(LABELS)


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


def sort_models(ids):
    return sorted(ids, key=lambda m: (ORDER.index(m) if m in ORDER else 99, m))


def bar(svg, x, bw, m, color, label, top, base):
    """One vertical labelled bar with a big value on top; a plain 'not run yet' when missing."""
    mid, span = x + bw / 2, base - top
    if ok(m):
        v = m["k"] / m["n"]
        svg.rect(x, base - v * span, bw, max(v * span, 3), color)
        svg.text(mid, base - v * span - 16, f"{v:.0%}", 44, 600, INK, "middle")
    else:
        svg.text(mid, base - 14, "not run yet", 20, 400, FAINT, "middle")
    svg.text(mid, base + 36, label, 20, 500 if color == ACCENT else 400, INK, "middle")


def hbar(svg, x, y, bh, m, color, label, width):
    """One horizontal bar: label on the left, value at the bar end."""
    svg.text(x - 16, y + bh * 0.72, label, 19, 500 if color == ACCENT else 400, INK, "end")
    if not ok(m):
        svg.text(x + 8, y + bh * 0.72, "not run yet", 18, 400, FAINT)
        return
    v = m["k"] / m["n"]
    svg.rect(x, y, max(v * width, 3), bh, color)
    svg.text(x + max(v * width, 3) + 12, y + bh * 0.78, f"{v:.0%}", 26, 600)


def frame(svg, title, subtitle, lines):
    svg.text(80, 96, title, 44, 600)
    svg.text(80, 140, subtitle, 22, 400, MUTED)
    svg.text(80, 818, lines[0], 21, 400, MUTED)
    svg.text(80, 852, lines[1], 21, 500, INK)


def panels(svg, s, models, specs, label_w=150, width=250):
    """Side-by-side panels of model / '+ Mirage' horizontal bar pairs, one metric each."""
    for x0, key, head, hint in specs:
        svg.text(x0, 214, head, 26, 600)
        svg.text(x0, 246, hint, 19, 400, MUTED)
        y, bx = 286, x0 + label_w
        svg.line(bx, y - 10, bx, y + len(models) * 92 - 18)
        for model in models:
            hbar(svg, bx, y, 30, s[model].get("unprotected", {}).get(key), GREY, LABELS.get(model, model), width)
            hbar(svg, bx, y + 36, 30, s[model].get("gate", {}).get(key), ACCENT, "+ Mirage", width)
            y += 92
        if not models:
            svg.text(bx + 8, y + 22, "not run yet", 20, 400, FAINT)


def pooled(s, arm, key):
    ms = [m[arm][key] for m in s.values() if ok(m.get(arm, {}).get(key))]
    return sum(m["k"] for m in ms), sum(m["n"] for m in ms)


def agentdojo(data, out):
    splits = data.get("splits", {})
    held = "held_out" in splits
    s = splits.get("held_out") or splits.get("dev") or {}
    models = sort_models(s)
    na = sorted({a["attacker_success"]["n"] for m in s.values() for a in m.values() if ok(a.get("attacker_success"))})
    nc = sorted({a["clean_utility"]["n"] for m in s.values() for a in m.values() if ok(a.get("clean_utility"))})
    where = "Held-out tasks" if held else "Tuning tasks only (held-out run not in yet)"
    per = (f"{'–'.join(map(str, sorted({na[0], na[-1]})))} attacked and {'–'.join(map(str, sorted({nc[0], nc[-1]})))} "
           "normal tasks per bar") if na and nc else "results not in yet"
    (a, an), (b, bn) = pooled(s, "unprotected", "attacker_success"), pooled(s, "gate", "attacker_success")
    (c, cn), (d, dn) = pooled(s, "unprotected", "utility_under_attack"), pooled(s, "gate", "utility_under_attack")
    (e, en), (f, fn) = pooled(s, "unprotected", "clean_utility"), pooled(s, "gate", "clean_utility")
    result = (f"Mirage cut successful attacks from {a} of {an} to {b} of {bn}, but fewer tasks got done "
              f"({d} vs {c} of {cn} attacked, {f} vs {e} of {en} normal).") if an and bn else "Not all results are in yet."
    svg = SVG()
    frame(svg, "AgentDojo: prompt-injection attacks", f"{where} · {per}",
          ["Each attacked task hides an attacker's instructions in data the agent reads, like a message or a web page.",
           result])
    panels(svg, s, models, [(80, "attacker_success", "Attacks that succeeded", "lower is better"),
                            (580, "utility_under_attack", "Task done under attack", "higher is better"),
                            (1080, "clean_utility", "Normal tasks completed", "no attack · higher is better")])
    svg.save(out / "agentdojo-v2-headline.svg", "AgentDojo prompt-injection attacks, with and without Mirage")


def stops(data, out):
    s = data.get("stops", {})
    models = sort_models(s)
    svg = SVG()
    frame(svg, "What Mirage stopped", "Held-out AgentDojo tasks, run with Mirage",
          ["Share of tasks where Mirage stopped at least one of the agent's actions.",
           "Almost every stop comes from one rule: the action used a link or address the user never gave."])
    for x0, key, head, color in [(80, "attack", "Attacked tasks stopped", ACCENT),
                                 (840, "clean", "Normal tasks wrongly stopped", GREY)]:
        n = sorted({m[key]["n"] for m in s.values() if ok(m.get(key))})
        hint = f"of {'–'.join(map(str, sorted({n[0], n[-1]})))} {'attacked' if key == 'attack' else 'normal'} tasks per model" if n else ""
        svg.text(x0, 214, head, 26, 600)
        svg.text(x0, 246, hint, 19, 400, MUTED)
        y, bx = 300, x0 + 170
        svg.line(bx, y - 14, bx, y + len(models) * 100 - 30)
        for model in models:
            hbar(svg, bx, y, 44, s[model].get(key), color, LABELS.get(model, model), 400)
            y += 100
        if not models:
            svg.text(bx + 8, y + 22, "not run yet", 20, 400, FAINT)
    svg.save(out / "agentdojo-v2-stops.svg", "What Mirage stopped on held-out AgentDojo tasks")


def agentrx(data, out):
    models = data.get("models", [])
    n = next((m["n"] for x in models for m in (x.get("simple"), x.get("assisted")) if ok(m)), None)
    held = data.get("split", "").startswith("heldout")
    where = "Held-out task families" if held else "Tuning cases only (held-out run not in yet)"
    found = "; ".join(f'{x["label"]} {frac(x.get("simple"))} → {frac(x.get("assisted"))} with Mirage' for x in models)
    svg = SVG()
    frame(svg, "AgentRx: finding where a failed agent run went wrong",
          f"{where} · higher is better · {n} failed runs per bar" if n else f"{where} · results not in yet",
          ["Each case is a recorded agent run that failed; the model must name the step where it broke (no answer = miss).",
           f"Broken step found: {found}." if found else "No results are in yet."])
    top, base = 260, 700
    svg.line(80, base, 1520, base)
    for j, x in enumerate(models[:2]):
        for i, (key, color, label) in enumerate([("simple", GREY, x["label"]), ("assisted", ACCENT, "+ Mirage")]):
            bar(svg, 150 + j * 720 + i * 290, 220, x.get(key), color, label, top, base)
    if not models:
        svg.text(W / 2, (top + base) / 2, "not run yet", 28, 400, FAINT, "middle")
    svg.save(out / "agentrx-v3-critical-step.svg", "AgentRx critical-step accuracy, with and without Mirage evidence")


def load(path):
    return json.loads(path.read_text()) if path and path.exists() else {}


def from_agentdojo(raw, path, rows_dir):
    """W1 summary: {"<dev|heldout>/[<model_id>/]<arm>": {"attack": {n, attacker_success, utility}, "clean": {n, utility}}}.
    Stops are recomputed from held-out gate rows: a task counts as stopped when its blocked list is non-empty."""
    splits = {}
    for key, s in raw.items():
        parts = key.split("/")
        if len(parts) not in (2, 3):
            continue
        split, arm, model = parts[0], parts[-1], parts[1] if len(parts) == 3 else "openai.gpt-oss-20b-1:0"
        a, c = s.get("attack", {}), s.get("clean", {})
        splits.setdefault({"heldout": "held_out"}.get(split, split), {}).setdefault(model, {})[arm] = {
            "attacker_success": {"k": a.get("attacker_success", 0), "n": a.get("n", 0)},
            "utility_under_attack": {"k": a.get("utility", 0), "n": a.get("n", 0)},
            "clean_utility": {"k": c.get("utility", 0), "n": c.get("n", 0)},
            "unknown": s.get("unknown"), "blocks": s.get("blocks"), "false_blocks": c.get("false_blocks")}
    stops, rules = {}, {}
    for p in sorted(rows_dir.glob("heldout__*_rows.jsonl")):
        for row in map(json.loads, filter(str.strip, p.read_text().splitlines())):
            if row["arm"] != "gate":
                continue
            m = stops.setdefault(row["model_id"], {}).setdefault(row["cohort"], {"k": 0, "n": 0})
            m["n"] += 1
            m["k"] += bool(row.get("blocked"))
            for rule in row.get("blocked") or []:
                rules[str(rule)] = rules.get(str(rule), 0) + 1
    return {"splits": splits, "stops": stops, "stop_rules": rules, "source": str(path), "rows": str(rows_dir)}


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
    p.add_argument("--agentdojo", type=Path, default=Path("docs/benchmarkmaxxing/v2-inputs/agentdojo_v2_summary.json"))
    p.add_argument("--agentdojo-rows", type=Path, default=Path("benchmarks/artifacts/agentdojo_v2"))
    p.add_argument("--agentrx", type=Path, default=Path("docs/benchmarkmaxxing/v2-inputs/agentrx_v3_summary.json"))
    p.add_argument("--output", type=Path, default=Path("docs/benchmarkmaxxing"))
    a = p.parse_args()
    dojo = from_agentdojo(load(a.agentdojo), a.agentdojo, a.agentdojo_rows)
    rx = from_agentrx(load(a.agentrx), a.agentrx)
    for model, s in dojo["stops"].items():  # rows and summary must describe the same fixed task set
        held = dojo["splits"].get("held_out", {}).get(model, {}).get("gate", {})
        assert not held or (s["attack"]["n"], s["clean"]["n"]) == (held["attacker_success"]["n"], held["clean_utility"]["n"]), model
    agentdojo(dojo, a.output)
    stops(dojo, a.output)
    agentrx(rx, a.output)
    (a.output / "v2-chart-source.json").write_text(json.dumps({"agentdojo": dojo, "agentrx": rx}, indent=2) + "\n")
    print(json.dumps({"stops": dojo["stops"], "stop_rules": dojo["stop_rules"]}))


if __name__ == "__main__":
    main()
