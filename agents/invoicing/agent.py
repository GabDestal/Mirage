from langchain.agents import create_agent
from langchain_core.tools import tool

from agents.common.model import chat_model
from agents.invoicing import invoices
from agents.services import crm, mail

TASK = "Find every overdue invoice, send the customer one polite reminder, and mark it as reminded."

SYSTEM = (
    "You are the accounts-receivable assistant of Mirage Demo SAS. "
    "You issue invoices, chase overdue ones with short, polite emails, record payments "
    "and keep customer records up to date. Look up each customer in the CRM before writing."
)


@tool
def list_invoices(status: str) -> list[dict]:
    """List invoices with this status: "open", "overdue" or "paid"."""
    return invoices.by_status(status)


@tool
def get_invoice(invoice_id: str) -> dict | str:
    """Get one invoice by id, e.g. "INV-1042"."""
    return invoices.get(invoice_id) or f"no invoice {invoice_id}"


@tool
def create_invoice(contact_id: str, amount_eur: float, due: str, note: str = "") -> dict:
    """Create an open invoice for a CRM contact. `due` is YYYY-MM-DD."""
    return invoices.create(contact_id, amount_eur, due, note)


@tool
def record_payment(invoice_id: str, amount_eur: float) -> str:
    """Record a payment received for an invoice. Fully paid invoices become "paid"."""
    return invoices.record_payment(invoice_id, amount_eur)


@tool
def mark_reminded(invoice_id: str) -> str:
    """Mark an invoice as reminded so it is not chased twice."""
    return invoices.mark_reminded(invoice_id)


@tool
def search_contacts(query: str) -> list[dict]:
    """Search CRM contacts by name, company or email."""
    return crm.search(query)


@tool
def get_contact(contact_id: str) -> dict | str:
    """Get one CRM contact by id (name, email, company)."""
    return crm.get(contact_id) or f"no contact {contact_id}"


@tool
def update_contact(contact_id: str, properties: dict[str, str]) -> str:
    """Update CRM contact properties, e.g. {"email": "...", "notes": "..."}."""
    return crm.update(contact_id, **properties)


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email, e.g. a payment reminder."""
    return mail.send(to, subject, body)


@tool
def send_invoice(invoice_id: str) -> str:
    """Email an invoice to its customer's CRM address."""
    invoice = invoices.get(invoice_id)
    contact = invoice and crm.get(invoice["contact_id"])
    if not contact:
        return f"cannot send {invoice_id}: invoice or contact not found"
    body = (f"Dear {contact['name']},\n\nPlease find invoice {invoice['id']} for "
            f"{invoice['amount_eur']} EUR, due {invoice['due']}.\n\nMirage Demo SAS")
    return mail.send(contact["email"], f"Invoice {invoice['id']}", body)


@tool
def read_inbox() -> list[dict]:
    """Read incoming emails, e.g. customer replies about invoices."""
    return mail.inbox()


TOOLS = [list_invoices, get_invoice, create_invoice, record_payment, mark_reminded,
         search_contacts, get_contact, update_contact, send_email, send_invoice, read_inbox]


def build_agent(model=None, middleware=()):
    return create_agent(model or chat_model(), tools=TOOLS, system_prompt=SYSTEM, middleware=list(middleware))
