# Luma Auto-Register (for minipc1)

Automatically scans **lu.ma** for events and registers the account
`howard.linra@gmail.com` for **free** ones — fully hands-off.

What it does each run:

1. **Login** — passwordless. Enters the email, then reads the 6-digit login
   code automatically from Gmail (IMAP). The browser session is saved to disk,
   so later runs skip login entirely.
2. **Discover** — scrapes one or more **city discover pages** (default: `sf`).
3. **Private / invited events** — scans the Gmail inbox for Luma *invitation*
   emails and pulls those event links too. This is the only reliable way to
   reach **private (unlisted) events** — they never show on public pages.
4. **Register** — for each new event: registers if it's **free** and one-click;
   **skips** paid events and ones needing host approval / waitlist.
5. **Dedup** — every handled event is recorded in `state/seen_events.json` so it
   is never processed twice.

> ⚠️ Private events across "the whole web" cannot be discovered — by design they
> are unlisted and require a direct invite. The inbox scanner (step 3) catches
> exactly the private events you've actually been invited to. See the FAQ below.

---

## Setup on minipc1

```bash
cd luma-auto-register

# 1. Python deps + the Chromium browser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps   # Linux: installs system libs for Chromium

# 2. Configure
cp .env.example .env
# edit .env — set GMAIL_APP_PASSWORD and LUMA_CITIES
```

### Gmail App Password (required)

The login code is read over IMAP, so the account needs a Google **App
Password** (not your normal password):

1. Enable 2-Step Verification on the Google account.
2. Go to <https://myaccount.google.com/apppasswords>, create one, paste it into
   `GMAIL_APP_PASSWORD` in `.env`.
3. Make sure IMAP is enabled (Gmail → Settings → Forwarding and POP/IMAP).

---

## First run

Do a visible login + dry run first to confirm everything works:

```bash
# Watch the browser, establish the saved session:
HEADLESS=false python luma_auto_register.py --login

# See what it WOULD register, without clicking anything:
python luma_auto_register.py --dry-run
```

Then a real scan:

```bash
python luma_auto_register.py
```

Run forever on an interval (uses `POLL_INTERVAL_MINUTES`):

```bash
python luma_auto_register.py --loop
```

---

## Run it on a schedule (minipc1)

### Option A — cron (every hour)

```cron
# crontab -e
0 * * * * cd /home/USER/physical-ai-matrix/luma-auto-register && \
  .venv/bin/python luma_auto_register.py >> state/run.log 2>&1
```

### Option B — systemd timer

`/etc/systemd/system/luma-register.service`

```ini
[Unit]
Description=Luma auto-register
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/USER/physical-ai-matrix/luma-auto-register
ExecStart=/home/USER/physical-ai-matrix/luma-auto-register/.venv/bin/python luma_auto_register.py
```

`/etc/systemd/system/luma-register.timer`

```ini
[Unit]
Description=Run Luma auto-register hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now luma-register.timer
```

---

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LUMA_EMAIL` | — | Account to register with |
| `GMAIL_ADDRESS` | = `LUMA_EMAIL` | Inbox to read the login code from |
| `GMAIL_APP_PASSWORD` | — | Google App Password (required) |
| `LUMA_CITIES` | `sf` | Comma-separated discover slugs, e.g. `sf,nyc` |
| `KEYWORD_FILTER` | *(empty)* | Only register if title/desc matches one of these |
| `SCAN_INBOX_INVITES` | `true` | Also register private/invited events from email |
| `INVITE_LOOKBACK_DAYS` | `30` | How far back to scan invite emails |
| `HEADLESS` | `true` | `false` to watch the browser |
| `POLL_INTERVAL_MINUTES` | `30` | Interval for `--loop` |
| `MAX_REGISTRATIONS_PER_RUN` | `15` | Safety cap per scan |

---

## FAQ

**Can it find private events across the whole internet?**
No — and neither can anything else. A "private" (unlisted) Luma event has no
public listing and is reachable only via a direct invite link. This tool finds
the private events *you have been invited to* by scanning the invitation emails
Luma sends to your Gmail (`SCAN_INBOX_INVITES`). That is the complete, reliable
set of private events you can actually register for.

**Will it double-register?**
No. Luma blocks duplicate registration, and the tool also detects an
already-registered state and records every event in `state/seen_events.json`.
⚠️ If you run this *and* another automated registrar (e.g. the existing
`luma_event_manager` cronjob) against the same account, they keep **separate**
seen-state — disable one to avoid redundant scanning.

**Selectors broke / login fails.**
Run with `HEADLESS=false` to watch, and check `screenshots/` — the tool saves a
screenshot whenever a step can't be confirmed.

---

## Files

| File | Purpose |
|---|---|
| `luma_auto_register.py` | Main script / CLI |
| `config.py` | Loads `.env` |
| `otp_reader.py` | Reads the login code from Gmail (IMAP) |
| `invite_scanner.py` | Finds private/invited events in the inbox |
| `state/` | Saved session + seen-events (gitignored) |
| `screenshots/` | Debug screenshots (gitignored) |
