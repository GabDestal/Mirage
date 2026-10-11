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


def test_invoice_lifecycle_tools():
    store.reset()
    invoices.reset()
    model = scripted(
        call("create_invoice", contact_id="c_006", amount_eur=500, due="2026-11-30"),
        call("get_invoice", invoice_id="INV-1044"),
        call("get_contact", contact_id="c_006"),
        call("send_invoice", invoice_id="INV-1044", to="farid.haddad@litware-demo.com",
             subject="Invoice INV-1044", body="Dear Farid Haddad,\n\nPlease find invoice INV-1044 "
             "for 500.0 EUR, due 2026-11-30.\n\nMirage Demo SAS"),
        call("record_payment", invoice_id="INV-1044", amount_eur=200),
        call("record_payment", invoice_id="INV-1044", amount_eur=300),
        AIMessage("Invoiced and collected."),
    )

    build_agent(model).invoke({"messages": [("user", "Invoice Farid 500 EUR and record his two payments.")]})

    assert store.state()["outbox"][0]["to"] == "farid.haddad@litware-demo.com"
    assert invoices.get("INV-1044")["status"] == "paid"
