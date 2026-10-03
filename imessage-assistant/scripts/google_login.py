"""One-time Google sign-in. Run on the Mac, sitting in front of it (it opens a browser):

    python -m scripts.google_login

Needs secrets/google_client_secret.json from the Google Cloud console (docs/google-cloud-setup.md).
Run it again whenever the assistant texts you that Google access expired, or after new scopes are added.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import settings
from app.google_auth import SCOPES, save_credentials


def main() -> None:
    if not os.path.exists(settings.google_client_secret_file):
        sys.exit(
            f"Not found: {settings.google_client_secret_file}\n"
            "Download the OAuth client JSON from Google Cloud (docs/google-cloud-setup.md) and save it there."
        )
    flow = InstalledAppFlow.from_client_secrets_file(settings.google_client_secret_file, SCOPES)
    # Starts a tiny temporary web server on a random port, opens your browser to Google's
    # sign-in page, and catches the redirect when you click Allow.
    creds = flow.run_local_server(port=0)
    save_credentials(creds)
    print(f"Saved Google token to {settings.google_token_file}")


if __name__ == "__main__":
    main()
