"""FastAPI server that BlueBubbles calls whenever an iMessage arrives.

Flow:  BlueBubbles --POST /webhook--> filters --> load history (SQLite) --> Claude
       --> BlueBubbles sends reply --> save your text + reply (SQLite)

Run locally:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import hmac
import logging
import threading
from collections import deque

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.config import normalize_address, settings
from app.logging_setup import setup_logging

setup_logging(settings.log_file, to_console=settings.log_to_console)

from app import memory  # noqa: E402
from app.bluebubbles import IncomingMessage, parse_new_message, send_text  # noqa: E402
from app.claude_client import get_reply  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI()

if settings.memory_enabled:
    memory.init_db()
    logger.info("Memory ON: last %d messages per chat from %s", settings.history_limit, settings.db_path)
else:
    logger.info("Memory OFF: each text is answered on its own")

# Handle one message at a time. If you send two texts quickly, the second waits until the
# first is answered and saved, so it sees the first in its history and replies arrive in order.
_reply_lock = threading.Lock()

# Remember the last 500 message ids so a webhook delivered twice is only answered once.
_seen_guids: deque[str] = deque(maxlen=500)
_seen_lock = threading.Lock()


def _already_seen(guid: str) -> bool:
    with _seen_lock:
        if guid in _seen_guids:
            return True
        _seen_guids.append(guid)
        return False


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/webhook")
def webhook(payload: dict, background_tasks: BackgroundTasks, secret: str = "") -> dict:
    # `secret` comes from the URL: /webhook?secret=...  compare_digest avoids timing leaks.
    if not hmac.compare_digest(secret, settings.webhook_secret):
        logger.warning("Rejected webhook with wrong secret")
        raise HTTPException(status_code=403, detail="forbidden")

    msg = parse_new_message(payload)
    if msg is None:
        return {"ok": True, "ignored": "not a new-message event"}

    reason = _ignore_reason(msg)
    if reason:
        logger.info("Ignoring message %s: %s", msg.guid, reason)
        return {"ok": True, "ignored": reason}

    logger.info("Accepted message %s from %s", msg.guid, msg.sender)
    # Answer BlueBubbles immediately; the slow Claude call happens after the response is sent.
    background_tasks.add_task(handle_message, msg)
    return {"ok": True}


def _ignore_reason(msg: IncomingMessage) -> str | None:
    """Return why we should NOT reply to this message, or None if we should."""
    # Order matters: is_from_me first, so the bot never reacts to its own replies (no loops).
    if msg.is_from_me:
        return "sent by this Mac (bot's own message)"
    if normalize_address(msg.sender) not in settings.allowed_senders:
        return f"sender {msg.sender!r} not in ALLOWED_SENDERS"
    if msg.is_group_chat:
        return "group chat (replies would go to other people)"
    if msg.is_reaction:
        return "tapback/reaction"
    if not msg.chat_guid or not msg.guid:
        return "missing chat or message id"
    if _already_seen(msg.guid):
        return "duplicate delivery"
    return None


def handle_message(msg: IncomingMessage) -> None:
    """Runs in the background. Any error is logged and reported back by text - never swallowed."""
    with _reply_lock:
        try:
            _reply(msg)
        except Exception:
            logger.exception("Failed to handle message %s", msg.guid)
            try:
                send_text(msg.chat_guid, "Sorry, something broke on my end. Details are in the log file.")
            except Exception:
                logger.exception("Also failed to send the error notice for %s", msg.guid)


def _reply(msg: IncomingMessage) -> None:
    if not msg.text:
        send_text(msg.chat_guid, "I can only read text so far - attachments aren't supported yet.")
        return

    history = memory.get_recent(msg.chat_guid, settings.history_limit) if settings.memory_enabled else []
    reply = get_reply(msg.text, history)
    send_text(msg.chat_guid, reply)

    # Saved only after BlueBubbles accepted the reply for sending, so failed attempts never enter history.
    # A failure here is logged but doesn't text you "something broke" - you already got your answer.
    if settings.memory_enabled:
        try:
            memory.save_exchange(msg.chat_guid, msg.text, reply, msg.guid)
        except Exception:
            logger.exception("Reply sent, but saving message %s to memory failed", msg.guid)
