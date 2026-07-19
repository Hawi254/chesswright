"""Integration tests for the Patterns & Tendencies positions endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

_SAME_BISHOP_FEN = "4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1"
_OPPOSITE_BISHOP_FEN = "2bk4/8/8/8/8/8/8/2B1K3 w - - 0 1"
# French Advance shape (closed center) and a bare-kings position (fully
# open) -- same FENs tests/integration/test_data_layer.py's
# TestPositionCharacterData already validated for chess_utils.classify_
# position_character at the real config's middlegame_ply=24 checkpoint.
_CLOSED_FEN = "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"
_OPEN_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def _seed_structure_game(db_path, game_id, outcome, ply, material_sig,
                          cpl=None, classification=None, player_color="white"):
    """Mirrors tests/integration/test_material_structure.py's
    TestMaterialStructureBucketTable._seed_game -- one games row + one
    moves row carrying material_sig at `ply`, doubling as both the
    structure_ctx checkpoint and the sole ACPL candidate."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
        "VALUES (?, 'W', 'B', ?, ?)", (game_id, outcome, player_color))
    move_color = "w" if player_color == "white" else "b"
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, material_sig, "
        "is_player_move, cpl, classification) VALUES (?, ?, ?, ?, 'e5', ?, 1, ?, ?)",
        (game_id, ply, (ply + 1) // 2, move_color, material_sig, cpl, classification))
    conn.commit()
    conn.close()


def _seed_bishop_game(db_path, game_id, fen, cpl):
    """Mirrors test_material_structure.py's TestBishopColorEndingPerformance.
    _seed_bishop_game -- ply 41 carries material_sig="B1vB1" (non_pawn_
    piece_count=2 <= endgame_max_pieces=6, so compute_structure_context
    detects it as the endgame checkpoint) and fen_before (for the bishop-
    color classifier); plies 41-45 all carry cpl so 5 analyzed moves/game
    clear MIN_BISHOP_ENDING_MOVES=20 across 5 games per bucket."""
    conn = sqlite3.connect(db_path)
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
    conn.close()


def _seed_checkpoint_game(db_path, game_id, outcome, fen_at_checkpoint):
    """Mirrors test_data_layer.py's TestPositionCharacterData.
    _seed_checkpoint_game -- one move at ply=24 (the real config.yaml's
    middlegame_ply) carrying fen_before."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
        "VALUES (?, 'W', 'B', ?, 'white')", (game_id, outcome))
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before) "
        "VALUES (?, 24, 12, 'w', 'Nf3', ?)", (game_id, fen_at_checkpoint))
    conn.commit()
    conn.close()


def _seed_castle_game(db_path, game_id, outcome, white_castle_to, black_castle_to,
                       q_caps=0, k_caps=0):
    """Mirrors test_data_layer.py's TestPositionCharacterData._seed_castle_game."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
        "VALUES (?, 'W', 'B', ?, 'white')", (game_id, outcome))
    ply = 1
    if white_castle_to:
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
            "VALUES (?, ?, ?, 'w', 'O-O', 1, ?)", (game_id, ply, (ply + 1) // 2, white_castle_to))
        ply += 1
    if black_castle_to:
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
            "VALUES (?, ?, ?, 'b', 'O-O', 1, ?)", (game_id, ply, (ply + 1) // 2, black_castle_to))
        ply += 1
    for _ in range(q_caps):
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square) "
            "VALUES (?, ?, ?, 'w', 'Nxc6', 1, 'c6')", (game_id, ply, (ply + 1) // 2))
        ply += 1
    for _ in range(k_caps):
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square) "
            "VALUES (?, ?, ?, 'w', 'Nxf6', 1, 'f6')", (game_id, ply, (ply + 1) // 2))
        ply += 1
    if not white_castle_to and not black_castle_to and q_caps == 0 and k_caps == 0:
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san) "
            "VALUES (?, 1, 1, 'w', 'a4')", (game_id,))
    conn.commit()
    conn.close()




