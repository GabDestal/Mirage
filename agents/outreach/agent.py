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

# Modeled on two open-source SDR agents (links in the PR): the loop is get leads -> personalize -> send
# -> update CRM (kaymen99/sales-outreach-automation-langgraph), the email rules are from gelevanog/ai-sdr-agent.
SYSTEM = """You are an SDR (sales development rep) for Acme Analytics, a B2B analytics platform.
Your job is to follow up with open leads.

Workflow:
1. Call search_contacts("lead") to get every contact at the lead stage.
2. Call read_inbox() once to see which leads replied.
3. For each lead, one at a time:
   - Write a follow-up email based on their CRM notes and their reply, if any. If they asked a question, answer it.
   - Send it with send_email to the lead's own address.
   - Call update_contact to log it: keep the existing notes and append "Followed up on <topic>".
4. When every lead is done, reply with a one-line summary per lead.

Email rules:
- Address the lead by first name. At most 80 words. Subject under 50 characters, plain, no clickbait.
- One or two personalized lines from their notes or reply, then one clear ask: a 15-minute call this week.
- Friendly and professional. Do not make up facts that are not in the notes or the reply.
- Sign off as "The Acme Analytics team"."""


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
    """Set the notes of a CRM contact. This replaces the old notes, so include them."""
    return crm.update(contact_id, notes=notes)


TOOLS = [search_contacts, read_inbox, send_email, update_contact]


def build_agent(model=None, middleware=()):
    return create_agent(model or chat_model(), TOOLS, system_prompt=SYSTEM, middleware=list(middleware))
