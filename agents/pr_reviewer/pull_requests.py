"""Fake code host for the PR reviewer: one synthetic repo with open pull requests.

shortcut: in-memory, one state per process. Swap for a real GitHub client (same function names) if needed.
Descriptions and comments are untrusted inputs: that is where a prompt injection can arrive.
"""
import copy
import json
from pathlib import Path

SEED = Path(__file__).resolve().parent / "pull_requests.json"
_state = None


def state() -> dict:
    global _state
    if _state is None:
        reset()
    return _state


def reset(seed: dict | None = None) -> None:
    global _state
    _state = copy.deepcopy(seed) if seed is not None else json.loads(SEED.read_text())
    _state.setdefault("reviews", [])
    _state.setdefault("merged", [])


def get(pr_id: int) -> dict | None:
    return next((pr for pr in state()["pull_requests"] if pr["id"] == pr_id), None)


def list_open() -> list[dict]:
    return [{k: pr[k] for k in ("id", "title", "author")} for pr in state()["pull_requests"] if pr["status"] == "open"]


def post_review(pr_id: int, body: str) -> str:
    if get(pr_id) is None:
        return f"no pull request #{pr_id}"
    state()["reviews"].append({"pr_id": pr_id, "body": body})
    return f"posted review on #{pr_id}"


def merge(pr_id: int) -> str:
    pr = get(pr_id)
    if pr is None:
        return f"no pull request #{pr_id}"
    pr["status"] = "merged"
    state()["merged"].append(pr_id)
    return f"merged #{pr_id}"
