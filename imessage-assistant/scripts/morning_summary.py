"""Text yourself a summary of today's calendar. launchd runs this once a day at MORNING_SUMMARY_TIME.

Run it by hand to test:  python -m scripts.morning_summary
"""

import logging
import sys

from app.config import settings
from app.logging_setup import setup_logging

# Its own log file: two processes rotating the same log file can step on each other.
setup_logging("logs/morning.log", to_console=settings.log_to_console)

from app import memory  # noqa: E402
from app.bluebubbles import chat_guid_for, send_text  # noqa: E402
from app.claude_client import get_reply  # noqa: E402

logger = logging.getLogger("morning_summary")

PROMPT = """\
This is your scheduled morning summary, not a message from me. Check my calendar for today and \
text me a short rundown: events in time order with start times, plus anything worth a heads-up \
(early start, back-to-back meetings, a location I need to travel to). If today is empty, say so in one line."""


def main() -> int:
    if not settings.google_calendar_enabled:
        logger.error("Morning summary needs GOOGLE_CALENDAR_ENABLED=true - skipping")
        return 1

    chat_guid = chat_guid_for(settings.owner_address)
    try:
        reply = get_reply(PROMPT)
        send_text(chat_guid, reply)
        logger.info("Morning summary sent to %s", chat_guid)
    except Exception:
        logger.exception("Morning summary failed")
        return 1

    # Saved to memory so you can reply with follow-ups like "where's the 2pm?"
    if settings.memory_enabled:
        try:
            memory.init_db()
            memory.save_exchange(chat_guid, "[Scheduled morning summary]", reply, None)
        except Exception:
            logger.exception("Summary sent, but saving it to memory failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
