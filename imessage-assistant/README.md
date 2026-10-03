# iMessage AI Assistant

A personal Claude assistant you text over iMessage. Runs on your Mac.

```
iPhone --iMessage--> Mac (BlueBubbles) --POST /webhook--> this server
   --> filters (secret, allowlist, not-from-me, not group, not tapback, not duplicate)
   --> load last 20 messages (SQLite, if memory is on)
   --> Claude --> BlueBubbles REST API --> reply arrives on your phone
   --> save your text + the reply (SQLite)
```

**Status:** Phases 1–3 (core loop, memory, background service) and the first Phase 4 tool (read-only Google Calendar) are written and unit-tested, but **none of it has been tested on the Mac yet**. Memory and Calendar ship turned off, so you can test one piece at a time.

## When you get home: test in this order

Each step only adds one new thing. If a step fails, the problem is in that step.

1. **Part 1 + Part 2**: install, `check_setup --send`, run uvicorn by hand, add the webhook, text the bot. *(Phase 1)*
2. **Part 3**: `MEMORY_ENABLED=true`, run the favorite-color test. *(Phase 2)*
3. **Part 4**: stop uvicorn, `scripts.service install`, the kill-and-restart test, auto-login settings. *(Phase 3)*
4. **Part 5**: Google sign-in, `GOOGLE_CALENDAR_ENABLED=true`, ask about your calendar. *(Phase 4a. Needs the Google Cloud setup done first; you can do that from any laptop.)*

## Files

| File | What it does |
|---|---|
| `app/config.py` | Loads `.env` and normalizes phone numbers so `+1 (555) 123-4567` matches `5551234567` |
| `app/main.py` | FastAPI server: `/webhook` decides whether to reply; `/health` is for checks |
| `app/bluebubbles.py` | Parses BlueBubbles webhooks and sends texts through its REST API |
| `app/claude_client.py` | The Claude API call |
| `app/memory.py` | SQLite conversation history (`data/assistant.db`) |
| `app/tools.py` | Tool definitions Claude sees, and `run_tool()` that executes them |
| `app/google_auth.py`, `app/google_calendar.py` | Google sign-in token handling; read-only Calendar queries |
| `scripts/google_login.py` | One-time Google sign-in (opens a browser on the Mac) |
| `docs/google-cloud-setup.md` | Click-by-click Google Cloud console setup |
| `app/logging_setup.py` | Logs to the terminal and `logs/assistant.log` (rotating, max 5 MB) |
| `scripts/check_setup.py` | Tests BlueBubbles and Claude separately, before you try end to end |
| `scripts/service.py` | Installs, restarts, checks or removes the launchd background service |
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
pytest -q          # expect: "N passed", no failures
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

## Part 3: Turn on memory (Phase 2)

Do this only after Part 2 works with memory off.

1. In `.env`, set `MEMORY_ENABLED=true`.
2. Stop the server (Ctrl+C) and start it again. The log should say `Memory ON: last 20 messages per chat`.
3. Text "My favorite color is green." Then text "What's my favorite color?" It should answer green. With memory off, it can't know.
4. Look at what was stored (you already know SQL, so this is just a normal table):
   ```bash
   sqlite3 data/assistant.db "SELECT id, role, substr(content, 1, 60), created_at FROM messages ORDER BY id DESC LIMIT 10"
   ```
5. To wipe memory and start fresh: stop the server, then `rm data/assistant.db`. It's recreated on the next start.

How memory behaves:
- Rows are saved only after BlueBubbles accepts the reply for sending. If Claude or the send fails, neither your text nor a reply is stored, so failed attempts never show up in history.
- Your text and the reply are saved together in one transaction, so the history always alternates you → bot → you → bot. Claude's API expects that order.
- If you send two texts quickly, the second waits until the first is answered and saved, so the second can see the first.
- `HISTORY_LIMIT=20` means 20 messages: your last 10 texts plus the bot's last 10 replies.

---

## Part 4: Run it as a background service (Phase 3)

Do this after Parts 2 and 3 work with uvicorn running in a terminal. After this, you no longer start the server by hand: macOS starts it at login and restarts it within about 10 seconds if it crashes.

**1. Stop the uvicorn you started by hand** (Ctrl+C in that terminal). Two servers can't use port 8000 at the same time.

**2. Install the service:**
```bash
cd ~/Projects/imessage-assistant && source .venv/bin/activate
python -m scripts.service install
python -m scripts.service status
```
`status` should show `state = running` and `/health -> 200`. Text the bot to confirm it still replies.

**3. Test the auto-restart.** Kill the process and watch launchd bring it back:
```bash
pkill -f "uvicorn app.main:app"
sleep 15 && python -m scripts.service status    # should be running again, with a new pid
```

