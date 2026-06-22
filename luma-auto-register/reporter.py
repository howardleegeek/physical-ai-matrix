"""Cumulative run stats + run-report formatting (and optional Telegram push).

Mirrors the reporting style of the existing `luma_event_manager` cronjob so the
two systems read the same way:

    Step 1 discovery: ...
    Step 2: ... events pending registration
    Step 3 registration: ... (registered N / pending_approval M)
    Final stats: total_registered=... / pending_approval=... / failed=...
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("luma.report")

# Statuses produced by register_event(), grouped for reporting.
REGISTERED = {"registered"}
PENDING = {"requested_approval"}
FAILED = {"error_load", "register_unconfirmed", "no_register_button"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Stats:
    """Cumulative counters persisted across runs."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {
            "total_registered": 0,
            "pending_approval": 0,
            "failed": 0,
            "runs": 0,
            "last_run": None,
        }
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text()))
            except json.JSONDecodeError:
                log.warning("stats.json corrupt; starting fresh.")

    def apply(self, tally: dict[str, int]) -> None:
        for status, count in tally.items():
            if status in REGISTERED:
                self.data["total_registered"] += count
            elif status in PENDING:
                self.data["pending_approval"] += count
            elif status in FAILED:
                self.data["failed"] += count
        self.data["runs"] += 1
        self.data["last_run"] = _now()
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))


def format_report(
    tally: dict[str, int],
    stats: Stats,
    *,
    discovered: int,
    pending_remaining: int,
    dry_run: bool,
) -> str:
    """Build a human-readable run summary in the cronjob's style."""
    reg = sum(tally.get(s, 0) for s in REGISTERED)
    pend = sum(tally.get(s, 0) for s in PENDING)
    failed = sum(tally.get(s, 0) for s in FAILED)
    attempted = reg + pend + failed

    mode = " (DRY RUN)" if dry_run else ""
    lines = [
        f"Luma minipc1: Event Discovery & Registration{mode}",
        "-------------",
        f"Step 1 discovery: {discovered}",
        f"Step 2: {attempted} events pending registration",
        f"Step 3 registration: {attempted}"
        f"（registered {reg} / pending_approval {pend} / failed {failed}）",
        f"Final stats: total_registered={stats.data['total_registered']} / "
        f"pending_approval={stats.data['pending_approval']} / "
        f"failed={stats.data['failed']}",
        f"Remaining pending for next run: {pending_remaining}",
    ]
    # Add a breakdown of skip reasons if any.
    skips = {k: v for k, v in tally.items() if k.startswith("skipped")}
    if skips:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(skips.items()))
        lines.append(f"Skipped: {detail}")
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    """Best-effort Telegram notification; never raises."""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode()
        with urllib.request.urlopen(url, data=payload, timeout=15) as resp:
            resp.read()
        log.info("Sent Telegram run report.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram notify failed: %s", exc)
