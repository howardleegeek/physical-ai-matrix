"""Tests for OTP-code and invite-URL parsing (stdlib-only modules)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invite_scanner import EVENT_URL_RE, _NON_EVENT  # noqa: E402
from otp_reader import CODE_RE  # noqa: E402


class TestOtpCodeRegex:
    def test_extracts_six_digits(self):
        assert CODE_RE.search("Your Luma code is 482913.").group(1) == "482913"

    def test_ignores_longer_numbers(self):
        # Should not match inside a 9-digit string.
        assert CODE_RE.search("ref 123456789") is None

    def test_ignores_short_numbers(self):
        assert CODE_RE.search("code 1234") is None

    def test_picks_code_among_text(self):
        body = "Hi,\nEnter 005512 to sign in. Valid 10 min."
        assert CODE_RE.search(body).group(1) == "005512"


class TestInviteUrlRegex:
    def test_extracts_event_slug(self):
        urls = [m.group(1) for m in EVENT_URL_RE.finditer(
            "Join at https://lu.ma/xyz789 today"
        )]
        assert "xyz789" in urls

    def test_non_event_slugs_known(self):
        assert "unsubscribe" in _NON_EVENT
        assert "e" in _NON_EVENT

    def test_multiple_links(self):
        body = "Event https://lu.ma/aaa111 and manage https://lu.ma/settings"
        slugs = {m.group(1) for m in EVENT_URL_RE.finditer(body)}
        assert "aaa111" in slugs
        assert "settings" in slugs  # regex finds it; caller filters via _NON_EVENT
