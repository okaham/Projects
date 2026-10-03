"""Check each piece separately before testing end to end.

    python -m scripts.check_setup            # check .env, BlueBubbles, Claude
    python -m scripts.check_setup --send     # also text "test" to the first ALLOWED_SENDERS number
"""

import sys

from app.config import settings


def main() -> int:
    ok = True
    print(f".env loaded. Allowed senders: {sorted(settings.allowed_senders)}")

    from app.bluebubbles import ping, send_text
    try:
        if ping():
            print("[OK]   BlueBubbles reachable at", settings.bluebubbles_url)
        else:
            print("[FAIL] BlueBubbles answered but rejected the password")
            ok = False
    except Exception as e:
        print(f"[FAIL] Can't reach BlueBubbles at {settings.bluebubbles_url}: {e}")
        ok = False

    from app.claude_client import get_reply
    try:
        print("[OK]   Claude says:", get_reply("Reply with exactly: OK"))
    except Exception as e:
        print(f"[FAIL] Claude call failed: {e}")
        ok = False

    if settings.memory_enabled:
        from app import memory
        try:
            memory.init_db()
            print(f"[OK]   Memory database ready at {settings.db_path}")
        except Exception as e:
            print(f"[FAIL] Memory database at {settings.db_path}: {e}")
            ok = False
    else:
        print("[--]   Memory is off (MEMORY_ENABLED=false)")

    if "--send" in sys.argv:
        target = sorted(settings.allowed_senders)[0]
        # 1:1 iMessage chat guids look like "iMessage;-;+15551234567" or "iMessage;-;me@icloud.com"
        address = target if "@" in target else "+" + target
        chat_guid = f"iMessage;-;{address}"
        try:
            send_text(chat_guid, "Test message from your assistant (check_setup).")
            print("[OK]   Sent test text to", chat_guid)
        except Exception as e:
            print(f"[FAIL] Sending to {chat_guid} failed: {e}")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
