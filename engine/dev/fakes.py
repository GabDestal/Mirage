"""Fake services over SQLite: calendar, CRM, outbox, web pages.

Same methods as the real adapters. Mirage detonations use them on a snapshot copy.
shortcut: production uses them too until the Google/HubSpot keys arrive; then swap in
real adapters with the same methods.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar (id TEXT PRIMARY KEY, calendar TEXT, start TEXT,
    title TEXT, organizer TEXT, attendees TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, name TEXT, email TEXT,
    company TEXT, phone TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, ts TEXT, sender TEXT,
    recipient TEXT, subject TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, body TEXT);
"""
CONTACT_FIELDS = ["id", "name", "email", "company", "phone", "notes"]


class FakeServices:
    def __init__(self, path):
        self.path = path
        with closing(self._connect()) as db:
            db.executescript(SCHEMA)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _rows(self, sql, params=()):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(sql, params)]

    def _write(self, sql, params=()):
        with closing(self._connect()) as db, db:
            return db.execute(sql, params).lastrowid

    # --- tools -------------------------------------------------------------------------

    def read_calendar(self, calendar, date=None):
        events = self._rows(
            "SELECT id, start, title, organizer, attendees, description FROM calendar"
            " WHERE calendar = ? AND start LIKE ? ORDER BY start",
            (calendar, f"{date or ''}%"),
        )
        for event in events:
            event["attendees"] = event["attendees"].split(",") if event["attendees"] else []
        return {"events": events}

    def crm_query(self, query):
        like = f"%{query}%"
        contacts = self._rows(
            "SELECT id, name, email, company, phone FROM contacts"
            " WHERE name LIKE ? OR email LIKE ? OR company LIKE ? LIMIT 10",
            (like, like, like),
        )
        return {"contacts": contacts}

    def crm_export(self):
        rows = self._rows(f"SELECT {', '.join(CONTACT_FIELDS)} FROM contacts ORDER BY id")
        lines = [",".join(CONTACT_FIELDS)] + [",".join(row[f] or "" for f in CONTACT_FIELDS)
                                              for row in rows]
        return {"count": len(rows), "csv": "\n".join(lines)}

    def send_email(self, sender, to, subject, body):
        message_id = self._write(
            "INSERT INTO outbox (ts, sender, recipient, subject, body) VALUES (?,?,?,?,?)",
            (datetime.now(UTC).isoformat(), sender, to, subject, body),
        )
        return {"status": "sent", "message_id": message_id}

    def fetch_url(self, url):
        page = self._rows("SELECT body FROM pages WHERE url = ?", (url,))
        return {"url": url, "body": page[0]["body"]} if page else {"error": f"404: {url}"}

    # --- inspection (UI panels, effects) -----------------------------------------------

    def outbox(self):
        return self._rows("SELECT * FROM outbox ORDER BY id")
