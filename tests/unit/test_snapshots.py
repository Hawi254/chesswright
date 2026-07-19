"""Unit tests for snapshots.py's pure formula helpers. The DB-backed
record_snapshot() itself is covered in tests/integration/test_snapshots.py
-- this file covers only the no-DB pieces, same split as
tests/unit/test_shared.py vs. the DB-backed get_headline_stats coverage
it explicitly defers elsewhere.
"""
import datetime
import sqlite3

import pytest

from snapshots import (
    MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING,
    _confidence_tier,
    _default_thresholds,
    _estimate_rating_from_acpl,
    get_headline_trend,
)


@pytest.mark.unit
class TestEstimateRatingFromAcpl:
    def test_zero_acpl_gives_formula_ceiling(self):
        # ELO ~= 3100 * e^(-0.01 * 0) = 3100 exactly. Same formula/values
        # as dashboard/data/_shared.py's estimate_rating_from_acpl --
        # duplicated, not imported, see snapshots.py's module docstring.
        assert _estimate_rating_from_acpl(0) == 3100

    def test_mid_range_acpl(self):
        # 3100 * e^(-0.01 * 50) = 3100 * e^-0.5 ~= 1880.24 -> rounds to 1880.
        assert _estimate_rating_from_acpl(50) == 1880

    def test_returns_int_not_float(self):
        assert isinstance(_estimate_rating_from_acpl(45.2), int)


@pytest.mark.unit
def test_min_analyzed_moves_threshold_constant():
    assert MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING == 20


@pytest.mark.unit
class TestConfidenceTierHelpers:
    def test_default_thresholds_applies_3x_8x_scheme(self):
        assert _default_thresholds(20) == {"low": 20, "medium": 60, "high": 160}

    def test_confidence_tier_below_low_is_insufficient(self):
        assert _confidence_tier(5, _default_thresholds(20)) == "insufficient"

    def test_confidence_tier_at_each_boundary(self):
        thresholds = _default_thresholds(20)
        assert _confidence_tier(20, thresholds) == "low"
        assert _confidence_tier(60, thresholds) == "medium"
        assert _confidence_tier(160, thresholds) == "high"


def _memory_conn_with_snapshots(rows):
    """rows: list of (snapshot_date, acpl, blunder_rate, win_pct,
    implied_rating) tuples. A bare in-memory table with just the 5
    columns get_headline_trend actually reads -- not the full migrated
    schema -- since this is a pure-logic test, same split test_snapshots.py's
    own docstring already draws between this file and
    tests/integration/test_snapshots.py's DB-backed coverage."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE metric_snapshots (
            snapshot_date TEXT PRIMARY KEY, acpl REAL, blunder_rate REAL,
            win_pct REAL, implied_rating INTEGER
        )
    """)
    conn.executemany(
        "INSERT INTO metric_snapshots "
        "(snapshot_date, acpl, blunder_rate, win_pct, implied_rating) "
        "VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    return conn


@pytest.mark.unit
class TestGetHeadlineTrend:
    def test_no_row_at_or_before_cutoff_returns_all_none(self):
        conn = _memory_conn_with_snapshots([])
        result = get_headline_trend(
            conn, {"acpl": 40.0, "blunder_rate": 5.0, "win_pct": 55.0, "implied_rating": 1900})
        assert result == {
            "compared_to_date": None, "acpl_delta": None, "blunder_rate_delta": None,
            "win_pct_delta": None, "implied_rating_delta": None,
        }

    def test_picks_the_row_closest_to_but_not_after_90_days_ago(self):
        cutoff = datetime.date.today() - datetime.timedelta(days=90)
        too_recent = (cutoff + datetime.timedelta(days=5)).isoformat()  # after cutoff, must be excluded
        exactly_old_enough = (cutoff - datetime.timedelta(days=2)).isoformat()
        older_still = (cutoff - datetime.timedelta(days=30)).isoformat()
        conn = _memory_conn_with_snapshots([
            (too_recent, 60.0, 10.0, 40.0, 1700),
            (exactly_old_enough, 50.0, 8.0, 45.0, 1800),
            (older_still, 45.0, 7.0, 42.0, 1750),
        ])
        result = get_headline_trend(
            conn, {"acpl": 40.0, "blunder_rate": 5.0, "win_pct": 55.0, "implied_rating": 1900})
        assert result["compared_to_date"] == exactly_old_enough
        assert result["acpl_delta"] == pytest.approx(40.0 - 50.0)
        assert result["blunder_rate_delta"] == pytest.approx(5.0 - 8.0)
        assert result["win_pct_delta"] == pytest.approx(55.0 - 45.0)
        assert result["implied_rating_delta"] == 1900 - 1800

    def test_none_current_stat_propagates_to_none_delta(self):
        old_date = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
        conn = _memory_conn_with_snapshots([(old_date, 50.0, 8.0, 45.0, 1800)])
        result = get_headline_trend(
            conn, {"acpl": None, "blunder_rate": 5.0, "win_pct": 55.0, "implied_rating": 1900})
        assert result["acpl_delta"] is None
        assert result["blunder_rate_delta"] == pytest.approx(5.0 - 8.0)

    def test_none_past_stat_propagates_to_none_delta(self):
        old_date = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
        conn = _memory_conn_with_snapshots([(old_date, None, 8.0, 45.0, None)])
        result = get_headline_trend(
            conn, {"acpl": 40.0, "blunder_rate": 5.0, "win_pct": 55.0, "implied_rating": 1900})
        assert result["acpl_delta"] is None
        assert result["implied_rating_delta"] is None
