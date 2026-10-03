import os

# Fake settings so tests never need a real .env. These win over .env because
# load_dotenv() does not overwrite variables that are already set.
os.environ.update(
    {
        "ANTHROPIC_API_KEY": "test-key",
        "BLUEBUBBLES_URL": "http://bluebubbles.test",
        "BLUEBUBBLES_PASSWORD": "test-password",
        "ALLOWED_SENDERS": "+1 (555) 123-4567, me@icloud.com",
        "WEBHOOK_SECRET": "s3cret",
        "LOG_FILE": "/tmp/imessage-assistant-test.log",
    }
)
