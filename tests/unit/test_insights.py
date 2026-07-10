"""Unit tests for dashboard/data/insights.py's severity/category/confidence
tagging (roadmap §15 unit #5). insights.py had zero direct tests before
this file -- a pre-existing gap, not backfilled in full here; only the new
severity/category/confidence logic added on top of each finding function is
covered.

The five functions that take a plain moves_df/baseline_blunder_rate (no
duck_conn) are covered with hand-built pandas DataFrames -- no DB fixture
needed. The remaining five (_castling, _nemesis, _giant_killing,
_tactical_highlights, _game_endings) need a real sqlite/duckdb connection;
those get a couple of smoke tests each, reusing this repo's existing
migrated_db fixture + a local DuckDB-attach helper (same pattern as
tests/integration/test_data_layer.py's _duck_from_conn), rather than
building new fixture infrastructure from scratch.
"""
import os
import sqlite3
import tempfile

import pandas as pd
import pytest

from data.insights import (
    _piece_hotspot, _safest_piece, _sharpness, _thinking_time, _time_pressure, _backrank,
    _castling, _nemesis, _best_matchup, _giant_killing, _tactical_highlights, _game_endings,
)


def _duck_from_conn(sqlite_conn):
    """Copy an in-memory/real sqlite connection to a temp file and attach
    it to a fresh DuckDB connection. Returns (duck_conn, disk_conn,
    tmp_path) -- callers must close both and delete the temp file. Mirrors
    tests/integration/test_data_layer.py's helper of the same name."""
    import duckdb
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in sqlite_conn.iterdump():
        try:
            disk.execute(line)
        except Exception:
            pass
    disk.commit()
    duck = duckdb.connect(":memory:")
    duck.execute(f"ATTACH '{tmp.name}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
    return duck, disk, tmp.name


# ---------------------------------------------------------------------------
# Plain pandas findings -- no DB needed.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPieceHotspot:
    def _df(self, n_blunders_a, n_blunders_b, n=20):
        rows = []
        for i in range(n):
            rows.append({"piece": "N", "cpl": 10.0,
                         "classification": "blunder" if i < n_blunders_a else "good"})
        for i in range(n):
            rows.append({"piece": "B", "cpl": 10.0,
                         "classification": "blunder" if i < n_blunders_b else "good"})
        return pd.DataFrame(rows)

    def test_category_is_tactical(self):
        result = _piece_hotspot(self._df(10, 2), baseline_blunder_rate=20.0)
        assert result["category"] == "tactical"

    def test_high_severity_for_large_ratio(self):
        # N: 10/20 = 50% blunder rate, vs. baseline 20% -> ratio 2.5 (>= high cutoff).
        result = _piece_hotspot(self._df(10, 2), baseline_blunder_rate=20.0)
        assert result["severity"] == "high"

    def test_low_severity_for_small_ratio(self):
        # N: 5/20 = 25% blunder rate, vs. baseline 20% -> ratio 1.25 (< medium cutoff).
        result = _piece_hotspot(self._df(5, 2), baseline_blunder_rate=20.0)
        assert result["severity"] == "low"

    def test_polarity_is_weakness(self):
        result = _piece_hotspot(self._df(10, 2), baseline_blunder_rate=20.0)
        assert result["polarity"] == "weakness"


@pytest.mark.unit
class TestSafestPiece:
    """Mirrors TestPieceHotspot's fixture-building approach, but the finding
    picks the piece with the LOWEST blunder rate instead of the highest."""
    def _df(self, n_blunders_a, n_blunders_b, n=20):
        rows = []
        for i in range(n):
            rows.append({"piece": "N", "cpl": 10.0,
                         "classification": "blunder" if i < n_blunders_a else "good"})
        for i in range(n):
            rows.append({"piece": "B", "cpl": 10.0,
                         "classification": "blunder" if i < n_blunders_b else "good"})
        return pd.DataFrame(rows)

    def test_category_is_tactical(self):
        result = _safest_piece(self._df(10, 2), baseline_blunder_rate=20.0)
        assert result["category"] == "tactical"

    def test_polarity_is_strength(self):
        result = _safest_piece(self._df(10, 2), baseline_blunder_rate=20.0)
        assert result["polarity"] == "strength"

    def test_high_severity_for_large_inverse_ratio(self):
        # B: 2/20 = 10% blunder rate, baseline 20% -> inverse ratio 2.0 (< high cutoff 2.5,
        # >= medium cutoff 1.5) -> "medium". Use a lower blunder rate for "high".
        # B: 1/20 = 5% blunder rate, baseline 20% -> inverse ratio 4.0 (>= high cutoff).
        result = _safest_piece(self._df(10, 1), baseline_blunder_rate=20.0)
        assert result["severity"] == "high"
        assert result["headline"].startswith("Bishop moves blunder at only 5.0%")


@pytest.mark.unit
class TestSharpness:
    def _df(self, n_flat_blunders, n_forcing_blunders, n=40):
        rows = []
        for i in range(n):
            rows.append({"sharpness": 2.0, "cpl": 10.0,
                         "classification": "blunder" if i < n_flat_blunders else "good"})
        for i in range(n):
            rows.append({"sharpness": 250.0, "cpl": 10.0,
                         "classification": "blunder" if i < n_forcing_blunders else "good"})
        return pd.DataFrame(rows)

    def test_category_is_tactical(self):
        result = _sharpness(self._df(1, 10))
        assert result["category"] == "tactical"

    def test_high_severity_for_large_gap(self):
        # flat 1/40=2.5%, forcing 15/40=37.5% -> gap 35pp (>= high cutoff 10).
        result = _sharpness(self._df(1, 15))
        assert result["severity"] == "high"

    def test_low_severity_for_small_gap(self):
        # flat 0/40=0%, forcing 1/40=2.5% -> gap 2.5pp (< medium cutoff 5).
        result = _sharpness(self._df(0, 1))
        assert result["severity"] == "low"

    def test_climbing_blunder_rate_is_weakness(self):
        # flat 1/40=2.5%, forcing 15/40=37.5% -> delta +35pp (climbs) -> weakness.
        result = _sharpness(self._df(1, 15))
        assert result["polarity"] == "weakness"
        assert "climbs" in result["headline"]

    def test_falling_blunder_rate_is_strength(self):
        # flat 15/40=37.5%, forcing 1/40=2.5% -> delta -35pp (falls) -> strength.
        result = _sharpness(self._df(15, 1))
        assert result["polarity"] == "strength"
        assert result["severity"] == "high"
        assert "holds steady or falls" in result["headline"]


@pytest.mark.unit
class TestThinkingTime:
    def _df(self, n_instant_blunders, n_considered_blunders, n=20):
        rows = []
        for i in range(n):
            rows.append({"time_spent_seconds": 0.5, "cpl": 10.0,
                         "classification": "blunder" if i < n_instant_blunders else "good"})
        for i in range(n):
            rows.append({"time_spent_seconds": 5.0, "cpl": 10.0,
                         "classification": "blunder" if i < n_considered_blunders else "good"})
        return pd.DataFrame(rows)

    def test_category_is_time(self):
        result = _thinking_time(self._df(10, 1))
        assert result["category"] == "time"

    def test_high_severity_for_large_gap(self):
        # instant 10/20=50%, considered 1/20=5% -> gap 45pp.
        result = _thinking_time(self._df(10, 1))
        assert result["severity"] == "high"

    def test_low_severity_for_small_gap(self):
        # instant 1/20=5%, considered 0/20=0% -> gap 5... use finer split.
        result = _thinking_time(self._df(1, 0, n=40))
        assert result["severity"] == "low"

    def test_polarity_is_mixed(self):
        result = _thinking_time(self._df(10, 1))
        assert result["polarity"] == "mixed"


@pytest.mark.unit
class TestTimePressure:
    def _df(self, n_critical_blunders, n_plenty_blunders, n=20):
        rows = []
        for i in range(n):
            # clock_seconds/base_seconds ~ 3.3% -> "critical (<5%)" bucket.
            rows.append({"clock_seconds": 10.0, "base_seconds": 300.0, "cpl": 10.0,
                         "classification": "blunder" if i < n_critical_blunders else "good"})
        for i in range(n):
            # ~66.7% -> "plenty (60-100%)" bucket.
            rows.append({"clock_seconds": 200.0, "base_seconds": 300.0, "cpl": 10.0,
                         "classification": "blunder" if i < n_plenty_blunders else "good"})
        return pd.DataFrame(rows)

    def test_category_is_time(self):
        result = _time_pressure(self._df(10, 1))
        assert result["category"] == "time"

    def test_high_severity_for_large_gap(self):
        # critical 10/20=50%, plenty 1/20=5% -> gap 45pp.
        result = _time_pressure(self._df(10, 1))
        assert result["severity"] == "high"

    def test_low_severity_for_small_gap(self):
        # finer split: critical 1/40=2.5%, plenty 0/40=0% -> gap 2.5pp.
        result = _time_pressure(self._df(1, 0, n=40))
        assert result["severity"] == "low"

    def test_polarity_is_mixed(self):
        result = _time_pressure(self._df(10, 1))
        assert result["polarity"] == "mixed"


@pytest.mark.unit
class TestBackrank:
    def _df(self, back_cpl, elsewhere_cpl, n=20):
        rows = []
        for _ in range(n):
            rows.append({"piece": "K", "to_square": "e1", "color": "w", "cpl": back_cpl})
        for _ in range(n):
            rows.append({"piece": "K", "to_square": "e4", "color": "w", "cpl": elsewhere_cpl})
        return pd.DataFrame(rows)

    def test_category_is_defense(self):
        result = _backrank(self._df(5.0, 30.0))
        assert result["category"] == "defense"

    def test_high_severity_for_large_gap(self):
        # back ACPL 5, elsewhere ACPL 30 -> gap 25 (>= high cutoff 20).
        result = _backrank(self._df(5.0, 30.0))
        assert result["severity"] == "high"

    def test_low_severity_for_small_gap(self):
        # back ACPL 10, elsewhere ACPL 15 -> gap 5 (< medium cutoff 10).
        result = _backrank(self._df(10.0, 15.0))
        assert result["severity"] == "low"

    def test_worse_elsewhere_is_weakness(self):
        # elsewhere ACPL (30) > back ACPL (5) -- the typical/expected pattern
        # (king play degrades away from the back rank) -> weakness.
        result = _backrank(self._df(5.0, 30.0))
        assert result["polarity"] == "weakness"

    def test_worse_on_back_rank_is_strength(self):
        # back ACPL (30) > elsewhere ACPL (5) -- king play is actually worse
        # ON the back rank here, so being active elsewhere is the strength.
        result = _backrank(self._df(30.0, 5.0))
        assert result["polarity"] == "strength"


# ---------------------------------------------------------------------------
# DB-backed findings -- smoke tests only (existing new-key shape, not a
# full re-derivation of each function's own correctness, which the
# pre-existing integration tests for patterns.py/matchups.py/game_endings.py
# already cover indirectly).
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCastlingSmoke:
    def _seed(self, conn, game_id, player_color, castled, outcome, num_plies=40):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color, num_plies) "
            "VALUES (?, 'W', 'B', ?, ?, ?)",
            (game_id, outcome, player_color, num_plies))
        move_color = "w" if player_color == "white" else "b"
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, is_player_move) "
            "VALUES (?, 1, 1, ?, 'O-O', ?, 1)",
            (game_id, move_color, 1 if castled else 0))

    def test_new_keys_present_with_expected_shape(self, migrated_db):
        for i in range(5):
            # All castled games win; all non-castled games lose -> a
            # large, unambiguous win-rate gap (severity should read "high").
            self._seed(migrated_db, f"c{i}", "white", castled=True, outcome="win")
            self._seed(migrated_db, f"n{i}", "white", castled=False, outcome="loss")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _castling(duck)
            assert result is not None
            assert result["category"] == "defense"
            assert result["severity"] == "high"
            assert result["confidence"] in ("low", "medium", "high")
            # All castled games win, all non-castled games lose -> castled
            # win_pct (100%) >= not_castled win_pct (0%) -> strength.
            assert result["polarity"] == "strength"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestNemesisSmoke:
    def test_new_keys_present_with_expected_shape(self, migrated_db):
        # 5 losses, no rating_diff recorded at all -> falls back to the
        # raw-score_pct severity branch (score_pct=0 -> max(0, 50-0)=50,
        # which lands in the fallback thresholds' "high" tier).
        for i in range(5):
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, outcome_for_player) "
                "VALUES (?, 'W', 'B', 'Nemesis', 'loss')", (f"g{i}",))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _nemesis(duck)
            assert result is not None
            assert result["category"] == "matchup"
            assert result["severity"] == "high"
            assert result["confidence"] in ("low", "medium", "high")
            assert result["polarity"] == "weakness"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestBestMatchup:
    """Mirrors TestNemesisSmoke's fixture-building approach, but the finding
    picks the opponent with the HIGHEST surprise_pct instead of the lowest."""
    def test_new_keys_present_with_expected_shape(self, migrated_db):
        # 5 wins, no rating_diff recorded at all -> falls back to the
        # raw-score_pct severity branch (score_pct=100 -> max(0, 100-50)=50,
        # which lands in the fallback thresholds' "high" tier).
        for i in range(5):
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, outcome_for_player) "
                "VALUES (?, 'W', 'B', 'Pushover', 'win')", (f"g{i}",))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _best_matchup(duck)
            assert result is not None
            assert result["category"] == "matchup"
            assert result["severity"] == "high"
            assert result["polarity"] == "strength"
            assert result["confidence"] in ("low", "medium", "high")
            assert "Pushover" in result["headline"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestGiantKillingSmoke:
    def test_new_keys_present_and_no_confidence_key(self, migrated_db):
        # 4 games as a 300+ favorite, 1 of them a collapse -> 25% collapse
        # rate, right at the "high" cutoff.
        for i in range(3):
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, rating_diff) "
                "VALUES (?, 'W', 'B', 'win', 350)", (f"fav_win{i}",))
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, rating_diff) "
            "VALUES ('fav_collapse', 'W', 'B', 'loss', 350)")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _giant_killing(duck)
            assert result is not None
            assert result["category"] == "giant_killer"
            assert result["severity"] == "high"
            assert "confidence" not in result
            assert result["polarity"] == "mixed"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestGameEndingsSmoke:
    def test_literal_low_severity_and_no_confidence_key(self, migrated_db):
        migrated_db.execute(
            "INSERT INTO games (id, white, black, game_end_type) VALUES ('g1', 'W', 'B', 'checkmate')")
        migrated_db.execute(
            "INSERT INTO games (id, white, black, game_end_type) VALUES ('g2', 'W', 'B', 'resignation')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _game_endings(duck)
            assert result is not None
            assert result["category"] == "general"
            assert result["severity"] == "low"
            assert "confidence" not in result
            assert result["polarity"] == "neutral"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestTacticalHighlightsSmoke:
    def test_literal_low_severity_and_no_confidence_key(self, migrated_db):
        moves_df = pd.DataFrame({
            "is_brilliant_candidate": [True],
            "eval_mate": [None],
            "best_move_san": [None],
            "san": [None],
            "outcome_for_player": ["win"],
        })
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = _tactical_highlights(duck, moves_df)
            assert result is not None
            assert result["category"] == "tactical"
            assert result["severity"] == "low"
            assert "confidence" not in result
            assert result["polarity"] == "neutral"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
