"""Snapshot: everything a frozen run read, saved at freeze. The sandbox's only input.

File: data/snapshots/<incident_id>.json
{id, incident_id, run_id, agent, task, system, model_id, entrypoint, policy, legit, taken_at,
 tool_results: [{call_id, tool, args, result}],
 inputs: [{id, kind, label, source_tool, preview, item}]}

Each item a read tool returned (one calendar event, one contact...) is one Input. Bisection
removes an input by dropping that item from every tool result.
"""

import copy
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import Input

SNAP_DIR = Path(os.getenv("MIRAGE_SNAPSHOTS", "data/snapshots"))
KINDS = [("calendar", "calendar_event"), ("contact", "crm_record"), ("crm", "crm_record"),
         ("mail", "email"), ("inbox", "email"), ("url", "web_page"), ("web", "web_page")]


def _items(result):
    """The list of records inside a tool result: a list, or the one list inside a dict."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        lists = [v for v in result.values() if isinstance(v, list)]
        return lists[0] if len(lists) == 1 else []
    return []


def _text(item, *keys):
    return next((str(item[k]) for k in keys if isinstance(item, dict) and item.get(k)), "")


def _inputs(task, tool_results):
    found = [{"id": "in_task", "kind": "user_task", "label": "User task", "source_tool": None,
              "preview": task[:160], "item": None}]
    seen = []
    for r in tool_results:
        for item in _items(r["result"]):
            if item in seen:
                continue
            seen.append(item)
            kind = next((k for word, k in KINDS if word in r["tool"]), "attachment")
            found.append({
                "id": f"in_{len(found):02d}", "kind": kind, "source_tool": r["tool"],
                "label": _text(item, "title", "name", "subject", "url") or r["tool"],
                "preview": _text(item, "description", "body", "notes", "email")[:160],
                "item": item,
            })
    return found


def save(run, incident_id, policy, entrypoint=""):
    results = [{k: r[k] for k in ("call_id", "tool", "args", "result")}
               for r in run.tool_results if not r.get("error")]
    snap = {
        "id": f"snap_{incident_id.removeprefix('inc_')}", "incident_id": incident_id,
        "run_id": run.id, "agent": run.agent, "task": run.task, "system": run.system,
        "model_id": run.model_id, "entrypoint": run.entrypoint or entrypoint,
        "policy": policy, "legit": run.legit, "taken_at": datetime.now(UTC).isoformat(),
        "tool_results": results, "inputs": _inputs(run.task, results),
    }
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{incident_id}.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    return snap


def load(incident_id):
    return json.loads((SNAP_DIR / f"{incident_id}.json").read_text(encoding="utf-8"))


def inputs(snap) -> list[Input]:
    return [Input(**{k: v for k, v in i.items() if k != "item"}) for i in snap["inputs"]]


def without(snap, input_id):
    """A copy of the snapshot with one input removed (bisection)."""
    snap = copy.deepcopy(snap)
    target = next(i for i in snap["inputs"] if i["id"] == input_id)
    if target["kind"] == "user_task":
        snap["task"] = "(no task)"
    for r in snap["tool_results"]:
        items = _items(r["result"])
        if target["item"] in items:
            items[:] = [x for x in items if x != target["item"]]
    return snap
