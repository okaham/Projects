# iMessage AI Assistant

A personal Claude assistant you text over iMessage. Runs on your Mac.

```
iPhone --iMessage--> Mac (BlueBubbles) --POST /webhook--> this server
   --> filters (secret, allowlist, not-from-me, not group, not tapback, not duplicate)
   --> Claude --> BlueBubbles REST API --> reply arrives on your phone
```

**Current phase: 1 (core loop).** No memory or tools yet. Each text is answered on its own.

## Files

| File | What it does |
|---|---|
| `app/config.py` | Loads `.env` and normalizes phone numbers so `+1 (555) 123-4567` matches `5551234567` |
| `app/main.py` | FastAPI server: `/webhook` decides whether to reply; `/health` is for checks |
| `app/bluebubbles.py` | Parses BlueBubbles webhooks and sends texts through its REST API |
| `app/claude_client.py` | The Claude API call |
| `app/logging_setup.py` | Logs to the terminal and `logs/assistant.log` (rotating, max 5 MB) |
| `scripts/check_setup.py` | Tests BlueBubbles and Claude separately, before you try end to end |
| `tests/` | Tests for the webhook filters (Claude and BlueBubbles are faked) |

---

## Part 1: Install on the Mac

Run these in Terminal (or over SSH).

**1. Python 3.11+.** The `python3` that ships with macOS is usually 3.9, which is too old. The code uses `str | None` syntax, which needs 3.10+.
```bash
python3 --version              # if this is below 3.11:
brew install python@3.11       # then use python3.11 below
```

**2. Get the code and install the dependencies into a virtual environment** (an isolated folder of packages, so they don't touch the system Python):
```bash
git clone https://github.com/okaham/Projects.git ~/Projects
cd ~/Projects/imessage-assistant
python3.11 -m venv .venv
source .venv/bin/activate      # run this again in every new terminal
pip install -r requirements.txt
```

**3. Create `.env`:**
```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # copy the output into WEBHOOK_SECRET
open -e .env                                                    # opens it in TextEdit
```
Fill in:
- `ANTHROPIC_API_KEY`: from console.anthropic.com → API Keys.
- `BLUEBUBBLES_PASSWORD`: the server password you set in BlueBubbles (see Part 2, step 1).
- `ALLOWED_SENDERS`: **your** phone number, the one you'll be texting *from*. Any format works.
- `WEBHOOK_SECRET`: the random string from the command above.

**4. Run the tests** (no network needed):
```bash
pytest -q          # expect: 14 passed
```

---

## Part 2: Configure BlueBubbles

The labels below match recent BlueBubbles Server versions. If yours differ slightly, look for the same thing under a nearby name.

**1. Find the server password and port.**
- Open the **BlueBubbles Server** app → **Settings** (left sidebar) → **Connection**.
- **Server Password**: copy it into `BLUEBUBBLES_PASSWORD` in `.env`.
- **Local Port**: usually `1234`. If yours is different, change `BLUEBUBBLES_URL` in `.env` to match.

**2. Check that this project can reach BlueBubbles and Claude:**
```bash
python -m scripts.check_setup
```
You want two `[OK]` lines. Then test sending:
```bash
python -m scripts.check_setup --send
```
Your phone should receive "Test message from your assistant." **Do not continue until this works.** If the send fails, see Troubleshooting below.

**3. Start the server** (leave this terminal open):
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
`127.0.0.1` means only programs on this Mac can reach it. Nothing on your network can. BlueBubbles runs on the same Mac, so that's all it needs.

**4. Add the webhook in BlueBubbles.**
- BlueBubbles Server app → **API & Webhooks** (left sidebar).
- In the **Webhooks** section, click **Add Webhook** (the **+** button).
- **URL**: `http://127.0.0.1:8000/webhook?secret=PASTE_YOUR_WEBHOOK_SECRET`
- **Events**: select only **New Messages**. Leave the others unchecked; the server ignores them anyway.
- Click **Save**.

**5. Test end to end.** In a second terminal:
```bash
cd ~/Projects/imessage-assistant && tail -f logs/assistant.log
```
From your iPhone, text the Apple ID that BlueBubbles is signed into. In the log you should see `Accepted message ... ` → `Claude replied ...` → `Sent reply ...`, and then the reply should arrive on your phone.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Nothing appears in the log when you text | The webhook isn't reaching the server. Check the uvicorn terminal is still running, the port is 8000, and the webhook URL is exactly right. |
| `Rejected webhook with wrong secret` | The `?secret=` in the BlueBubbles URL doesn't match `WEBHOOK_SECRET` in `.env`. |
| `Ignoring ... not in ALLOWED_SENDERS` | The log prints the address it actually received. If you text from an email Apple ID rather than your number, add that email to `ALLOWED_SENDERS`. |
| `Ignoring ... sent by this Mac` on **your** texts | Your phone and the Mac use the same Apple ID, so every message counts as "from me." Sign the Mac into a separate Apple ID. The bot can't work any other way, because "from me" is the only signal that stops it replying to itself forever. |
| `BlueBubbles send failed: HTTP 500` | Usually a macOS permission. System Settings → Privacy & Security → **Automation** → BlueBubbles → turn on **Messages**. Also check that Full Disk Access and Accessibility are still granted. |
| `Claude call failed` / 401 | Bad `ANTHROPIC_API_KEY`, or the account has no credits. |
| Changed `.env` and nothing happened | Settings load at startup. Restart uvicorn (Ctrl+C, then run it again). |

---

## Design notes

- **Why reply in the background:** the webhook returns `200` right away, and the slow Claude call (a few seconds) runs afterwards. If BlueBubbles had to wait for Claude, it might time out and resend the webhook.
- **Why there's a duplicate check:** if a webhook is delivered twice, the second copy is dropped by message GUID, so you never get two replies to one text. The list lives in memory and resets on restart. It moves to SQLite in Phase 2.
- **Why group chats are ignored:** a reply in a group chat goes to everyone in it, even when you were the one who sent the message.
- **Model and cost:** `claude-opus-5-5` at `effort=low`. A short exchange is a few hundred tokens, so roughly $0.005–$0.01 per text at $4/$20 per million input/output tokens. Once Phase 2 adds 20 messages of history, every request resends that history, so expect several times more per text. You can change `CLAUDE_MODEL` and `CLAUDE_EFFORT` in `.env`.
- **Refusal fallback:** the API call turns on server-side `fallbacks="default"`. If a safety filter wrongly declines a harmless message, the API retries it on a fallback model in the same call. If the whole chain still declines, you get "Sorry, I can't help with that one."

## Roadmap

1. ✅ Core loop (verify end to end on the Mac)
2. Memory: last ~20 messages per chat in SQLite
3. launchd service with auto-restart
4. Tools: Google Calendar (read) → Gmail (read → draft → send, with confirmation by text) → Google Drive. Every side-effecting action asks for confirmation first.
5. Scheduled tasks (e.g. a morning calendar summary)
