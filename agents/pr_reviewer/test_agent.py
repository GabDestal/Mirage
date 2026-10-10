from langchain_core.messages import AIMessage

from agents.common.testing import call, scripted
from agents.pr_reviewer import pull_requests
from agents.pr_reviewer.agent import TASK, build_agent


def test_reviews_a_pr_with_inline_comment_labels_and_verdict():
    pull_requests.reset()
    model = scripted(
        call("list_pull_requests"),
        call("read_pull_request", pr_id=41),
        call("read_file", path="billing/webhooks.py"),
        call("post_inline_comment", pr_id=41, path="billing/webhooks.py", line=14, body="Only Timeout is retried."),
        call("set_labels", pr_id=41, labels=["enhancement"]),
        call("submit_review", pr_id=41, body="Add a test for the final raise.", event="request_changes"),
        AIMessage("Reviewed #41."),
    )

    build_agent(model).invoke({"messages": [("user", TASK)]})

    s = pull_requests.state()
    assert s["reviews"] == [{"pr_id": 41, "body": "Add a test for the final raise.", "event": "request_changes"}]
    assert s["inline_comments"] == [
        {"pr_id": 41, "path": "billing/webhooks.py", "line": 14, "body": "Only Timeout is retried."}
    ]
    assert pull_requests.get(41)["labels"] == ["enhancement"]
    assert all(pr["status"] == "open" for pr in s["pull_requests"])


def test_rejects_unknown_review_event_and_unchanged_file():
    pull_requests.reset()
    assert pull_requests.submit_review(41, "x", "merge").startswith("event must be")
    assert pull_requests.inline_comment(41, "billing/tax.py", 1, "x") == "billing/tax.py is not changed in #41"
    assert pull_requests.state()["reviews"] == pull_requests.state()["inline_comments"] == []
