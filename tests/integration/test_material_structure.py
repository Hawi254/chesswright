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
import pathlib
import sys

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


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
