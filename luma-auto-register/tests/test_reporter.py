"""Tests for cumulative stats and run-report formatting."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reporter import Stats, format_report  # noqa: E402


def test_stats_accumulate(tmp_path):
    path = tmp_path / "stats.json"
    st = Stats(path)
    st.apply({"registered": 3, "requested_approval": 2, "error_load": 1})
    assert st.data["total_registered"] == 3
    assert st.data["pending_approval"] == 2
    assert st.data["failed"] == 1
    assert st.data["runs"] == 1

    # A second run accumulates and persists.
    st.apply({"registered": 2})
    assert st.data["total_registered"] == 5
    assert st.data["runs"] == 2

    reloaded = Stats(path)
    assert reloaded.data["total_registered"] == 5
    assert reloaded.data["runs"] == 2


def test_report_contains_cronjob_fields(tmp_path):
    st = Stats(tmp_path / "stats.json")
    tally = {"registered": 3, "requested_approval": 5, "skipped_paid": 2}
    st.apply(tally)
    report = format_report(
        tally, st, discovered=12, pending_remaining=5, dry_run=False
    )
    assert "Step 1 discovery: 12" in report
    assert "registered 3" in report
    assert "pending_approval 5" in report
    assert "total_registered=3" in report
    assert "Remaining pending for next run: 5" in report
    assert "skipped_paid=2" in report


def test_dry_run_marker(tmp_path):
    st = Stats(tmp_path / "stats.json")
    report = format_report({}, st, discovered=0, pending_remaining=0, dry_run=True)
    assert "DRY RUN" in report
