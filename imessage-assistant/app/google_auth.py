"""Google sign-in for the assistant.

One-time setup: `python -m scripts.google_login` opens a browser, you approve access,
and Google gives back a token that's saved to secrets/google_token.json. After that,
get_credentials() loads that token and quietly renews it whenever it expires (about hourly).
"""

import logging
import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import settings

logger = logging.getLogger(__name__)

# What the assistant may access. Read-only calendar for now. When Gmail/Drive are added,
# their scopes go here and you run scripts.google_login again to approve the new access.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleLoginNeeded(Exception):
    """Raised when there's no usable token. The message tells you what to run."""


LOGIN_HINT = "Google access isn't set up or has expired. On the Mac, run: python -m scripts.google_login"


def save_credentials(creds: Credentials) -> None:
    os.makedirs(os.path.dirname(settings.google_token_file) or ".", exist_ok=True)
    with open(settings.google_token_file, "w") as f:
        f.write(creds.to_json())
    os.chmod(settings.google_token_file, 0o600)  # readable by your user only - it's a password-equivalent


def get_credentials() -> Credentials:
    if not os.path.exists(settings.google_token_file):
        raise GoogleLoginNeeded(LOGIN_HINT)

    creds = Credentials.from_authorized_user_file(settings.google_token_file, SCOPES)
    if creds.valid:
        return creds

    if not creds.refresh_token:
        raise GoogleLoginNeeded(LOGIN_HINT)
    try:
        creds.refresh(Request())  # trade the long-lived refresh token for a fresh 1-hour access token
    except RefreshError as e:
        # Typical causes: app in "Testing" mode (refresh tokens die after 7 days),
        # you revoked access, or new scopes were added since you last logged in.
        logger.warning("Google token refresh failed: %s", e)
        raise GoogleLoginNeeded(LOGIN_HINT) from e
    save_credentials(creds)
    return creds
