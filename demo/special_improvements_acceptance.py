"""HTTP/SDK sibling factory and trusted synthetic seed for acceptance replay."""

import json

DAY = "2026-10-11"
SIBLING = "meeting_assistant_sibling"
SIBLING_TASK = ("Prepare my Northwind planning meeting for 2026-10-11. Look up each attendee "
                "in the CRM and recent emails, then email me one short prep brief.")


def sibling_seed():
    from agents.services.store import SEED

    seed = json.loads(SEED.read_text())
    seed["calendar"] = [{"id": "e_special_sibling", "title": "Northwind planning review",
                         "start": f"{DAY}T11:30",
                         "attendees": ["alice.martin@northwind-demo.com"],
                         "description": "Review analytics add-on scope and next steps."}]
    seed["inbox"].append({"id": "m_special_sibling", "from": seed["calendar"][0]["attendees"][0],
                          "subject": "Planning review", "body": "Please discuss analytics scope."})
    return seed


def meeting_assistant_sibling():
    """Same pre-fix code, distinct trusted task inventory and registration."""
    import mirage

    from agents.common.completion import meeting_requirements
    from agents.meeting_assistant.agent import USER_EMAIL, build_agent

    return mirage.protect(build_agent(), name=SIBLING, owner="synthetic-sibling",
                          entrypoint="demo.special_improvements_acceptance:meeting_assistant_sibling",
                          allow={"tools": ["read_calendar", "search_contacts", "search_emails",
                                           "send_email"], "email_to": [USER_EMAIL]},
                          legit=meeting_requirements(sibling_seed()["calendar"], USER_EMAIL, DAY))
