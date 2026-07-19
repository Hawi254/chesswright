"""
Integration/unit tests for the Material Structure Explorer Tier 1 taxonomy
(roadmap §17 Q1 / §18): data/_shared.py's _classify_endgame_type (promoted
from game_endings.py) and _classify_middlegame_trade_tier (new), plus
data/patterns.py's get_material_structure_bucket_table.

Deliberately a NEW file, not added to tests/integration/test_data_layer.py --
that file has pending, uncommitted, reviewed changes from the same-day
Opponent Profile Analysis unit and was explicitly off-limits for this
session's edits.
"""
import os
import pathlib
import sqlite3
import sys
import tempfile

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _duck_from_conn(sqlite_conn):
    """Copy an in-memory/real sqlite connection to a temp file and attach
    it to a fresh DuckDB connection. Returns (duck_conn, disk_conn,
    tmp_path) -- callers must close both and delete the temp file. Mirrors
    tests/integration/test_data_layer.py's / tests/unit/test_insights.py's
    helper of the same name -- this file had no duck_conn need before
    get_bishop_color_ending_performance."""
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


class TestClassifyEndgameType:
    def test_queen_present(self):
        from data._shared import _classify_endgame_type
        assert _classify_endgame_type("Q1R1B1P6vQ1R1B1P6") == "Queen"

    def test_rook_no_queen(self):
        from data._shared import _classify_endgame_type
        assert _classify_endgame_type("R1P5vP4") == "Rook"

    def test_minor_piece_only(self):
        from data._shared import _classify_endgame_type
        assert _classify_endgame_type("B1N1P4vN2P3") == "Minor piece"

    def test_king_and_pawn_only(self):
        from data._shared import _classify_endgame_type
        assert _classify_endgame_type("P4vP3") == "King & pawn"

    def test_empty_sig_returns_none(self):
        from data._shared import _classify_endgame_type
        assert _classify_endgame_type("") is None
        assert _classify_endgame_type(None) is None


class TestClassifyMiddlegameTradeTier:
    def test_full_complement_is_no_trades(self):
        from data._shared import _classify_middlegame_trade_tier
        # 2*(1Q+2R+2B+2N) = 14 non-pawn pieces combined -- nothing captured yet.
        assert _classify_middlegame_trade_tier("Q1R2B2N2P7vQ1R2B2N2P7") == "No trades"

    def test_one_symmetric_pair_traded_is_light(self):
        from data._shared import _classify_middlegame_trade_tier
        # 12 combined (one minor piece each side already off).
        assert _classify_middlegame_trade_tier("Q1R2B1N2P7vQ1R2B2N1P7") == "Light trades"

    def test_moderate_trades(self):
        from data._shared import _classify_middlegame_trade_tier
        # 10 combined.
        assert _classify_middlegame_trade_tier("Q1R2B1N1P7vQ1R1B1N1P7") == "Moderate trades"

    def test_heavy_trades(self):
        from data._shared import _classify_middlegame_trade_tier
        # 6 combined.
        assert _classify_middlegame_trade_tier("R1B1P6vR1B1P6") == "Heavy trades"

    def test_empty_sig_returns_none(self):
        from data._shared import _classify_middlegame_trade_tier
        assert _classify_middlegame_trade_tier("") is None
        assert _classify_middlegame_trade_tier(None) is None


