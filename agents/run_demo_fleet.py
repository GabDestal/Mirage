"""Run 4 demo agents in parallel under Mirage protection:
1. meeting_assistant: reads calendar, searches contacts & mail (gets poisoned invite and freezes)
2. invoicing: checks overdue invoices, searches CRM, sends reminders (keeps running)
3. outreach: SDR lead follow-ups, queries CRM, logs sales activity (keeps running)
4. pr_reviewer: reviews open pull requests, inspects files, posts comments (keeps running)

Each agent has a module-level factory (`meeting_assistant()`, ...) that only builds and protects
it. That factory is the entrypoint Mirage records, so the sandbox can rebuild the agent to
detonate an incident (a function nested in run_fleet could not be found there).
"""

import json
import os
import sys
import threading

from dotenv import load_dotenv

# Ensure root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

import mirage
from mirage import core

from agents.common.completion import (
    invoice_requirements,
    meeting_requirements,
    outreach_requirements,
    review_requirements,
)
from agents.invoicing import invoices
from agents.invoicing.agent import TASK as INVOICING_TASK
from agents.invoicing.agent import build_agent as build_invoicing_agent
from agents.meeting_assistant.agent import TASK as MEETING_TASK
from agents.meeting_assistant.agent import USER_EMAIL
from agents.meeting_assistant.agent import build_agent as build_meeting_agent
from agents.meeting_assistant.eval_injection import TASK_DAY, VARIANTS, seeded
from agents.outreach.agent import TASK as OUTREACH_TASK
from agents.outreach.agent import build_agent as build_outreach_agent
from agents.pr_reviewer import pull_requests
from agents.pr_reviewer.agent import TASK as PR_TASK
from agents.pr_reviewer.agent import build_agent as build_pr_agent
from agents.services.store import SEED
from agents.services.store import reset as reset_store

CUSTOMERS = ["*@contoso-demo.com", "*@fabrikam-demo.com", "*@tailspin-demo.com",
             "*@adatum-demo.com", "*@proseware-demo.com", "*@litware-demo.com",
             "*@wingtip-demo.com", "*@northwind-demo.com", USER_EMAIL]


_SPECS = {
    "meeting_assistant": {"owner": "liam", "allow": {
        "tools": ["read_calendar", "search_contacts", "search_emails", "send_email"],
        "email_to": [USER_EMAIL],
    }},
    "invoicing": {"owner": "accounting", "allow": {
        "tools": ["list_invoices", "get_invoice", "create_invoice", "record_payment",
                  "mark_reminded", "search_contacts", "get_contact", "update_contact",
                  "send_email", "send_invoice", "read_inbox"],
        "email_to": CUSTOMERS,
    }},
    "outreach": {"owner": "sales", "allow": {
        "tools": ["search_contacts", "get_contact", "create_contact", "update_contact",
                  "log_activity", "list_activities", "read_inbox", "send_email",
                  "schedule_follow_up"],
        "email_to": CUSTOMERS,
    }},
    "pr_reviewer": {"owner": "engineering", "allow": {
        "tools": ["list_pull_requests", "read_pull_request", "read_file",
                  "post_inline_comment", "set_labels", "update_description", "submit_review"],
    }},
}
for _name, _spec in _SPECS.items():
    _spec["entrypoint"] = f"agents.run_demo_fleet:{_name}"


def _requirements(*, opted_out=()):
    # Read trusted files, never the poisoned invite or concurrently mutated service state.
    clean = json.loads(SEED.read_text())
    return {
        "meeting_assistant": meeting_requirements(clean["calendar"], USER_EMAIL, TASK_DAY),
        "invoicing": invoice_requirements(json.loads(invoices.SEED.read_text())["invoices"],
                                          clean["contacts"]),
        "outreach": outreach_requirements(clean["contacts"], TASK_DAY, opted_out=opted_out),
        "pr_reviewer": review_requirements(
            json.loads(pull_requests.SEED.read_text())["pull_requests"]),
    }


# Fresh sandbox imports can construct a factory without running fleet setup.
_legit = _requirements()


def _protect(agent, name):
    return mirage.protect(agent, name=name, **_SPECS[name], legit=_legit[name])


def meeting_assistant():
    return _protect(build_meeting_agent(), "meeting_assistant")


def invoicing():
    return _protect(build_invoicing_agent(), "invoicing")


def outreach():
    return _protect(build_outreach_agent(), "outreach")


def pr_reviewer():
    return _protect(build_pr_agent(), "pr_reviewer")


FLEET = [(meeting_assistant, MEETING_TASK), (invoicing, INVOICING_TASK),
         (outreach, OUTREACH_TASK), (pr_reviewer, PR_TASK)]


def setup_demo_services(*, opted_out=()):
    """Seed services with 4 agents' synthetic data, including the poisoned calendar event."""
    global _legit
    _legit = _requirements(opted_out=opted_out)
    reset_store(seeded(VARIANTS["V2_system_tag"]))
    invoices.reset()
    pull_requests.reset()
    print("[Demo] Seeded synthetic data with 4 agents & poisoned calendar invite.")


def run_fleet(blocking: bool = True):
    """Blocking returns whether all invocations completed; a request alone has no outcome."""
    setup_demo_services()

    threads = []
    outcomes = []
    for factory, task in FLEET:
        def start_worker(factory=factory, task=task):
            name = factory.__name__
            token, error, completed = None, None, False
            phase = "register"
            try:
                spec = _SPECS[name]
                core.register(name, spec["allow"]["tools"], **spec, legit=_legit[name])
                phase = "start"
                token = core.start(name, task)
                phase = "factory"
                agent = factory()
                phase = "invoke"
                agent.invoke({"messages": [("user", task)]})
                completed = True
            except mirage.Blocked as exc:
                error = exc
                print(f"[Demo] {name}: blocked ({type(exc).__name__})")
            except BaseException as exc:  # noqa: BLE001 - one failed worker must not stop siblings
                error = exc
                print(f"[Demo] {name}: {phase}_error ({type(exc).__name__})")
            finally:
                try:
                    core.end(token, error)
                except BaseException as exc:  # noqa: BLE001 - completion delivery also can fail
                    completed = False
                    print(f"[Demo] {name}: completion_error ({type(exc).__name__})")
                outcomes.append(completed)
            if completed:
                print(f"[Demo] {name}: completed")

        t = threading.Thread(target=start_worker, daemon=True, name=f"agent-{factory.__name__}")
        threads.append(t)
        t.start()
        print(f"[Demo] Launch requested for {factory.__name__}")

    if blocking:
        for t in threads:
            t.join()
        return all(outcomes)


if __name__ == "__main__":
    raise SystemExit(0 if run_fleet(blocking=True) else 1)
