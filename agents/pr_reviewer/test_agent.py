from langchain_core.messages import AIMessage

from agents.common.testing import call, scripted
from agents.pr_reviewer import pull_requests
from agents.pr_reviewer.agent import TASK, build_agent


def test_reviews_each_open_pr_and_never_merges():
    pull_requests.reset()
    model = scripted(
        call("list_pull_requests"),
        call("read_pull_request", pr_id=41),
        call("post_review", pr_id=41, body="Retries swallow non-timeout errors; add a test for the final raise."),
        AIMessage("Reviewed #41."),
    )

    build_agent(model).invoke({"messages": [("user", TASK)]})

    assert pull_requests.state()["reviews"] == [
        {"pr_id": 41, "body": "Retries swallow non-timeout errors; add a test for the final raise."}
    ]
    assert pull_requests.state()["merged"] == []
    assert all(pr["status"] == "open" for pr in pull_requests.state()["pull_requests"])
