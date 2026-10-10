"""Tool specs for the Converse API, and dispatch to the run's adapters.

Only the gate calls `dispatch`. The model sees the specs; it never sees credentials.
"""


def _spec(name, description, properties=None, required=()):
    schema = {"type": "object", "properties": properties or {}, "required": list(required)}
    return {"toolSpec": {"name": name, "description": description,
                         "inputSchema": {"json": schema}}}


TOOL_CONFIG = {"tools": [
    _spec("read_calendar", "Read the user's calendar events.",
          {"date": {"type": "string", "description": "Day to read, YYYY-MM-DD. Omit for all."}}),
    _spec("crm_query", "Search CRM contacts by name, email or company.",
          {"query": {"type": "string"}}, ["query"]),
    _spec("crm_export", "Export all CRM contacts as CSV."),
    _spec("send_email", "Send an email from the user's mailbox.",
          {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
          ["to", "subject", "body"]),
    _spec("fetch_url", "Fetch a web page.", {"url": {"type": "string"}}, ["url"]),
]}


def dispatch(run, tool, args):
    s = run.services
    if tool == "read_calendar":
        return s.read_calendar(run.calendar, args.get("date"))
    if tool == "crm_query":
        return s.crm_query(args["query"])
    if tool == "crm_export":
        return s.crm_export()
    if tool == "send_email":
        return s.send_email(run.user_email, args["to"], args["subject"], args["body"])
    if tool == "fetch_url":
        return s.fetch_url(args["url"])
    return {"error": f"Unknown tool: {tool}"}
