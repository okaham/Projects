"""FastAPI server that BlueBubbles calls whenever an iMessage arrives.

Flow:  BlueBubbles --POST /webhook--> filters --> Claude --> BlueBubbles sends reply

Run locally:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import hmac
import logging
import threading
from collections import deque

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.config import normalize_address, settings
from app.logging_setup import setup_logging

setup_logging(settings.log_file)

from app.bluebubbles import IncomingMessage, parse_new_message, send_text  # noqa: E402
from app.claude_client import get_reply  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI()

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
    try:
        if not msg.text:
            reply = "I can only read text so far - attachments aren't supported yet."
        else:
            reply = get_reply(msg.text)
        send_text(msg.chat_guid, reply)
    except Exception:
        logger.exception("Failed to handle message %s", msg.guid)
        try:
            send_text(msg.chat_guid, "Sorry, something broke on my end. Details are in the log file.")
        except Exception:
            logger.exception("Also failed to send the error notice for %s", msg.guid)
