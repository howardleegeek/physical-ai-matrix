#!/usr/bin/env python3
"""Luma auto-register.

Scans one or more lu.ma city discover pages, and automatically registers the
configured account for FREE events it hasn't seen before.

Login is passwordless: the script enters the email, Luma emails a 6-digit code,
and the code is read automatically from Gmail over IMAP. The browser session is
persisted to disk so subsequent runs skip the login step entirely.

Usage:
    python luma_auto_register.py            # one scan
    python luma_auto_register.py --loop     # scan forever on an interval
    python luma_auto_register.py --dry-run  # find + log, but never click Register
    python luma_auto_register.py --login    # just (re)establish the session

Run `python -m playwright install chromium` once after installing deps.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from config import (
    SCREENSHOT_DIR,
    SEEN_EVENTS_PATH,
    STATE_DIR,
    STATS_PATH,
    STORAGE_STATE_PATH,
    Config,
)
from invite_scanner import scan_invite_urls
from matching import looks_like_event_path, looks_paid, normalize_event_url
from otp_reader import fetch_login_code
from reporter import Stats, format_report, send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("luma")

LUMA_BASE = "https://lu.ma"


# --------------------------------------------------------------------------- #
# State (dedup of already-handled events)
# --------------------------------------------------------------------------- #
def load_seen() -> dict[str, dict]:
    if SEEN_EVENTS_PATH.exists():
        try:
            return json.loads(SEEN_EVENTS_PATH.read_text())
        except json.JSONDecodeError:
            log.warning("seen_events.json is corrupt; starting fresh.")
    return {}


def save_seen(seen: dict[str, dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_EVENTS_PATH.write_text(json.dumps(seen, indent=2, ensure_ascii=False))


def mark_seen(seen: dict[str, dict], url: str, status: str, title: str = "") -> None:
    seen[url] = {
        "status": status,
        "title": title,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_seen(seen)


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def is_logged_in(page: Page) -> bool:
    """Heuristic: signed-in users have an account avatar / no 'Sign In' CTA."""
    try:
        page.goto(f"{LUMA_BASE}/home", wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        return False
    page.wait_for_timeout(2000)
    # If a "Sign In" button is visible we are anonymous.
    sign_in = page.get_by_role("link", name="Sign In")
    try:
        if sign_in.first.is_visible(timeout=2000):
            return False
    except PWTimeout:
        pass
    return "signin" not in page.url


def login(context: BrowserContext, cfg: Config) -> None:
    """Perform the passwordless email-code login and persist the session."""
    page = context.new_page()
    log.info("Starting Luma login for %s", cfg.luma_email)
    page.goto(f"{LUMA_BASE}/signin", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1500)

    # 1) Enter email.
    email_box = page.locator("input[type='email'], input[name='email']").first
    email_box.wait_for(state="visible", timeout=20000)
    email_box.fill(cfg.luma_email)

    triggered_at = time.time()
    _click_first(
        page,
        [
            page.get_by_role("button", name="Continue with Email"),
            page.get_by_role("button", name="Continue"),
            page.get_by_role("button", name="Sign In"),
        ],
    )
    page.wait_for_timeout(3000)

    # 2) Read the code from Gmail.
    code = fetch_login_code(
        cfg.gmail_imap_host,
        cfg.gmail_address,
        cfg.gmail_app_password,
        not_before=triggered_at,
        timeout_seconds=150,
    )
    if not code:
        _screenshot(page, "login-no-code")
        raise SystemExit("Could not retrieve login code from email. Aborting.")

    # 3) Enter the code. Luma may render one input or 6 single-digit boxes.
    _enter_code(page, code)
    page.wait_for_timeout(4000)

    # 4) Verify + persist.
    if "signin" in page.url:
        _screenshot(page, "login-failed")
        raise SystemExit("Login appears to have failed after entering code.")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(STORAGE_STATE_PATH))
    log.info("Login successful — session saved to %s", STORAGE_STATE_PATH)
    page.close()


def _enter_code(page: Page, code: str) -> None:
    # Case A: 6 individual boxes.
    boxes = page.locator(
        "input[autocomplete='one-time-code'], input[inputmode='numeric']"
    )
    try:
        count = boxes.count()
    except PWTimeout:
        count = 0

    if count >= 6:
        for i, digit in enumerate(code):
            boxes.nth(i).fill(digit)
        return
    if count == 1:
        boxes.first.fill(code)
    else:
        # Fallback: any visible text/number input.
        page.locator("input").first.fill(code)

    _click_first(
        page,
        [
            page.get_by_role("button", name="Continue"),
            page.get_by_role("button", name="Sign In"),
            page.get_by_role("button", name="Verify"),
        ],
        required=False,
    )


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_event_urls(page: Page, city: str) -> list[str]:
    """Collect event page URLs from a city's discover page."""
    url = f"{LUMA_BASE}/{city.strip('/')}"
    log.info("Scanning discover page: %s", url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except PWTimeout:
        log.warning("Timed out loading %s", url)
        return []

    # Let the client-side event list render, then lazy-load by scrolling.
    page.wait_for_timeout(3000)
    for _ in range(5):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1200)

    hrefs = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => e.getAttribute('href'))",
    )
    urls: list[str] = []
    seen_local: set[str] = set()
    for href in hrefs:
        if not href:
            continue
        # Event pages are short top-level slugs like /abc123 or /e/...
        if not looks_like_event_path(href):
            continue
        full = normalize_event_url(href)
        if full not in seen_local:
            seen_local.add(full)
            urls.append(full)

    log.info("Found %d candidate event link(s) on /%s", len(urls), city)
    return urls


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def register_event(
    page: Page, url: str, cfg: Config, dry_run: bool
) -> tuple[str, str]:
    """Visit an event page and register if it is free. Returns (status, title)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except PWTimeout:
        return "error_load", ""
    page.wait_for_timeout(2500)

    title = (page.title() or "").replace(" · Luma", "").strip()

    # Keyword filter.
    if cfg.keyword_filter:
        body_text = page.inner_text("body").lower()
        if not any(k.lower() in body_text for k in cfg.keyword_filter):
            return "skipped_keyword", title

    # Already registered?
    body_text = page.inner_text("body")
    lowered = body_text.lower()
    if any(
        s in lowered
        for s in ("you're in", "you are in", "registered", "you're going", "manage registration")
    ):
        return "already_registered", title

    # Paid? Skip anything that shows a non-free price.
    if looks_paid(lowered):
        return "skipped_paid", title

    # Find the register / get-ticket button.
    btn = _find_register_button(page)
    if btn is None:
        return "no_register_button", title

    label = (btn.inner_text() or "").strip().lower()
    # Approval-required / waitlist / apply flows: only proceed if opted in.
    is_approval = any(s in label for s in ("request", "waitlist", "apply"))
    if is_approval and not cfg.request_approval_events:
        return "skipped_approval", title

    if dry_run:
        return "dry_run", title

    btn.click()
    page.wait_for_timeout(2500)

    # A registration modal may require filling fields / confirming.
    _confirm_registration(page, cfg)
    page.wait_for_timeout(3000)

    lowered_after = page.inner_text("body").lower()
    if any(
        s in lowered_after
        for s in ("you're in", "you are in", "you're going", "registered", "see you")
    ):
        return "registered", title
    if is_approval and any(
        s in lowered_after
        for s in ("pending", "request sent", "awaiting", "submitted", "review")
    ):
        return "requested_approval", title

    # Couldn't confirm success — capture for debugging but don't crash.
    _screenshot(page, f"register-unconfirmed-{_slug(url)}")
    return "register_unconfirmed", title


def _find_register_button(page: Page):
    candidates = [
        page.get_by_role("button", name="Register"),
        page.get_by_role("button", name="One-Click Register"),
        page.get_by_role("button", name="Get Ticket"),
        page.get_by_role("button", name="Get Tickets"),
        page.get_by_role("button", name="RSVP"),
        page.get_by_role("button", name="Join Event"),
    ]
    for c in candidates:
        try:
            if c.first.is_visible(timeout=1500):
                return c.first
        except PWTimeout:
            continue
    return None


def _confirm_registration(page: Page, cfg: Config) -> None:
    """Fill any required fields, then click through the confirmation modal."""
    # Some events render a registration form (name/email) before confirming.
    try:
        email_field = page.locator("input[type='email']").first
        if email_field.is_visible(timeout=1000) and not (email_field.input_value()):
            email_field.fill(cfg.luma_email)
    except PWTimeout:
        pass

    candidates = [
        page.get_by_role("button", name="Register"),
        page.get_by_role("button", name="One-Click Register"),
        page.get_by_role("button", name="Confirm"),
        page.get_by_role("button", name="Submit"),
        page.get_by_role("button", name="Request to Join"),
        page.get_by_role("button", name="Done"),
    ]
    for c in candidates:
        try:
            if c.first.is_visible(timeout=1500):
                c.first.click()
                page.wait_for_timeout(1500)
        except PWTimeout:
            continue


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _click_first(page: Page, locators, required: bool = True) -> None:
    for loc in locators:
        try:
            if loc.first.is_visible(timeout=2000):
                loc.first.click()
                return
        except PWTimeout:
            continue
    if required:
        # Fall back to pressing Enter on the focused field.
        page.keyboard.press("Enter")


def _screenshot(page: Page, name: str) -> None:
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}-{int(time.time())}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info("Saved screenshot: %s", path)
    except Exception:  # noqa: BLE001
        pass


def _slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1][:40]


# A realistic desktop fingerprint to reduce anti-bot friction.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _context_options() -> dict:
    return {
        "user_agent": USER_AGENT,
        "viewport": {"width": 1440, "height": 900},
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_scan(cfg: Config, dry_run: bool) -> dict[str, int]:
    seen = load_seen()
    tally: dict[str, int] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless)
        storage = (
            str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None
        )
        context = browser.new_context(storage_state=storage, **_context_options())
        page = context.new_page()

        if not is_logged_in(page):
            log.info("Not logged in — establishing session.")
            login(context, cfg)
            page = context.new_page()

        # Build the work list: public city-discover events + private/invited
        # events pulled from Luma invitation emails in the inbox.
        sources: list[tuple[str, list[str]]] = []
        for city in cfg.cities:
            sources.append((f"discover:{city}", discover_event_urls(page, city)))
        if cfg.scan_inbox_invites:
            invite_urls = scan_invite_urls(
                cfg.gmail_imap_host,
                cfg.gmail_address,
                cfg.gmail_app_password,
                lookback_days=cfg.invite_lookback_days,
            )
            sources.append(("inbox-invites", invite_urls))

        discovered = sum(len(urls) for _, urls in sources)
        registered_this_run = 0
        for source_name, urls in sources:
            log.info("Processing %d event(s) from %s", len(urls), source_name)
            for url in urls:
                if url in seen:
                    continue
                if registered_this_run >= cfg.max_registrations_per_run:
                    log.info("Hit per-run registration cap; stopping.")
                    break

                status, title = register_event(page, url, cfg, dry_run)
                tally[status] = tally.get(status, 0) + 1
                mark_seen(seen, url, status, title)

                emoji = {
                    "registered": "✅",
                    "dry_run": "🔎",
                    "already_registered": "↩️",
                    "skipped_paid": "💵",
                    "skipped_approval": "🔒",
                    "skipped_keyword": "🚫",
                }.get(status, "•")
                log.info("%s [%s] %s — %s", emoji, status, title or "(untitled)", url)

                if status == "registered":
                    registered_this_run += 1
                page.wait_for_timeout(1500)
            else:
                continue
            break  # inner loop hit the cap; stop processing further sources

        context.close()
        browser.close()

    # Update cumulative stats and emit a report in the cronjob's style.
    stats = Stats(STATS_PATH)
    if not dry_run:
        stats.apply(tally)
    pending_remaining = tally.get("requested_approval", 0)
    report = format_report(
        tally,
        stats,
        discovered=discovered,
        pending_remaining=pending_remaining,
        dry_run=dry_run,
    )
    log.info("Scan complete:\n%s", report)
    send_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, report)
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description="Luma auto-register")
    parser.add_argument("--loop", action="store_true", help="run forever on an interval")
    parser.add_argument(
        "--dry-run", action="store_true", help="find + log, never click Register"
    )
    parser.add_argument(
        "--login", action="store_true", help="just establish/refresh the session"
    )
    args = parser.parse_args()

    cfg = Config.load()

    if args.login:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            context = browser.new_context(**_context_options())
            login(context, cfg)
            context.close()
            browser.close()
        return 0

    if args.loop:
        log.info("Loop mode: scanning every %d min.", cfg.poll_interval_minutes)
        while True:
            try:
                run_scan(cfg, args.dry_run)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("Scan failed: %s", exc)
            time.sleep(cfg.poll_interval_minutes * 60)

    run_scan(cfg, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