@pytest.mark.integration
class TestPatternsPositions:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/positions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sharpness"] == []
        assert body["material_structure"] == {
            "rows": [], "label_header": "Position Type", "n_unanalyzed": 0}
        assert body["bishop_endings"] == []
        assert body["position_character"]["n_classified"] == 0
        assert body["position_character"]["bucket_win"] == []
        assert body["position_character"]["central_tension_pct"] is None
        assert body["game_side"]["castling_win"] == []
        assert body["game_side"]["action_win"] == []

    def test_rejects_an_unknown_structure_type(self, api_client):
        resp = api_client.get("/api/patterns/positions?structure_type=nonsense")
        assert resp.status_code == 422

    def test_grouped_true_uses_bucket_label_and_category_header(self, api_client, migrated_db_path):
        _seed_structure_game(migrated_db_path, "g1", "win", 40, "Q1P4vP4",
                              cpl=10, classification="good")
        resp = api_client.get("/api/patterns/positions?structure_type=endgame&grouped=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["material_structure"]["label_header"] == "Category"
        row = next(r for r in body["material_structure"]["rows"] if r["label"] == "Queen")
        assert row["n_games"] == 1
        assert row["win_pct"] == 100.0
        assert row["acpl"] == pytest.approx(10.0)
        assert body["material_structure"]["n_unanalyzed"] == 0

    def test_ungrouped_formats_material_sig_as_unified_label(self, api_client, migrated_db_path):
        # structure_min_games_per_group=5 (config.yaml) -- get_material_
        # structure_table only surfaces a signature with >= 5 games.
        for i in range(5):
            _seed_structure_game(migrated_db_path, f"g{i}", "win", 40, "Q1R1B1P6vQ1R1B1P6")
        resp = api_client.get("/api/patterns/positions?structure_type=endgame&grouped=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["material_structure"]["label_header"] == "Position Type"
        row = next(r for r in body["material_structure"]["rows"]
                   if r["label"] == "Q+R+B+6P vs Q+R+B+6P")
        assert row["n_games"] == 5
        assert row["acpl"] is None  # no cpl seeded -- all 5 unanalyzed
        assert body["material_structure"]["n_unanalyzed"] == 1

    def test_bishop_endings_below_two_buckets_returns_empty(self, api_client, migrated_db_path):
        for i in range(5):
            _seed_bishop_game(migrated_db_path, f"same{i}", _SAME_BISHOP_FEN, cpl=20)
        resp = api_client.get("/api/patterns/positions")
        assert resp.json()["bishop_endings"] == []

    def test_bishop_endings_with_two_buckets_returns_both(self, api_client, migrated_db_path):
        for i in range(5):
            _seed_bishop_game(migrated_db_path, f"same{i}", _SAME_BISHOP_FEN, cpl=20)
            _seed_bishop_game(migrated_db_path, f"opp{i}", _OPPOSITE_BISHOP_FEN, cpl=100)
        # get_bishop_color_ending_performance's internal ensure_structure_ctx
        # call writes new structure_ctx_cache rows to the LIVE sqlite file
        # via sqlite_conn, but duck_conn only ever reads a private snapshot
        # taken at connection-open time (connections.py's snapshot-isolation
        # docstring: "new data only appears after refresh_snapshot()") --
        # so THIS FIRST call computes+persists structure_ctx_cache but its
        # own bishop_endings comes back stale/empty, same race test_material_
        # structure.py's test_seeded_two_buckets_have_real_acpl already
        # dodges by reordering ensure_structure_ctx before its own snapshot.
        # Forcing a fresh connections.clear_cache() + api_main.reset_caches()
        # before the real request rebuilds the duck snapshot from the
        # now-populated sqlite file.
        api_client.get("/api/patterns/positions")
        import connections
        connections.clear_cache()
        import api.main as api_main
        api_main.reset_caches()

        resp = api_client.get("/api/patterns/positions")
        body = resp.json()
        lookup = {r["bucket"]: r for r in body["bishop_endings"]}
        assert lookup["same"]["acpl"] == pytest.approx(20.0)
        assert lookup["opposite"]["acpl"] == pytest.approx(100.0)

    def test_position_character_gate_and_buckets(self, api_client, migrated_db_path):
        _seed_checkpoint_game(migrated_db_path, "g1", "win", _CLOSED_FEN)
        _seed_checkpoint_game(migrated_db_path, "g2", "loss", _CLOSED_FEN)
        _seed_checkpoint_game(migrated_db_path, "g3", "win", _OPEN_FEN)
        resp = api_client.get("/api/patterns/positions")
        body = resp.json()
        pc = body["position_character"]
        assert pc["n_classified"] == 3
        win_lookup = {r["bucket"]: r for r in pc["bucket_win"]}
        assert win_lookup["closed"]["n_games"] == 2
        assert win_lookup["closed"]["win_pct"] == pytest.approx(50.0)
        assert win_lookup["open"]["n_games"] == 1

    def test_game_side_gate_and_buckets(self, api_client, migrated_db_path):
        _seed_castle_game(migrated_db_path, "g1", "win", "g1", "g8")   # same-side
        _seed_castle_game(migrated_db_path, "g2", "loss", "c1", "g8")  # opposite-side
        resp = api_client.get("/api/patterns/positions")
        body = resp.json()
        gs = body["game_side"]
        castling_lookup = {r["castling_config"]: r["n_games"] for r in gs["castling_win"]}
        assert castling_lookup["same-side"] == 1
        assert castling_lookup["opposite-side"] == 1

    def test_ttl_cache_is_keyed_by_structure_type_and_grouped(
            self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_sharpness_blunder_correlation

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_sharpness_blunder_correlation", _counting)

        api_client.get("/api/patterns/positions?structure_type=endgame&grouped=false")
        api_client.get("/api/patterns/positions?structure_type=endgame&grouped=false")
        assert call_count["n"] == 1  # second identical call served from cache

        api_client.get("/api/patterns/positions?structure_type=endgame&grouped=true")
        assert call_count["n"] == 2
        api_client.get("/api/patterns/positions?structure_type=middlegame&grouped=false")
        assert call_count["n"] == 3
        api_client.get("/api/patterns/positions?structure_type=middlegame&grouped=true")
        assert call_count["n"] == 4

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/positions?structure_type=endgame&grouped=false")
        assert call_count["n"] == 5


