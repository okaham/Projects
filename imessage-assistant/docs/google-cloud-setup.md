# Google Cloud setup (for the Calendar tool, and later Gmail and Drive)

You can do all of this from any laptop browser. It takes about 15 minutes, and none of it needs the Mac until the last step.

Google renames console pages often. If a label below doesn't match what you see, look for the same idea nearby. As of 2025–2026, the OAuth settings live in a section called **Google Auth Platform**.

## 1. Create a project

1. Go to <https://console.cloud.google.com> and sign in with **the Google account whose calendar you want the bot to read**.
2. Click the project picker at the top left (it may say "Select a project") → **New Project**.
3. Name it `imessage-assistant`. Leave Organization as "No organization". Click **Create**.
4. When it finishes, make sure the project picker shows `imessage-assistant`. Every step below happens inside this project.

## 2. Turn on the Calendar API

1. ☰ menu → **APIs & Services** → **Library**.
2. Search for **Google Calendar API**, open it, and click **Enable**.

(Later phases: enable **Gmail API** and **Google Drive API** the same way when we get to them.)

## 3. Set up the consent screen (what Google shows when you sign in)

1. ☰ → **APIs & Services** → **OAuth consent screen**. This opens Google Auth Platform. Click **Get started**.
2. **App information**: App name `iMessage Assistant`, User support email = your email → **Next**.
3. **Audience**: choose **External** → **Next**. "Internal" is only for Google Workspace accounts. A normal @gmail.com account has to use External.
4. **Contact information**: your email → **Next**.
5. Agree to the policy → **Continue** → **Create**.
6. Left sidebar → **Audience** → under **Test users**, click **Add users** → enter your own Gmail address → **Save**.
7. Left sidebar → **Data Access** → **Add or remove scopes** → filter for `calendar.readonly` → tick `.../auth/calendar.readonly` → **Update** → **Save**.

## 4. Create the OAuth client (the app's ID card)

1. Left sidebar → **Clients** → **Create client**.
2. Application type: **Desktop app**. Name: `imessage-assistant-mac`. Click **Create**.
3. **Click "Download JSON" in the dialog that appears.** Google may only show the client secret once, when you create the client. If you close the dialog without downloading, delete the client and make a new one.
4. Rename the downloaded file to `google_client_secret.json`.

Treat this file like a password. Don't email it or commit it. To get it onto the Mac, use AirDrop, or iCloud Drive and delete it from iCloud afterwards.

## 5. On the Mac (when you're home)

```bash
cd ~/Projects/imessage-assistant && source .venv/bin/activate
pip install -r requirements.txt                 # installs the Google libraries
mkdir -p secrets && mv ~/Downloads/google_client_secret.json secrets/
python -m scripts.google_login                  # opens a browser - sign in and click Allow
```
Google will warn **"Google hasn't verified this app"**. That's expected: you wrote the app, and Google hasn't reviewed it. Click **Continue** (or **Advanced → Go to iMessage Assistant**), then **Allow**.

Then set `GOOGLE_CALENDAR_ENABLED=true` in `.env`, restart the service, and text "What's on my calendar today?"

---

## Decision needed: "Testing" mode expires your login every 7 days

Your spec says the app stays in **Testing** mode. Google's rule: while an External app is in Testing and asks for anything beyond basic profile info (Calendar does), **the sign-in it gives you expires after 7 days**. For a bot that's meant to always be on, that means:

**Option A: stay in Testing.** Every 7 days, calendar questions stop working. The bot texts you "Google access expired... run: python -m scripts.google_login", and you re-run that on the Mac, sitting at it, because it opens a browser. Nothing else to do.

**Option B (my recommendation): publish the app ("In production") but don't submit it for verification.** Google Auth Platform → **Audience** → **Publish app**. You'll keep seeing the "unverified app" warning when you sign in. The sign-in no longer expires on a 7-day clock. Google can still cancel it if you revoke access or it goes unused for 6 months. Once Gmail is added, changing your Google password also cancels it. Google exempts personal-use apps from verification. An unverified app is capped at 100 users, and you are 1. **Before we add Gmail**, re-check this: Gmail read/send access counts as "restricted" scopes, and Google is stricter about those.

Option B doesn't list the app anywhere or give anyone access to your data. Reading your calendar still requires signing in as you, and the bot only answers your phone number.

Tell me A or B. The code works either way. B just removes the weekly re-login.
