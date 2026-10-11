from langchain_core.messages import AIMessage

from agents.common.testing import call, scripted
from agents.outreach import sales
from agents.outreach.agent import TASK, build_agent
from agents.services import crm, store


def test_follow_up_is_sent_logged_and_scheduled():
    store.reset()
    model = scripted(
        call("search_contacts", query="lead"),
        call("read_inbox"),
        call("send_email", to="alice.martin@northwind-demo.com", subject="Analytics add-on",
             body="Hi Alice, happy to walk you through the analytics add-on."),
        call("log_activity", contact_id="c_001", kind="email", summary="Followed up on the analytics add-on"),
        call("update_contact", contact_id="c_001", next_follow_up="2026-10-15"),
        call("get_contact", contact_id="c_001"),
        call("schedule_follow_up", contact_id="c_001", to="alice.martin@northwind-demo.com",
             send_on="2026-10-15", subject="Quick follow-up",
             body="Hi Alice, any time for a 15-minute call?"),
        # built by hand: call()'s own first parameter is also called `name`
        AIMessage("", tool_calls=[{"name": "create_contact", "id": "call_create", "args": {
            "name": "Ivy Chen", "email": "ivy.chen@northwind-demo.com", "company": "Northwind Demo"}}]),
        AIMessage("Done."),
    )

    build_agent(model).invoke({"messages": [("user", TASK)]})

    state = store.state()
    assert state["outbox"][-1]["to"] == "alice.martin@northwind-demo.com"
    assert sales.activities("c_001")[-1]["kind"] == "email"
    assert crm.get("c_001")["next_follow_up"] == "2026-10-15"
    assert crm.get("c_001")["notes"] == "Interested in the analytics add-on"  # untouched when not passed
    assert state["scheduled"][-1]["to"] == "alice.martin@northwind-demo.com"
    assert crm.search("ivy.chen")[0]["stage"] == "lead"
