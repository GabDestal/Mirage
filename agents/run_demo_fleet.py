"""Run 4 demo agents in parallel under Mirage protection:
1. meeting_assistant: reads calendar, searches contacts & mail (gets poisoned invite and freezes)
2. invoicing: checks overdue invoices, searches CRM, sends reminders (keeps running)
3. outreach: SDR lead follow-ups, queries CRM, logs sales activity (keeps running)
4. pr_reviewer: reviews open pull requests, inspects files, posts comments (keeps running)
"""

import os
import sys
import threading
import time
from datetime import UTC, datetime

from dotenv import load_dotenv

# Ensure root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from engine.gateway import gate
from engine.store import events
from agents.services.store import reset as reset_store, state as get_store_state
from agents.meeting_assistant.eval_injection import VARIANTS, seeded
import mirage

from agents.meeting_assistant.agent import build_agent as build_meeting_agent, TASK as MEETING_TASK, USER_EMAIL
from agents.invoicing.agent import build_agent as build_invoicing_agent, TASK as INVOICING_TASK
from agents.outreach.agent import build_agent as build_outreach_agent, TASK as OUTREACH_TASK
from agents.pr_reviewer.agent import build_agent as build_pr_agent, TASK as PR_TASK


def setup_demo_services():
    """Seed services with 4 agents' synthetic data, including the poisoned calendar event."""
    # Seed base data + poisoned calendar invite for meeting assistant
    reset_store(seeded(VARIANTS["V2_system_tag"]))
    print("[Demo] Seeded synthetic data with 4 agents & poisoned calendar invite.")


def run_fleet(blocking: bool = True):
    setup_demo_services()

    # Agent specs & allows
    agents_spec = [
        {
            "name": "meeting_assistant",
            "task": MEETING_TASK,
            "allow": {
                "tools": ["read_calendar", "search_contacts", "search_emails", "send_email"],
                "email_to": [USER_EMAIL],
            },
            "builder": build_meeting_agent,
            "owner": "liam",
        },
        {
            "name": "invoicing",
            "task": INVOICING_TASK,
            "allow": {
                "tools": [
                    "list_invoices", "get_invoice", "create_invoice", "record_payment",
                    "mark_reminded", "search_contacts", "get_contact", "update_contact",
                    "send_email", "send_invoice", "read_inbox"
                ],
                "email_to": ["*@contoso-demo.com", "*@fabrikam-demo.com", "*@tailspin-demo.com", "*@adatum-demo.com", "*@proseware-demo.com", "*@litware-demo.com", "*@wingtip-demo.com", "*@northwind-demo.com", USER_EMAIL],
            },
            "builder": build_invoicing_agent,
            "owner": "accounting",
        },
        {
            "name": "outreach",
            "task": OUTREACH_TASK,
            "allow": {
                "tools": [
                    "search_contacts", "get_contact", "create_contact", "update_contact",
                    "log_activity", "list_activities", "read_inbox", "send_email", "schedule_follow_up"
                ],
                "email_to": ["*@contoso-demo.com", "*@fabrikam-demo.com", "*@tailspin-demo.com", "*@adatum-demo.com", "*@proseware-demo.com", "*@litware-demo.com", "*@wingtip-demo.com", "*@northwind-demo.com", USER_EMAIL],
            },
            "builder": build_outreach_agent,
            "owner": "sales",
        },
        {
            "name": "pr_reviewer",
            "task": PR_TASK,
            "allow": {
                "tools": [
                    "list_pull_requests", "read_pull_request", "read_file",
                    "post_inline_comment", "set_labels", "update_description", "submit_review"
                ],
            },
            "builder": build_pr_agent,
            "owner": "engineering",
        },
    ]

    threads = []
    for spec in agents_spec:
        def start_worker(s=spec):
            agent = mirage.protect(
                s["builder"](),
                name=s["name"],
                owner=s["owner"],
                allow=s["allow"]
            )
            try:
                agent.invoke({"messages": [("user", s["task"])]})
            except Exception as e:
                # Expected when meeting_assistant freezes or is killed
                pass

        t = threading.Thread(target=start_worker, daemon=True, name=f"agent-{spec['name']}")
        threads.append(t)
        t.start()
        print(f"[Demo] Launched {spec['name']}")

    if blocking:
        for t in threads:
            t.join()


if __name__ == "__main__":
    run_fleet(blocking=True)