**4. Make the Mac recover on its own after a power cut or reboot.** The service runs inside your login session, and so do BlueBubbles and Messages. So all three only come back if the Mac logs you in automatically.
- **BlueBubbles Server** → Settings → turn on its start-at-login option (named something like "Startup with macOS").
- **System Settings → Users & Groups → Automatically log in as** → your user. macOS hides this option while **FileVault** disk encryption is on. Turning FileVault off lets anyone who steals the Mac read the disk. That's your trade-off to make. If you keep FileVault on, someone has to type your password after every reboot before anything works.
- **System Settings → Energy → "Start up automatically after a power failure"** → on (desktop Macs; laptops don't have it).

**Day-to-day commands:**

| Task | Command |
|---|---|
| After changing code or `.env` | `python -m scripts.service restart` |
| Is it running? | `python -m scripts.service status` |
| Watch the log | `tail -f logs/assistant.log` |
| It keeps crashing on startup | `cat logs/launchd.err.log` (startup errors such as a missing `.env` setting land here, because they happen before logging starts) |
| Remove the service | `python -m scripts.service uninstall` |

Texts that arrive while the server is down (during a restart, for example) are not answered later. BlueBubbles sends each webhook once and doesn't retry.

---

## Part 5: Google Calendar (Phase 4a, read-only)

1. Do the Google Cloud console steps in [`docs/google-cloud-setup.md`](docs/google-cloud-setup.md). Any laptop works. You end up with a `google_client_secret.json` file.
2. On the Mac, follow step 5 of that doc: `pip install -r requirements.txt`, move the JSON into `secrets/`, then `python -m scripts.google_login`.
3. Set `GOOGLE_CALENDAR_ENABLED=true` in `.env`, then `python -m scripts.service restart`.
4. Text "What's on my calendar today?" and "Am I free Thursday afternoon?" In the log you should see `Tool call: list_calendar_events {...}` followed by a reply listing your events.

How tools work: Claude's reply either answers you, or says "I want to call `list_calendar_events` with these inputs." In the second case, `get_reply()` runs the tool, adds the result to the conversation, and asks Claude again. It allows at most 5 rounds of this per text. If something goes wrong in a tool (bad date, expired Google login), the error goes back to Claude as text, and Claude tells you about it by text instead of the bot crashing.

Limits right now: primary calendar only (not shared or subscribed calendars). It can only read; nothing can create or change events. The current date and time come from the Mac's clock and time zone.

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
| Bot forgets things with memory on | Check the log line `Claude replied: history=N msgs`. If N is always 0, `MEMORY_ENABLED` isn't `true`, or the server wasn't restarted. |
| Bot says Google access expired | Run `python -m scripts.google_login` on the Mac. If this happens every 7 days, your Google app is in Testing mode (see the decision in `docs/google-cloud-setup.md`). |
| Calendar answers have the wrong day or time | The bot uses the Mac's time zone. Check System Settings → General → Date & Time. |
| `Reply sent, but saving message ... failed` | The reply reached you but wasn't stored. Usually disk space or permissions on `data/`. |

---

## Design notes

- **Why reply in the background:** the webhook returns `200` right away, and the slow Claude call (a few seconds) runs afterwards. If BlueBubbles had to wait for Claude, it might time out and resend the webhook.
- **Why there's a duplicate check:** if a webhook is delivered twice, the second copy is dropped by message GUID, so you never get two replies to one text. The list of recent GUIDs is kept in RAM and resets on restart. That's fine for duplicates that arrive seconds apart.
- **Why group chats are ignored:** a reply in a group chat goes to everyone in it, even when you were the one who sent the message.
- **Model and cost:** `claude-opus-5-5` at `effort=low`, priced at $4/$20 per million input/output tokens. With memory off, a short exchange costs roughly $0.005–$0.01. With memory on, every request resends up to 20 earlier messages, so expect a few cents per text if your messages are long. You can change `CLAUDE_MODEL` and `CLAUDE_EFFORT` in `.env`.
- **Why no prompt caching:** caching only pays off when the same prompt start is resent within about 5 minutes. Texts are usually further apart than that. Once there are 20 messages, the oldest one drops off every turn, so the start of the prompt changes each time anyway. Writing to the cache costs 25% more than normal input, so here it would raise the bill, not lower it.
- **Refusal fallback:** the API call turns on server-side `fallbacks="default"`. If a safety filter wrongly declines a harmless message, the API retries it on a fallback model in the same call. If the whole chain still declines, you get "Sorry, I can't help with that one."

## Roadmap

1. Core loop: written and unit-tested, not yet tested on the Mac
2. Memory (last 20 messages per chat in SQLite): written and unit-tested, not yet tested on the Mac
3. launchd service with auto-restart: written and unit-tested, not yet tested on the Mac
4. Tools: Google Calendar (read): written and unit-tested, not yet tested on the Mac → Gmail (read → draft → send, with confirmation by text) → Google Drive. Every side-effecting action asks for confirmation first.
5. Scheduled tasks (e.g. a morning calendar summary)
