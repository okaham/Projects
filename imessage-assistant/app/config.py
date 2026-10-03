"""Loads settings from .env once at startup.

Every other module imports `settings` from here instead of reading
environment variables directly, so all config lives in one place.
"""

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

# Reads key=value pairs from .env into os.environ (does nothing if .env is missing).
load_dotenv()


def normalize_address(address: str) -> str:
    """Turn a phone number or email into one canonical form so they can be compared.

    "+1 (555) 123-4567", "555-123-4567" and "+15551234567" all become "15551234567".
    Emails (Apple IDs) are just lowercased.
    Assumes US numbers: a bare 10-digit number gets a leading "1".
    """
    address = address.strip()
    if "@" in address:
        return address.lower()
    digits = re.sub(r"\D", "", address)  # \D = any non-digit character
    if len(digits) == 10:
        digits = "1" + digits
    return digits


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting {name} in .env (see .env.example)")
    return value


def _bool(name: str, default: bool) -> bool:
    """Read a true/false setting. Accepts true/false, yes/no, 1/0."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    claude_model: str
    claude_effort: str
    bluebubbles_url: str
    bluebubbles_password: str
    bluebubbles_send_method: str
    allowed_senders: frozenset[str]
    webhook_secret: str
    log_file: str
    log_to_console: bool
    memory_enabled: bool
    history_limit: int
    db_path: str


def load_settings() -> Settings:
    allowed = {
        normalize_address(a)
        for a in _required("ALLOWED_SENDERS").split(",")
        if a.strip()
    }
    return Settings(
        anthropic_api_key=_required("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=os.getenv("CLAUDE_EFFORT", "low"),
        bluebubbles_url=_required("BLUEBUBBLES_URL").rstrip("/"),
        bluebubbles_password=_required("BLUEBUBBLES_PASSWORD"),
        bluebubbles_send_method=os.getenv("BLUEBUBBLES_SEND_METHOD", "apple-script"),
        allowed_senders=frozenset(allowed),
        webhook_secret=_required("WEBHOOK_SECRET"),
        log_file=os.getenv("LOG_FILE", "logs/assistant.log"),
        log_to_console=_bool("LOG_TO_CONSOLE", True),
        memory_enabled=_bool("MEMORY_ENABLED", False),
        history_limit=int(os.getenv("HISTORY_LIMIT", "20")),
        db_path=os.getenv("DB_PATH", "data/assistant.db"),
    )


settings = load_settings()
