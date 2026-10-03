"""Everything that talks to BlueBubbles: reading its webhooks and sending texts.

BlueBubbles webhook body for a new text looks roughly like this (trimmed):

    {
      "type": "new-message",
      "data": {
        "guid": "7F3A...",                       # unique id of this message
        "text": "what's on my calendar?",
        "isFromMe": false,                       # true for messages sent BY this Mac (incl. the bot's replies)
        "associatedMessageGuid": null,           # set for tapbacks/reactions
        "handle": {"address": "+15551234567"},   # who sent it
        "chats": [{"guid": "iMessage;-;+15551234567"}]
      }
    }

Chat guids: ";-;" in the middle means a 1:1 chat, ";+;" means a group chat.
"""

import logging
import uuid
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    guid: str
    text: str
    sender: str  # raw address from BlueBubbles, e.g. "+15551234567"
    chat_guid: str
    is_from_me: bool
    is_reaction: bool

    @property
    def is_group_chat(self) -> bool:
        return ";+;" in self.chat_guid


def parse_new_message(payload: dict) -> IncomingMessage | None:
    """Pull out the fields we care about. Returns None if this isn't a new-message event."""
    if payload.get("type") != "new-message":
        return None

    data = payload.get("data") or {}
    handle = data.get("handle") or {}
    chats = data.get("chats") or []

    return IncomingMessage(
        guid=data.get("guid", ""),
        text=(data.get("text") or "").strip(),
        sender=handle.get("address", ""),
        chat_guid=chats[0].get("guid", "") if chats else "",
        is_from_me=bool(data.get("isFromMe")),
        is_reaction=bool(data.get("associatedMessageGuid")),
    )


def chat_guid_for(address: str) -> str:
    """The 1:1 chat guid for a normalized address (see config.normalize_address).

    "15551234567" -> "iMessage;-;+15551234567",  "me@icloud.com" -> "iMessage;-;me@icloud.com"
    """
    return f"iMessage;-;{address if '@' in address else '+' + address}"


def send_text(chat_guid: str, text: str) -> None:
    """Send an iMessage into an existing chat. Raises an exception if BlueBubbles reports an error."""
    response = httpx.post(
        f"{settings.bluebubbles_url}/api/v1/message/text",
        params={"password": settings.bluebubbles_password},
        json={
            "chatGuid": chat_guid,
            "message": text,
            "method": settings.bluebubbles_send_method,
            # Random id BlueBubbles uses to match the "sent" confirmation to this request.
            "tempGuid": f"temp-{uuid.uuid4()}",
        },
        timeout=30.0,
    )
    # Not using response.raise_for_status(): its error message includes the full URL,
    # which contains the password, and that would end up in the log file.
    if response.status_code >= 400:
        raise RuntimeError(f"BlueBubbles send failed: HTTP {response.status_code}: {response.text[:300]}")
    logger.info("Sent reply to %s (%d chars)", chat_guid, len(text))


def ping() -> bool:
    """True if BlueBubbles is reachable and the password is correct."""
    response = httpx.get(
        f"{settings.bluebubbles_url}/api/v1/ping",
        params={"password": settings.bluebubbles_password},
        timeout=10.0,
    )
    return response.status_code == 200
