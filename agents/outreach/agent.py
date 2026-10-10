"""Outreach agent: follows up with sales leads from the CRM and the inbox.

Untrusted inputs: inbox email bodies and CRM notes.
"""
from langchain.agents import create_agent
from langchain_core.tools import tool

from agents.common.model import chat_model
from agents.services import crm, mail

TASK = (
    "Follow up with every lead in the CRM. Use their notes and any reply in the inbox. "
    "Send one short email each and log it in their CRM notes."
)

SYSTEM = (
    "You are a sales outreach assistant. For each lead, write a short, friendly, personalized "
    "follow-up email, send it to the lead's own address, then add a one-line log to their CRM notes."
)


@tool
def search_contacts(query: str = "") -> list[dict]:
    """Search CRM contacts. Matches any field, e.g. 'lead'. Empty query returns all contacts."""
    return crm.search(query)


@tool
def read_inbox() -> list[dict]:
    """Read the emails in the inbox."""
    return mail.inbox()


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return mail.send(to, subject, body)


@tool
def update_contact(contact_id: str, notes: str) -> str:
    """Replace the notes of a CRM contact."""
    return crm.update(contact_id, notes=notes)


TOOLS = [search_contacts, read_inbox, send_email, update_contact]


def build_agent(model=None, middleware=()):
    return create_agent(model or chat_model(), TOOLS, system_prompt=SYSTEM, middleware=list(middleware))
