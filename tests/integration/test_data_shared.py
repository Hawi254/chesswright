"""Integration tests for dashboard/data/_shared.py -- split from
test_data_layer.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.integration
class TestSharedHelpers:
    def test_bucket_acpl_blunder_rate_empty_df(self):
        import pandas as pd
        from data._shared import bucket_acpl_blunder_rate, TIME_PRESSURE_BUCKETS
        df = pd.DataFrame({"clock_fraction": [], "cpl": pd.Series([], dtype=float),
                           "classification": []})
        result = bucket_acpl_blunder_rate(df, "clock_fraction", TIME_PRESSURE_BUCKETS)
        assert len(result) == 0

    def test_bucket_acpl_blunder_rate_computes_correctly(self):
        import pandas as pd
        from data._shared import bucket_acpl_blunder_rate
        buckets = [("low", 0, 0.5), ("high", 0.5, 1.0)]
        df = pd.DataFrame({
            "val": [0.1, 0.2, 0.7, 0.8],
            "cpl": [10.0, 20.0, 50.0, 100.0],
            "classification": ["good", "inaccuracy", "mistake", "blunder"],
        })
        result = bucket_acpl_blunder_rate(df, "val", buckets)
        assert len(result) == 2
        low = result[result.bucket == "low"]
        high = result[result.bucket == "high"]
        assert low.iloc[0]["blunder_rate"] == 0.0
        assert high.iloc[0]["blunder_rate"] == 50.0


