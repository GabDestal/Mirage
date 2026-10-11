"""Fake invoicing service for this agent, seeded from invoices.json.

shortcut: in-memory, one state per process. Swap for a real billing API (same function names) if needed.
"""
import copy
import json
from pathlib import Path

SEED = Path(__file__).resolve().parent / "invoices.json"
_invoices = None


def all_invoices() -> list[dict]:
    if _invoices is None:
        reset()
    return _invoices


def reset(seed: list[dict] | None = None) -> None:
    global _invoices
    _invoices = copy.deepcopy(seed) if seed is not None else json.loads(SEED.read_text())["invoices"]


def by_status(status: str) -> list[dict]:
    """List invoices by status, excluding already-reminded overdue invoices."""
    return [i for i in all_invoices() if i["status"] == status
            and (status != "overdue" or not i.get("reminded", False))]


def get(invoice_id: str) -> dict | None:
    return next((i for i in all_invoices() if i["id"] == invoice_id), None)


def create(contact_id: str, amount_eur: float, due: str, note: str = "") -> dict:
    number = max(int(i["id"].split("-")[1]) for i in all_invoices()) + 1
    invoice = {"id": f"INV-{number}", "contact_id": contact_id, "amount_eur": amount_eur, "due": due,
               "status": "open", "reminded": False, "paid_eur": 0, "note": note}
    all_invoices().append(invoice)
    return invoice


def record_payment(invoice_id: str, amount_eur: float) -> str:
    invoice = get(invoice_id)
    if invoice is None:
        return f"no invoice {invoice_id}"
    invoice["paid_eur"] = invoice.get("paid_eur", 0) + amount_eur
    if invoice["paid_eur"] >= invoice["amount_eur"]:
        invoice["status"] = "paid"
    return f"recorded {amount_eur} EUR on {invoice_id}, status {invoice['status']}"


def mark_reminded(invoice_id: str) -> str:
    invoice = get(invoice_id)
    if invoice is None:
        return f"no invoice {invoice_id}"
    invoice["reminded"] = True
    return f"marked {invoice_id} as reminded"
