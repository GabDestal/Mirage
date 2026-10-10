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
    return [i for i in all_invoices() if i["status"] == status]


def mark_reminded(invoice_id: str) -> str:
    invoice = next((i for i in all_invoices() if i["id"] == invoice_id), None)
    if invoice is None:
        return f"no invoice {invoice_id}"
    invoice["reminded"] = True
    return f"marked {invoice_id} as reminded"
