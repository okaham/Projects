"""Tools Claude can call, and the code that runs them.

Each tool has two halves:
  1. A definition (name, description, input schema) sent to Claude so it knows the tool exists.
  2. Code in run_tool() that actually does the work when Claude asks for it.

Rule for later phases: a tool with side effects (send an email, edit a file, change the
calendar) must NOT act here directly. It will save a pending action and text you to
confirm first. Everything below is read-only, so it runs immediately.
"""

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

CALENDAR_TOOL = {
    "name": "list_calendar_events",
    "description": (
        "List events on the user's primary Google Calendar. Read-only. Use it for questions about "
        "their schedule, meetings, or free time. Times come back as ISO 8601 with a UTC offset; "
        "all-day events have only a date."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "First day to include, YYYY-MM-DD, in the user's local time zone.",
            },
            "days": {
                "type": "integer",
                "description": "How many days to include, starting at start_date. 1 = just that day. Max 31.",
            },
        },
        "required": ["start_date", "days"],
        "additionalProperties": False,
    },
    "strict": True,  # Claude's tool input is guaranteed to match the schema above
}


def enabled_tools() -> list[dict]:
    """Definitions of the tools turned on in .env. An empty list means plain chat, no tools."""
    tools = []
    if settings.google_calendar_enabled:
        tools.append(CALENDAR_TOOL)
    return tools


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool. Returns (result_text, is_error). Never raises: errors go back to Claude as text,
    so it can explain the problem in its reply (e.g. "Google access expired, run ...")."""
    # Imported here so the Google libraries only load if a Google tool is actually used.
    from app.google_auth import GoogleLoginNeeded

    logger.info("Tool call: %s %s", name, tool_input)
    try:
        if name == "list_calendar_events" and settings.google_calendar_enabled:
            from app import google_calendar

            events = google_calendar.list_events(tool_input["start_date"], tool_input["days"])
            return json.dumps(events), False
        return f"Unknown or disabled tool: {name}", True
    except (GoogleLoginNeeded, ValueError) as e:
        return str(e), True
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return f"The tool failed: {type(e).__name__}: {e}", True