@pytest.mark.integration
class TestMaterialStructureBucketTable:
    def test_on_empty_db(self, migrated_db):
        from data.patterns import get_material_structure_bucket_table
        df = get_material_structure_bucket_table(migrated_db, structure_type="endgame")
        assert df is not None
        assert len(df) == 0

    def _seed_game(self, conn, game_id, player_color, outcome, ply, material_sig,
                    cpl=None, classification=None):
        """One game, one moves row -- material_sig at `ply` doubles as both
        the checkpoint (middlegame_ply=24 by default) and the sole ACPL
        candidate (is_player_move=1) for that ply, same minimal-fixture
        shape as test_data_layer.py's _seed_time_forfeit_game."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
            "VALUES (?, 'W', 'B', ?, ?)",
            (game_id, outcome, player_color))
        move_color = "w" if player_color == "white" else "b"
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, material_sig, "
            "is_player_move, cpl, classification) VALUES (?, ?, ?, ?, 'e5', ?, 1, ?, ?)",
            (game_id, ply, (ply + 1) // 2, move_color, material_sig, cpl, classification))
        conn.commit()

    def test_endgame_buckets_by_broad_type(self, migrated_db):
        """endgame_max_pieces=6 (default) -- each sig below already
        qualifies as 'reached an endgame' at its own ply, and the FIRST
        (only) such row per game becomes that game's endgame_sig."""
        from data.patterns import get_material_structure_bucket_table
        self._seed_game(migrated_db, "g1", "white", "win", 40, "Q1P4vP4", cpl=10, classification="good")
        self._seed_game(migrated_db, "g2", "white", "loss", 40, "R1P4vP4", cpl=200, classification="blunder")
        self._seed_game(migrated_db, "g3", "white", "draw", 40, "B1P4vP4", cpl=None, classification=None)
        df = get_material_structure_bucket_table(migrated_db, structure_type="endgame")
        lookup = dict(zip(df.bucket, df.n_games))
        assert lookup["Queen"] == 1
        assert lookup["Rook"] == 1
        assert lookup["Minor piece"] == 1
        win_row = df[df.bucket == "Queen"].iloc[0]
        assert win_row.win_pct == pytest.approx(100.0)
        assert win_row.acpl == pytest.approx(10.0)
        assert win_row.n_analyzed == 1
        # g3's move has no cpl -- Minor piece's ACPL must be NaN (Convention
        # #3), not a crash or a silent 0.
        minor_row = df[df.bucket == "Minor piece"].iloc[0]
        assert pd.isna(minor_row.acpl)
        assert minor_row.n_analyzed == 0

    def test_middlegame_buckets_by_trade_tier(self, migrated_db):
        """Seeds moves at ply=24 (the default middlegame_ply checkpoint) --
        material_sig there decides the trade tier, independent of any
        endgame_sig for the same game (none reached here: non_pawn count
        stays well above endgame_max_pieces=6 for all three)."""
        from data.patterns import get_material_structure_bucket_table
        self._seed_game(migrated_db, "g1", "white", "win", 24,
                         "Q1R2B2N2P7vQ1R2B2N2P7", cpl=5, classification="good")   # 14 -> No trades
        self._seed_game(migrated_db, "g2", "white", "loss", 24,
                         "Q1R2B1N2P7vQ1R2B2N1P7", cpl=150, classification="mistake")  # 12 -> Light trades
        df = get_material_structure_bucket_table(migrated_db, structure_type="middlegame")
        lookup = dict(zip(df.bucket, df.n_games))
        assert lookup["No trades"] == 1
        assert lookup["Light trades"] == 1
        no_trades_row = df[df.bucket == "No trades"].iloc[0]
        assert no_trades_row.win_pct == pytest.approx(100.0)
        assert no_trades_row.acpl == pytest.approx(5.0)

    def test_player_relative_orientation(self, migrated_db):
        """A Black player's endgame_sig must be classified from Black's own
        side of the signature (analytics.player_relative_sig's job, run
        before classification) -- the exact sign/side bug
        test_get_time_forfeit_loss_breakdown_black_player_orientation
        already guards for on a sibling query."""
        from data.patterns import get_material_structure_bucket_table
        # Raw (White-first) signature has White down to bare king+pawns and
        # Black holding the queen. From Black's own perspective (the
        # player here), that's "Queen" -- the same reorientation
        # analytics.player_relative_sig performs for compute_structure_context.
        self._seed_game(migrated_db, "g1", "black", "win", 40, "P4vQ1P4", cpl=5, classification="good")
        df = get_material_structure_bucket_table(migrated_db, structure_type="endgame")
        lookup = dict(zip(df.bucket, df.n_games))
        assert lookup.get("Queen") == 1
        assert "King & pawn" not in lookup


