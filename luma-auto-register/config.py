"""Configuration loading for the Luma auto-register tool."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
STORAGE_STATE_PATH = STATE_DIR / "storage_state.json"
SEEN_EVENTS_PATH = STATE_DIR / "seen_events.json"
STATS_PATH = STATE_DIR / "stats.json"


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    luma_email: str
    gmail_imap_host: str
    gmail_address: str
    gmail_app_password: str
    cities: list[str]
    keyword_filter: list[str] = field(default_factory=list)
    headless: bool = True
    poll_interval_minutes: int = 30
    max_registrations_per_run: int = 15
    scan_inbox_invites: bool = True
    invite_lookback_days: int = 30
    request_approval_events: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def load(cls) -> "Config":
        if load_dotenv is not None:
            load_dotenv(BASE_DIR / ".env")

        missing = []

        def required(key: str) -> str:
            val = os.getenv(key, "").strip()
            if not val:
                missing.append(key)
            return val

        luma_email = required("LUMA_EMAIL")
        gmail_address = os.getenv("GMAIL_ADDRESS", "").strip() or luma_email
        gmail_app_password = required("GMAIL_APP_PASSWORD").replace(" ", "")
        cities = _split_csv(os.getenv("LUMA_CITIES"))
        if not cities:
            missing.append("LUMA_CITIES")

        if missing:
            raise SystemExit(
                "Missing required config values: "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill them in."
            )

        return cls(
            luma_email=luma_email,
            gmail_imap_host=os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com").strip(),
            gmail_address=gmail_address,
            gmail_app_password=gmail_app_password,
            cities=cities,
            keyword_filter=_split_csv(os.getenv("KEYWORD_FILTER")),
            headless=os.getenv("HEADLESS", "true").strip().lower() != "false",
            poll_interval_minutes=int(os.getenv("POLL_INTERVAL_MINUTES", "30")),
            max_registrations_per_run=int(
                os.getenv("MAX_REGISTRATIONS_PER_RUN", "15")
            ),
            scan_inbox_invites=os.getenv("SCAN_INBOX_INVITES", "true")
            .strip()
            .lower()
            != "false",
            invite_lookback_days=int(os.getenv("INVITE_LOOKBACK_DAYS", "30")),
            request_approval_events=os.getenv("REQUEST_APPROVAL_EVENTS", "false")
            .strip()
            .lower()
            == "true",
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        )
