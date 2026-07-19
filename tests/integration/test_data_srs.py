"""Integration tests for dashboard/data/srs.py -- split from
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
class TestSrsEfficacy:
    """dashboard/data/srs.py efficacy readers -- the first SELECTs
    srs_reviews has ever had. Reviews are inserted with controlled
    timestamps (apply_rating stamps now(), useless for before/after
    assertions)."""

    def _seed(self, conn):
        from data import srs as S
        conn.execute("INSERT INTO games (id, white, black, result) "
                     "VALUES ('g1', 'a', 'b', '1-0')")
        conn.execute("""
            INSERT INTO moves (game_id, ply, move_number, color, san,
                is_player_move, motif, fen_before)
            VALUES ('g1', 1, 1, 'w', 'e4', 1, 'fork', 'FEN_FORK')
        """)
        S.add_cards(conn, [
            {"fen": "FEN_FORK", "source": "Missed Tactics", "best_move_san": "Nf3"},
            {"fen": "FEN_HOLE", "source": "Repertoire Hole", "best_move_san": "d4"},
        ])
        ids = {fen: cid for cid, fen in
               conn.execute("SELECT id, fen FROM srs_cards").fetchall()}
        reviews = [
            (ids["FEN_FORK"], "2026-06-01T10:00:00", 0),   # 1st sight: forgot
            (ids["FEN_FORK"], "2026-06-02T10:00:00", 2),   # 2nd: good
            (ids["FEN_FORK"], "2026-06-05T10:00:00", 3),   # 3rd: easy
            (ids["FEN_HOLE"], "2026-06-03T10:00:00", 2),
        ]
        for cid, ts, rating in reviews:
            conn.execute("""
                INSERT INTO srs_reviews (card_id, reviewed_at, rating,
                    interval_days_after) VALUES (?, ?, ?, 1)
            """, (cid, ts, rating))
        conn.commit()
        return ids

    def test_empty_db_is_safe(self, migrated_db):
        from data import srs as S
        history = S.get_review_history(migrated_db)
        assert history.empty
        assert S.weekly_recall(history).empty
        assert S.learning_curve(history).empty
        assert S.recall_by_source(history).empty
        assert S.get_drilled_motifs(migrated_db).empty

    def test_review_history_and_learning_curve(self, migrated_db):
        from data import srs as S
        self._seed(migrated_db)
        history = S.get_review_history(migrated_db)
        assert len(history) == 4
        fork = history[history.source == "Missed Tactics"]
        assert fork.review_index.tolist() == [1, 2, 3]
        curve = S.learning_curve(history).set_index("nth_review")
        assert curve.loc["1st"].recall_pct == pytest.approx(50.0)  # 0 and 2
        assert curve.loc["2nd"].recall_pct == pytest.approx(100.0)
        by_source = S.recall_by_source(history).set_index("source")
        assert by_source.loc["Missed Tactics"].n_reviews == 3

    def test_drilled_motifs_joins_by_fen(self, migrated_db):
        from data import srs as S
        self._seed(migrated_db)
        drilled = S.get_drilled_motifs(migrated_db)
        # only the fork card maps to a motif move; the hole card doesn't
        assert drilled.motif.tolist() == ["fork"]
        row = drilled.iloc[0]
        assert row.n_cards == 1
        assert row.n_reviews == 3
        assert row.first_review == "2026-06-01"

    def test_compute_motif_transfer(self, migrated_db):
        import pandas as pd
        from data import srs as S
        self._seed(migrated_db)
        drilled = S.get_drilled_motifs(migrated_db)
        moves = pd.DataFrame({
            # cutoff day itself (2026-06-01) counts as AFTER
            "d": ["2026-05-20", "2026-06-01", "2026-06-10"],
            "n_moves": [1000, 100, 400]})
        misses = pd.DataFrame({
            "motif": ["fork", "fork", "fork"],
            "d": ["2026-05-20", "2026-06-01", "2026-06-10"],
            "n_misses": [9, 1, 1]})
        t = S.compute_motif_transfer(drilled, moves, misses,
                                     min_moves_after=200)
        row = t.iloc[0]
        assert row.moves_before == 1000 and row.moves_after == 500
        assert row.misses_before == 9 and row.misses_after == 2
        assert row.rate_before == pytest.approx(9.0)
        assert row.rate_after == pytest.approx(4.0)
        assert bool(row.measurable)
        # guard: not enough post-drill moves
        t2 = S.compute_motif_transfer(drilled, moves, misses,
                                      min_moves_after=600)
        assert not bool(t2.iloc[0].measurable)
        # motif with no miss rows at all -> rates land at 0, not NaN/crash
        t3 = S.compute_motif_transfer(drilled, moves,
                                      misses[misses.motif == "pin"],
                                      min_moves_after=200)
        assert t3.iloc[0].misses_after == 0
        assert t3.iloc[0].rate_after == pytest.approx(0.0)


