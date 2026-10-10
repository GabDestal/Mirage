from langchain_core.messages import AIMessage

from agents.common.testing import call, scripted
from agents.invoicing import invoices
from agents.invoicing.agent import TASK, build_agent
from agents.services import store


def test_reminds_overdue_invoice():
    store.reset()
    invoices.reset()
    model = scripted(
        call("list_invoices", status="overdue"),
        call("get_contact", contact_id="c_004"),
        call("send_email", to="david.kim@tailspin-demo.com", subject="Reminder: INV-1042",
             body="Hi David, a friendly reminder that INV-1042 is overdue."),
        call("mark_reminded", invoice_id="INV-1042"),
        AIMessage("Reminded David Kim about INV-1042."),
    )

    build_agent(model).invoke({"messages": [("user", TASK)]})

    assert store.state()["outbox"] == [{"to": "david.kim@tailspin-demo.com", "subject": "Reminder: INV-1042",
                                        "body": "Hi David, a friendly reminder that INV-1042 is overdue."}]
    assert next(i for i in invoices.all_invoices() if i["id"] == "INV-1042")["reminded"] is True
