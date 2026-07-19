"""Integration tests for the Patterns & Tendencies pieces endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _insert_full_game, _insert_full_move

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
class TestPatternsPieces:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/pieces")
        assert resp.status_code == 200
        body = resp.json()
        assert body["piece_movement"] == []
        assert body["piece_by_view"] == []
        assert body["bishop_square_color"] == []
        assert body["rook_king_backrank"] == []
        assert body["square_heatmap"] == {"cells": [], "n_analyzed": 0, "n_total_in_scope": 0}
        assert body["motif_backfill_needed"] is False
        assert body["castling"] == {"win": [], "acpl": []}

    def test_rejects_an_unknown_view_by(self, api_client):
        resp = api_client.get("/api/patterns/pieces?view_by=nonsense")
        assert resp.status_code == 422

    def test_bundles_real_data_view_by_phase(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1", player_color="white",
                           outcome_for_player="win", num_plies=40)
        # material_sig seeded so analytics.ensure_structure_ctx() builds a
        # structure_ctx row for g1 -- get_piece_blunder_by_phase() inner-joins
        # moves against structure_ctx, so a game with no material_sig data
        # anywhere would silently drop out of piece_by_view entirely.
        full_material_sig = "Q1R2B2N2P8vQ1R2B2N2P8"
        _insert_full_move(migrated_db_path, "g1", ply=1, move_number=1, color="w",
                           is_player_move=1, cpl=150, classification="blunder",
                           piece="Q", to_square="d4", material_sig=full_material_sig)
        _insert_full_move(migrated_db_path, "g1", ply=3, move_number=2, color="w",
                           is_player_move=1, cpl=10, classification="good",
                           piece="B", to_square="e5", material_sig=full_material_sig)
        _insert_full_move(migrated_db_path, "g1", ply=5, move_number=3, color="w",
                           is_player_move=1, cpl=20, classification="good",
                           piece="R", to_square="a1", material_sig=full_material_sig)
        _insert_full_move(migrated_db_path, "g1", ply=7, move_number=4, color="w",
                           is_player_move=1, cpl=5, classification="good",
                           piece="K", to_square="g1", is_castle=1, material_sig=full_material_sig)
        # motif_backfill_needed requires >= MOTIF_BACKFILL_MIN_CANDIDATES (20)
        # blunder/mistake player moves with no motif classification -- the
        # single Q blunder above isn't enough on its own to cross that gate.
        for i in range(19):
            _insert_full_move(migrated_db_path, "g1", ply=100 + i, move_number=50 + i, color="w",
                               is_player_move=1, cpl=150, classification="blunder")

        resp = api_client.get("/api/patterns/pieces?view_by=phase")
        assert resp.status_code == 200
        body = resp.json()

        piece_rows = {r["piece"]: r for r in body["piece_movement"]}
        assert piece_rows["Q"]["n_moves"] == 1
        assert piece_rows["Q"]["blunder_rate"] == 100.0

        view_rows = {(r["piece"], r["phase"]) for r in body["piece_by_view"]}
        assert ("Q", "opening") in view_rows
        assert "bucket" not in body["piece_by_view"][0]

        assert len(body["bishop_square_color"]) == 1

        backrank_rows = {(r["piece"], r["location"]) for r in body["rook_king_backrank"]}
        assert ("R", "back rank") in backrank_rows  # a1 is white's back rank
        assert ("K", "back rank") in backrank_rows  # g1 is white's back rank

        assert body["motif_backfill_needed"] is True  # no motif classification seeded anywhere

        win_rows = {r["status"]: r for r in body["castling"]["win"]}
        assert win_rows["castled"]["n_games"] == 1
        assert win_rows["castled"]["win_pct"] == 100.0

    def test_view_by_sharpness_uses_bucket_key(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1")
        _insert_full_move(migrated_db_path, "g1", ply=1, move_number=1, color="w",
                           is_player_move=1, cpl=100, classification="blunder",
                           piece="Q", sharpness=50)

        resp = api_client.get("/api/patterns/pieces?view_by=sharpness")
        assert resp.status_code == 200
        body = resp.json()
        assert body["piece_by_view"][0]["bucket"] == "moderate (25-75cp)"
        assert "phase" not in body["piece_by_view"][0]

    def test_square_heatmap_melts_pivot_into_long_form_cells(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1", num_plies=40)
        for i in range(25):
            _insert_full_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1, color="w",
                               is_player_move=1, cpl=50,
                               classification="blunder" if i < 5 else "good",
                               piece="P", to_square="e4")

        resp = api_client.get("/api/patterns/pieces?view_by=phase")
        body = resp.json()
        heatmap = body["square_heatmap"]
        assert heatmap["n_analyzed"] == 25
        assert heatmap["n_total_in_scope"] == 25
        e4_cell = next(c for c in heatmap["cells"] if c["file"] == "e" and c["rank"] == 4)
        assert e4_cell["n_moves"] == 25
        assert e4_cell["blunder_rate"] == pytest.approx(20.0)

    def test_ttl_cache_is_keyed_by_view_by(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_piece_movement_patterns

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_piece_movement_patterns", _counting)

        api_client.get("/api/patterns/pieces?view_by=phase")
        api_client.get("/api/patterns/pieces?view_by=phase")
        assert call_count["n"] == 1  # second phase call served from cache

        api_client.get("/api/patterns/pieces?view_by=sharpness")
        assert call_count["n"] == 2  # different view_by -> separate cache entry

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/pieces?view_by=phase")
        assert call_count["n"] == 3

