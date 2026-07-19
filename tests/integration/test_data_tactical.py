"""Integration tests for dashboard/data/tactical.py -- split from
test_data_layer.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _duck_from_conn

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.integration
class TestTacticalData:
    def test_get_motif_breakdown_on_empty_db(self, migrated_db):
        # takes sqlite_conn since migration 0031 (partial motif index)
        from data.tactical import get_motif_breakdown
        df = get_motif_breakdown(migrated_db)
        assert df is not None

    def test_get_brilliant_candidates_on_empty_db(self, migrated_db):
        from data.tactical import get_brilliant_candidates
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_brilliant_candidates(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


