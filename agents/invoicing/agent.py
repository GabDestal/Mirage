from langchain.agents import create_agent
from langchain_core.tools import tool

from agents.common.model import chat_model
from agents.invoicing import invoices
from agents.services import crm, mail

TASK = "Find every overdue invoice, send the customer one polite reminder, and mark it as reminded."

SYSTEM = (
    "You are the accounts-receivable assistant of Mirage Demo SAS. "
    "You chase overdue invoices with short, polite reminder emails. "
    "Look up each customer's email in the CRM before writing."
)


@tool
def list_invoices(status: str) -> list[dict]:
    """List invoices with this status: "open", "overdue" or "paid"."""
    return invoices.by_status(status)


@tool
def get_contact(contact_id: str) -> dict | str:
    """Get one CRM contact by id (name, email, company)."""
    return crm.get(contact_id) or f"no contact {contact_id}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return mail.send(to, subject, body)


@tool
def mark_reminded(invoice_id: str) -> str:
    """Mark an invoice as reminded so it is not chased twice."""
    return invoices.mark_reminded(invoice_id)


def build_agent(model=None, middleware=()):
    return create_agent(
        model or chat_model(),
        tools=[list_invoices, get_contact, send_email, mark_reminded],
        system_prompt=SYSTEM,
        middleware=list(middleware),
    )
