"""Integration tests for the Training page's API surface (merges Drill
Export/Training Queue/SRS Drills) -- see
docs/superpowers/specs/2026-07-18-training-page-merge-design.md.
"""
import pathlib
import sqlite3
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


class TestMotifBackfillNeeded:
    def test_returns_true_when_no_motifs_labelled(self, api_client, migrated_db_path):
        # motif_backfill_needed() only trips once n_candidates >=
        # MOTIF_BACKFILL_MIN_CANDIDATES (20, see dashboard/data/tactical.py)
        # -- a single blunder/mistake row isn't enough signal on its own.
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, outcome_for_player) "
            "VALUES ('g1', 'W', 'B', 'white', 'loss')")
        for ply in range(1, 21):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, "
                "is_player_move, classification, cpl, fen_before, best_move_san, motif) "
                "VALUES ('g1', ?, ?, 'w', 'a4', 1, 'blunder', 300, "
                "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'e4', NULL)",
                [ply, ply])
        conn.commit()
        conn.close()

        r = api_client.get("/api/training/motif-backfill-needed")

        assert r.status_code == 200
        assert r.json() == {"needed": True}

    def test_returns_false_when_below_candidate_threshold(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, outcome_for_player) "
            "VALUES ('g1', 'W', 'B', 'white', 'loss')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, "
            "is_player_move, classification, cpl, fen_before, best_move_san, motif) "
            "VALUES ('g1', 1, 1, 'w', 'a4', 1, 'blunder', 300, "
            "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'e4', NULL)")
        conn.commit()
        conn.close()

        r = api_client.get("/api/training/motif-backfill-needed")

        assert r.status_code == 200
        assert r.json() == {"needed": False}


class TestBuildSetPreview:
    def test_preview_returns_motif_source(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, outcome_for_player, opening_family) "
            "VALUES ('g1', 'W', 'B', 'white', 'loss', 'Sicilian Defense')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, "
            "is_player_move, classification, cpl, fen_before, best_move_san, motif) "
            "VALUES ('g1', 1, 1, 'w', 'a4', 1, 'blunder', 300, "
            "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'e4', 'fork')")
        conn.commit()
        conn.close()

        r = api_client.get("/api/training/build-set/preview", params={
            "include_motifs": True, "include_moments": False, "include_holes": False,
            "top_n": 20,
        })

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["sources"][0]["key"] == "missed_tactics"
        assert body["sources"][0]["count"] == 1

    def test_download_pgn_returns_attachment(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, outcome_for_player) "
            "VALUES ('g1', 'W', 'B', 'white', 'loss')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, "
            "is_player_move, classification, cpl, fen_before, best_move_san, motif) "
            "VALUES ('g1', 1, 1, 'w', 'a4', 1, 'blunder', 300, "
            "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'e4', 'fork')")
        conn.commit()
        conn.close()

        r = api_client.get("/api/training/build-set/download-pgn", params={
            "include_motifs": True, "include_moments": False, "include_holes": False,
            "top_n": 20,
        })

        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert "[Event" in r.text


class TestAddToReview:
    def test_403_without_pro(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        r = api_client.post("/api/training/build-set/add-to-review", json={
            "include_motifs": True, "include_moments": False, "include_holes": False, "top_n": 20,
        })
        assert r.status_code == 403

    def test_adds_cards_when_pro_active(self, api_client, migrated_db_path, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, outcome_for_player) "
            "VALUES ('g1', 'W', 'B', 'white', 'loss')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, "
            "is_player_move, classification, cpl, fen_before, best_move_san, motif) "
            "VALUES ('g1', 1, 1, 'w', 'a4', 1, 'blunder', 300, "
            "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'e4', 'fork')")
        conn.commit()
        conn.close()

        r = api_client.post("/api/training/build-set/add-to-review", json={
            "include_motifs": True, "include_moments": False, "include_holes": False, "top_n": 20,
        })

        assert r.status_code == 200
        assert r.json() == {"added": 1}

        conn = sqlite3.connect(migrated_db_path)
        count = conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0]
        conn.close()
        assert count == 1


class TestReviewStatsAndDueCards:
    def test_stats_403_without_pro(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        r = api_client.get("/api/training/review/stats")
        assert r.status_code == 403

    def test_stats_and_due_cards_when_pro_active(self, api_client, migrated_db_path, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO srs_cards (fen, source, best_move_san, context, "
            "ease_factor, interval_days, repetitions, next_due, added_at) "
            "VALUES ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', "
            "'Missed Tactics', 'e4', 'ctx', 2.5, 0, 0, '2020-01-01', '2020-01-01')")
        conn.commit()
        conn.close()

        stats_r = api_client.get("/api/training/review/stats")
        assert stats_r.status_code == 200
        assert stats_r.json()["counts"] == {"total": 1, "due": 1, "new": 1}

        due_r = api_client.get("/api/training/review/due-cards")
        assert due_r.status_code == 200
        cards = due_r.json()
        assert len(cards) == 1
        assert cards[0]["best_move_san"] == "e4"

    def test_rate_and_skip(self, api_client, migrated_db_path, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO srs_cards (fen, source, best_move_san, context, "
            "ease_factor, interval_days, repetitions, next_due, added_at) "
            "VALUES ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', "
            "'Missed Tactics', 'e4', 'ctx', 2.5, 0, 0, '2020-01-01', '2020-01-01')")
        conn.commit()
        card_id = conn.execute("SELECT id FROM srs_cards").fetchone()[0]
        conn.close()

        rate_r = api_client.post("/api/training/review/rate", json={"card_id": card_id, "rating": 2})
        assert rate_r.status_code == 200
        assert rate_r.json() == {"interval_days": 1}

        skip_r = api_client.post("/api/training/review/skip", json={"card_id": card_id})
        assert skip_r.status_code == 200

        conn = sqlite3.connect(migrated_db_path)
        count = conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0]
        conn.close()
        assert count == 0
