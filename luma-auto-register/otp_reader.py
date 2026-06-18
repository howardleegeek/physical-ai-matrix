"""Read the Luma sign-in OTP code from Gmail over IMAP."""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from email.header import decode_header
from email.message import Message

log = logging.getLogger("luma.otp")

# Luma sends the login code from these addresses. We match loosely on the
# domain so we don't break if the exact sender mailbox changes.
LUMA_SENDER_HINTS = ("lu.ma", "luma", "no-reply")

# A standalone 6-digit code (Luma uses 6 digits).
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _body_text(msg: Message) -> str:
    """Extract a plain-ish text body from an email message."""
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    text = "\n".join(chunks)
    # Strip HTML tags so the regex sees the digits cleanly.
    return re.sub(r"<[^>]+>", " ", text)


def _looks_like_luma(from_header: str, subject: str) -> bool:
    haystack = f"{from_header} {subject}".lower()
    return any(hint in haystack for hint in LUMA_SENDER_HINTS)


def fetch_login_code(
    imap_host: str,
    address: str,
    app_password: str,
    *,
    not_before: float,
    timeout_seconds: int = 120,
    poll_seconds: int = 5,
) -> str | None:
    """Poll the inbox for a fresh Luma login code.

    `not_before` is a unix timestamp; only emails received at/after this time
    are considered, so we never read a stale code from a previous attempt.
    Returns the 6-digit code, or None on timeout.
    """
    deadline = time.time() + timeout_seconds
    log.info("Waiting for Luma login code in %s ...", address)

    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL(imap_host) as imap:
                imap.login(address, app_password)
                imap.select("INBOX")
                # Search recent messages; IMAP SINCE is day-granular so we
                # additionally filter by the message's internal date below.
                typ, data = imap.search(None, "UNSEEN")
                ids = data[0].split() if data and data[0] else []
                # Newest first.
                for msg_id in reversed(ids):
                    typ, msg_data = imap.fetch(msg_id, "(RFC822 INTERNALDATE)")
                    if typ != "OK" or not msg_data:
                        continue
                    raw = next(
                        (p[1] for p in msg_data if isinstance(p, tuple)), None
                    )
                    if not raw:
                        continue
                    msg = email.message_from_bytes(raw)

                    received = email.utils.parsedate_to_datetime(msg.get("Date"))
                    if received is not None and received.timestamp() < not_before - 60:
                        continue

                    from_header = _decode(msg.get("From"))
                    subject = _decode(msg.get("Subject"))
                    if not _looks_like_luma(from_header, subject):
                        continue

                    body = f"{subject}\n{_body_text(msg)}"
                    match = CODE_RE.search(body)
                    if match:
                        code = match.group(1)
                        log.info("Found login code from %s", from_header)
                        # Mark as read so we don't reuse it.
                        imap.store(msg_id, "+FLAGS", "\\Seen")
                        return code
        except Exception as exc:  # noqa: BLE001
            log.warning("IMAP poll error (will retry): %s", exc)

        time.sleep(poll_seconds)

    log.error("Timed out waiting for Luma login code.")
    return None
