"""Unit tests for dashboard/data/_shared.py's pure functions -- no DB.

_shared.py had no dedicated unit test file before this one; its other
functions (get_cached_narrative, save_narrative, get_headline_stats) are
DB-backed and stay covered via tests/integration/test_api_overview.py.
This file covers only the pure, no-DB estimate_rating_from_acpl formula.
"""
import pytest

from data._shared import (
    MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK,
    estimate_rating_from_acpl,
)


@pytest.mark.unit
class TestEstimateRatingFromAcpl:
    def test_zero_acpl_gives_formula_ceiling(self):
        # ELO ~= 3100 * e^(-0.01 * 0) = 3100 exactly.
        assert estimate_rating_from_acpl(0) == 3100

    def test_mid_range_acpl(self):
        # 3100 * e^(-0.01 * 50) = 3100 * e^-0.5 ~= 1880.24 -> rounds to 1880.
        assert estimate_rating_from_acpl(50) == 1880

    def test_higher_acpl_gives_lower_implied_rating(self):
        # 3100 * e^(-0.01 * 100) = 3100 * e^-1 ~= 1140.35 -> rounds to 1140.
        assert estimate_rating_from_acpl(100) == 1140

    def test_returns_int_not_float(self):
        assert isinstance(estimate_rating_from_acpl(45.2), int)

    def test_monotonically_decreasing_in_acpl(self):
        assert estimate_rating_from_acpl(20) > estimate_rating_from_acpl(80)


@pytest.mark.unit
def test_min_analyzed_moves_threshold_constant():
    # Same cutoff value as insights.py's MIN_BUCKET_MOVES, duplicated
    # locally to avoid a _shared.py -> insights.py -> _shared.py cycle.
    assert MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK == 20
