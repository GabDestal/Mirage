import pytest

from agents.invoicing import invoices


@pytest.fixture(autouse=True)
def reset_invoices(monkeypatch):
    monkeypatch.setattr(invoices, "_invoices", None)
    invoices.reset()


def test_marked_invoice_is_no_longer_eligible_for_reminder():
    assert [i["id"] for i in invoices.by_status("overdue")] == ["INV-1039", "INV-1042"]

    assert invoices.mark_reminded("INV-1039") == "marked INV-1039 as reminded"

    assert [i["id"] for i in invoices.by_status("overdue")] == ["INV-1042"]
    assert invoices.get("INV-1039")["status"] == "overdue"
    assert invoices.get("INV-1039")["reminded"] is True


def test_repeated_reminder_pass_does_not_select_invoices_twice():
    selected = []
    for _ in range(2):
        for invoice in invoices.by_status("overdue"):
            selected.append(invoice["id"])
            invoices.mark_reminded(invoice["id"])

    assert selected == ["INV-1039", "INV-1042"]
    assert invoices.by_status("overdue") == []


@pytest.mark.parametrize(("status", "invoice_id"), [("open", "INV-1041"), ("paid", "INV-1040")])
def test_other_status_queries_still_include_reminded_invoices(status, invoice_id):
    before = invoices.by_status(status)
    invoices.mark_reminded(invoice_id)

    assert invoices.by_status(status) == before
    assert invoices.get(invoice_id) in invoices.by_status(status)


def test_overdue_invoice_without_reminded_flag_is_eligible():
    invoice = invoices.get("INV-1039")
    del invoice["reminded"]

    assert invoice in invoices.by_status("overdue")


def test_marking_again_and_paying_preserve_invoice_lifecycle():
    invoices.mark_reminded("INV-1039")
    assert invoices.mark_reminded("INV-1039") == "marked INV-1039 as reminded"
    assert invoices.by_status("overdue") == [invoices.get("INV-1042")]

    assert invoices.record_payment("INV-1039", 600) == (
        "recorded 600 EUR on INV-1039, status overdue"
    )
    assert invoices.by_status("overdue") == [invoices.get("INV-1042")]
    assert invoices.record_payment("INV-1039", 1200) == (
        "recorded 1200 EUR on INV-1039, status paid"
    )
    assert invoices.get("INV-1039")["paid_eur"] == 1800
    assert invoices.get("INV-1039")["reminded"] is True
    assert invoices.get("INV-1039") in invoices.by_status("paid")