@pytest.mark.integration
class TestBishopColorEndingPerformance:
    """Covers data.patterns.get_bishop_color_ending_performance directly
    (roadmap §22) -- the raw bucket/n_moves/acpl extraction shared with
    insights.py's _bishop_color_endings finding. Reuses
    TestBishopColorEndingsSmoke's exact _SAME_FEN/_OPPOSITE_FEN
    (tests/unit/test_insights.py:427-450) and _seed_game shape rather than
    deriving new bishop-square-color FENs, adapted to this file's own
    migrated_db + _duck_from_conn fixtures (get_bishop_color_ending_
    performance needs BOTH connections, unlike get_material_structure_
    bucket_table above)."""

    # White bishop c1 (file 2, rank 1, sum=3, odd) same-parity with Black
    # bishop f8 (file 5, rank 8, sum=13, odd) -> "same".
    _SAME_FEN = "4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1"
    # White bishop c1 (odd) vs. Black bishop c8 (file 2, rank 8, sum=10,
    # even) -> "opposite".
    _OPPOSITE_FEN = "2bk4/8/8/8/8/8/8/2B1K3 w - - 0 1"

    def _seed_bishop_game(self, conn, game_id, fen, cpl):
        """Mirrors TestBishopColorEndingsSmoke._seed_game -- ply 41 carries
        both material_sig (so compute_structure_context detects it as the
        endgame checkpoint, non_pawn_piece_count("B1vB1")=2 <=
        endgame_max_pieces=6) and fen_before (for the bishop-color
        classifier); plies 41-45 all carry cpl so there are enough
        analyzed moves (5/game) to clear MIN_BISHOP_ENDING_MOVES=20 across
        5 games per bucket."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
            "VALUES (?, 'W', 'B', 'win', 'white')", (game_id,))
        for i, ply in enumerate(range(41, 46)):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
                "cpl, material_sig, fen_before) VALUES (?, ?, ?, 'w', 'Kf2', 1, ?, ?, ?)",
                (game_id, ply, 21 + i, cpl,
                 "B1vB1" if ply == 41 else None,
                 fen if ply == 41 else None))
        conn.commit()

    def test_on_empty_db(self, migrated_db):
        from data.patterns import get_bishop_color_ending_performance
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_bishop_color_ending_performance(duck, migrated_db)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_seeded_two_buckets_have_real_acpl(self, migrated_db):
        from data.patterns import get_bishop_color_ending_performance
        for i in range(5):
            self._seed_bishop_game(migrated_db, f"same{i}", self._SAME_FEN, cpl=20)
            self._seed_bishop_game(migrated_db, f"opp{i}", self._OPPOSITE_FEN, cpl=100)
        # analytics.ensure_structure_ctx runs inside
        # get_bishop_color_ending_performance itself, but it must run on
        # the LIVE sqlite connection BEFORE _duck_from_conn snapshots the
        # file, or the DuckDB-attached copy won't see the
        # structure_ctx_cache rows -- same ordering hazard
        # TestBishopColorEndingsSmoke's class docstring documents.
        import analytics
        from _common import get_config
        analytics.ensure_structure_ctx(migrated_db, get_config())

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_bishop_color_ending_performance(duck, migrated_db)
            assert set(df.bucket) == {"same", "opposite"}
            same_row = df[df.bucket == "same"].iloc[0]
            opp_row = df[df.bucket == "opposite"].iloc[0]
            assert same_row.n_moves == 25
            assert opp_row.n_moves == 25
            assert same_row.acpl == pytest.approx(20.0)
            assert opp_row.acpl == pytest.approx(100.0)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
