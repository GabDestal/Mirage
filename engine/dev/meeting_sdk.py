"""Liam's meeting assistant protected by the SDK: the demo's real agent, for engine dev runs.

`factory()` is also what the sandbox calls to rebuild the agent (protect records it).
shortcut: lives in engine/dev until demo/ has its own story runner (Liam).
"""

import mirage

from agents.meeting_assistant.agent import USER_EMAIL, build_agent

ALLOW = {"tools": ["read_calendar", "search_contacts", "search_emails", "send_email"],
         "email_to": [USER_EMAIL]}


def factory():
    return mirage.protect(build_agent(), name="meeting_assistant", owner="liam", allow=ALLOW)
