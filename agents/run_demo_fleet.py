"""Run 4 demo agents in parallel under Mirage protection:
1. meeting_assistant: reads calendar, searches contacts & mail (gets poisoned invite and freezes)
2. invoicing: checks overdue invoices, searches CRM, sends reminders (keeps running)
3. outreach: SDR lead follow-ups, queries CRM, logs sales activity (keeps running)
4. pr_reviewer: reviews open pull requests, inspects files, posts comments (keeps running)

Each agent has a module-level factory (`meeting_assistant()`, ...) that only builds and protects
it. That factory is the entrypoint Mirage records, so the sandbox can rebuild the agent to
detonate an incident (a function nested in run_fleet could not be found there).
"""

import os
import sys
import threading

from dotenv import load_dotenv

# Ensure root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

import mirage

from agents.invoicing.agent import TASK as INVOICING_TASK
from agents.invoicing.agent import build_agent as build_invoicing_agent
from agents.meeting_assistant.agent import TASK as MEETING_TASK
from agents.meeting_assistant.agent import USER_EMAIL
from agents.meeting_assistant.agent import build_agent as build_meeting_agent
from agents.meeting_assistant.eval_injection import VARIANTS, seeded
from agents.outreach.agent import TASK as OUTREACH_TASK
from agents.outreach.agent import build_agent as build_outreach_agent
from agents.pr_reviewer.agent import TASK as PR_TASK
from agents.pr_reviewer.agent import build_agent as build_pr_agent
from agents.services.store import reset as reset_store

CUSTOMERS = ["*@contoso-demo.com", "*@fabrikam-demo.com", "*@tailspin-demo.com",
             "*@adatum-demo.com", "*@proseware-demo.com", "*@litware-demo.com",
             "*@wingtip-demo.com", "*@northwind-demo.com", USER_EMAIL]


def _protect(agent, name, owner, allow):
    # entrypoint: this module's factory of the same name, rebuilt by the sandbox on detonation
    return mirage.protect(agent, name=name, owner=owner, allow=allow,
                          entrypoint=f"agents.run_demo_fleet:{name}")


def meeting_assistant():
    return _protect(build_meeting_agent(), "meeting_assistant", "liam", {
        "tools": ["read_calendar", "search_contacts", "search_emails", "send_email"],
        "email_to": [USER_EMAIL],
    })


def invoicing():
    return _protect(build_invoicing_agent(), "invoicing", "accounting", {
        "tools": ["list_invoices", "get_invoice", "create_invoice", "record_payment",
                  "mark_reminded", "search_contacts", "get_contact", "update_contact",
                  "send_email", "send_invoice", "read_inbox"],
        "email_to": CUSTOMERS,
    })


def outreach():
    return _protect(build_outreach_agent(), "outreach", "sales", {
        "tools": ["search_contacts", "get_contact", "create_contact", "update_contact",
                  "log_activity", "list_activities", "read_inbox", "send_email",
                  "schedule_follow_up"],
        "email_to": CUSTOMERS,
    })


def pr_reviewer():
    return _protect(build_pr_agent(), "pr_reviewer", "engineering", {
        "tools": ["list_pull_requests", "read_pull_request", "read_file",
                  "post_inline_comment", "set_labels", "update_description", "submit_review"],
    })


FLEET = [(meeting_assistant, MEETING_TASK), (invoicing, INVOICING_TASK),
         (outreach, OUTREACH_TASK), (pr_reviewer, PR_TASK)]


def setup_demo_services():
    """Seed services with 4 agents' synthetic data, including the poisoned calendar event."""
    reset_store(seeded(VARIANTS["V2_system_tag"]))
    print("[Demo] Seeded synthetic data with 4 agents & poisoned calendar invite.")


def run_fleet(blocking: bool = True):
    setup_demo_services()

    threads = []
    for factory, task in FLEET:
        def start_worker(factory=factory, task=task):
            agent = factory()
            try:
                agent.invoke({"messages": [("user", task)]})
            except Exception:  # noqa: BLE001, S110 - expected when a run is frozen then killed
                pass

        t = threading.Thread(target=start_worker, daemon=True, name=f"agent-{factory.__name__}")
        threads.append(t)
        t.start()
        print(f"[Demo] Launched {factory.__name__}")

    if blocking:
        for t in threads:
            t.join()


if __name__ == "__main__":
    run_fleet(blocking=True)
