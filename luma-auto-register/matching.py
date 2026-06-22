"""Pure matching/classification helpers (no browser or network deps).

Kept dependency-free so the logic is unit-testable without Playwright.
"""

from __future__ import annotations

import re

LUMA_BASE = "https://lu.ma"

# Reserved top-level paths on lu.ma that are never an individual event.
NON_EVENT_SLUGS = {
    "home", "signin", "signup", "discover", "create", "settings",
    "help", "pricing", "about", "terms", "privacy", "explore",
    "calendars", "user", "p", "blog", "careers", "contact",
    "unsubscribe", "check-in", "login", "logout", "search",
}

_PRICE_RE = re.compile(r"[$£€]\s?(\d+(?:\.\d{2})?)")


def looks_like_event_path(href: str) -> bool:
    """True if an href points at an individual Luma event page.

    Event pages are either ``/e/<id>`` or a single short slug containing a
    digit (e.g. ``/abc123``). City/discover pages are plain words and are
    excluded, as are the reserved app paths above.
    """
    if href.startswith("http") and "lu.ma" not in href:
        return False
    path = href.split("lu.ma")[-1] if href.startswith("http") else href
    path = path.split("?")[0].split("#")[0].strip("/")
    if not path:
        return False
    parts = path.split("/")
    if parts[0] == "e" and len(parts) == 2 and parts[1]:
        return True
    if len(parts) == 1:
        slug = parts[0]
        if slug.lower() in NON_EVENT_SLUGS:
            return False
        # Real event slugs are short alphanumerics that include a digit;
        # city pages ("sf", "nyc", "london") are pure letters.
        return bool(slug) and any(c.isdigit() for c in slug)
    return False


def normalize_event_url(href: str) -> str:
    """Return a canonical absolute event URL (no query/fragment/trailing /)."""
    full = href if href.startswith("http") else f"{LUMA_BASE}{href}"
    return full.split("?")[0].split("#")[0].rstrip("/")


def looks_paid(lowered_body: str) -> bool:
    """Heuristic: True only if the page shows a non-zero price and no free tier.

    "free" appearing anywhere means at least one free option exists, so we treat
    the event as free-registerable.
    """
    if "free" in lowered_body:
        return False
    for m in _PRICE_RE.finditer(lowered_body):
        try:
            if float(m.group(1)) > 0:
                return True
        except ValueError:
            continue
    return False
