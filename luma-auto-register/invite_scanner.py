"""Discover *private* / unlisted Luma events from invitation emails in Gmail.

Private Luma events are intentionally unlisted: they never appear on a public
city discover page. The only programmatic way to find the ones you actually
have access to is the invitation Luma emails you. This module scans the inbox
for those invites and extracts the event URLs so they can be auto-registered
just like discovered public events.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header
from email.message import Message

log = logging.getLogger("luma.invites")

# Match lu.ma event links inside the email HTML/body.
EVENT_URL_RE = re.compile(r"https?://lu\.ma/([A-Za-z0-9\-]+)")

# Reserved non-event slugs we never treat as an event.
_NON_EVENT = {
    "home", "signin", "signup", "discover", "create", "settings", "help",
    "pricing", "about", "terms", "privacy", "explore", "calendars", "user",
    "p", "blog", "careers", "contact", "unsubscribe", "e", "check-in",
}

INVITE_SUBJECT_HINTS = ("invit", "you're going", "rsvp", "reminder", "added you")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    out = []
    for text, enc in decode_header(value):
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _body_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    return "\n".join(chunks)


def scan_invite_urls(
    imap_host: str,
    address: str,
    app_password: str,
    *,
    lookback_days: int = 30,
    max_emails: int = 200,
) -> list[str]:
    """Return de-duplicated lu.ma event URLs found in recent Luma emails."""
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    found: list[str] = []
    seen: set[str] = set()

    try:
        with imaplib.IMAP4_SSL(imap_host) as imap:
            imap.login(address, app_password)
            imap.select("INBOX")
            # Luma sends from the lu.ma domain.
            typ, data = imap.search(None, f'(SINCE {since} FROM "lu.ma")')
            ids = data[0].split() if data and data[0] else []
            for msg_id in reversed(ids[-max_emails:]):
                typ, msg_data = imap.fetch(msg_id, "(RFC822)")
                if typ != "OK" or not msg_data:
                    continue
                raw = next((p[1] for p in msg_data if isinstance(p, tuple)), None)
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                subject = _decode(msg.get("Subject")).lower()
                # Keep invites/RSVPs/reminders; these carry the event link.
                if not any(h in subject for h in INVITE_SUBJECT_HINTS):
                    continue
                body = _body_text(msg)
                for m in EVENT_URL_RE.finditer(body):
                    slug = m.group(1)
                    if slug.lower() in _NON_EVENT:
                        continue
                    url = f"https://lu.ma/{slug}"
                    if url not in seen:
                        seen.add(url)
                        found.append(url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Invite scan failed: %s", exc)

    log.info("Inbox invite scan found %d private/invited event link(s).", len(found))
    return found
