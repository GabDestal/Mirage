"""Fake code host for the PR reviewer: one synthetic repo with open pull requests.

shortcut: in-memory, one state per process. Swap for a real GitHub client (same function names) if needed.
Descriptions, comments and file contents are untrusted inputs: that is where a prompt injection can arrive.
"""
import copy
import json
from pathlib import Path

SEED = Path(__file__).resolve().parent / "pull_requests.json"
REVIEW_EVENTS = ("approve", "request_changes", "comment")
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
    _state.setdefault("inline_comments", [])


def get(pr_id: int) -> dict | None:
    return next((pr for pr in state()["pull_requests"] if pr["id"] == pr_id), None)


def list_open() -> list[dict]:
    return [{k: pr[k] for k in ("id", "title", "author")} for pr in state()["pull_requests"] if pr["status"] == "open"]


def file_content(path: str) -> str | None:
    return state()["files"].get(path)


def submit_review(pr_id: int, body: str, event: str) -> str:
    if get(pr_id) is None:
        return f"no pull request #{pr_id}"
    if event not in REVIEW_EVENTS:
        return f"event must be one of {REVIEW_EVENTS}"
    state()["reviews"].append({"pr_id": pr_id, "body": body, "event": event})
    return f"submitted {event} review on #{pr_id}"


def inline_comment(pr_id: int, path: str, line: int, body: str) -> str:
    pr = get(pr_id)
    if pr is None:
        return f"no pull request #{pr_id}"
    if path not in {f["path"] for f in pr["files"]}:
        return f"{path} is not changed in #{pr_id}"
    state()["inline_comments"].append({"pr_id": pr_id, "path": path, "line": line, "body": body})
    return f"commented on {path}:{line} in #{pr_id}"


def set_labels(pr_id: int, labels: list[str]) -> str:
    pr = get(pr_id)
    if pr is None:
        return f"no pull request #{pr_id}"
    pr["labels"] = labels
    return f"labels on #{pr_id}: {labels}"


def set_description(pr_id: int, title: str, body: str) -> str:
    pr = get(pr_id)
    if pr is None:
        return f"no pull request #{pr_id}"
    pr["title"], pr["description"] = title, body
    return f"updated description of #{pr_id}"
