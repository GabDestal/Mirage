from langchain_core.messages import AIMessage

from agents.common.testing import call, scripted
from agents.outreach.agent import TASK, build_agent
from agents.services import crm, store


def test_follow_up_is_sent_and_logged():
    store.reset()
    model = scripted(
        call("search_contacts", query="lead"),
        call("send_email", to="alice.martin@northwind-demo.com", subject="Analytics add-on",
             body="Hi Alice, happy to walk you through the analytics add-on."),
        call("update_contact", contact_id="c_001", notes="Followed up on the analytics add-on"),
        AIMessage("Done."),
    )

    build_agent(model).invoke({"messages": [("user", TASK)]})

    assert store.state()["outbox"][-1]["to"] == "alice.martin@northwind-demo.com"
    assert crm.get("c_001")["notes"] == "Followed up on the analytics add-on"
