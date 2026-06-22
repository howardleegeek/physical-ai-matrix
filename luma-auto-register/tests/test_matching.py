"""Tests for the pure event-classification helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matching import (  # noqa: E402
    looks_like_event_path,
    looks_paid,
    normalize_event_url,
)


class TestLooksLikeEventPath:
    def test_event_slug_with_digit(self):
        assert looks_like_event_path("/abc123")
        assert looks_like_event_path("https://lu.ma/x9k2p")

    def test_e_prefixed_event(self):
        assert looks_like_event_path("/e/evt-abc123")
        assert looks_like_event_path("https://lu.ma/e/manage")

    def test_city_pages_excluded(self):
        # Pure-letter slugs are city/discover pages, not events.
        assert not looks_like_event_path("/sf")
        assert not looks_like_event_path("/london")
        assert not looks_like_event_path("https://lu.ma/nyc")

    def test_reserved_paths_excluded(self):
        for p in ("/home", "/signin", "/discover", "/settings", "/unsubscribe"):
            assert not looks_like_event_path(p), p

    def test_external_links_excluded(self):
        assert not looks_like_event_path("https://twitter.com/foo123")
        assert not looks_like_event_path("https://example.com/abc1")

    def test_empty_and_root(self):
        assert not looks_like_event_path("/")
        assert not looks_like_event_path("")

    def test_query_and_fragment_stripped(self):
        assert looks_like_event_path("/abc123?ref=home")
        assert looks_like_event_path("/abc123#tickets")


class TestNormalizeEventUrl:
    def test_relative_becomes_absolute(self):
        assert normalize_event_url("/abc123") == "https://lu.ma/abc123"

    def test_strips_query_fragment_trailing_slash(self):
        assert (
            normalize_event_url("https://lu.ma/abc123/?ref=x#y")
            == "https://lu.ma/abc123"
        )


class TestLooksPaid:
    def test_free_anywhere_means_not_paid(self):
        assert not looks_paid("tickets: free")
        assert not looks_paid("general admission free · vip $50")

    def test_nonzero_price_is_paid(self):
        assert looks_paid("ticket price $25")
        assert looks_paid("entry £10 at the door")
        assert looks_paid("cost: €5.00")

    def test_no_price_no_free_is_not_paid(self):
        # One-click register events often show no price and no "free" word.
        assert not looks_paid("register now to join us")

    def test_zero_price_not_paid(self):
        assert not looks_paid("price $0")
