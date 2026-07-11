"""
Integration tests for dashboard/data/drills.py (roadmap §24, "Endgame
Trainer MVP"): get_decisive_moment_positions' new `phase` filter (with its
real-material endgame check, not just move_number > 30) and
build_drill_cards' new `include_endgame_moments` source.

Zero test coverage existed for this module before this file -- confirmed
via grep, no other test references get_decisive_moment_positions or
build_drill_cards.
"""
import pathlib
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _duck_from_conn(sqlite_conn):
    """Copy an in-memory/real sqlite connection to a temp file and attach
    it to a fresh DuckDB connection. Returns (duck_conn, disk_conn,
    tmp_path) -- callers must close both and delete the temp file. Mirrors
    tests/integration/test_material_structure.py's helper of the same
    name."""
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


# Non-pawn piece counts verified against chess_utils.non_pawn_piece_count's
# NON_PAWN_PIECE_RE = r"([QRBN])(\d+)" (only Q/R/B/N letters counted, P
# skipped): "Q1R2B1N1P7vQ1R1B1N1P6" -> 1+2+1+1 + 1+1+1+1 = 9 (> 6, the
# default endgame_max_pieces). "R1B1P6vR1B1P6" -> 1+1 + 1+1 = 4 (<= 6).
_HEAVY_MATERIAL_SIG = "Q1R2B1N1P7vQ1R1B1N1P6"   # non_pawn_piece_count == 9
_LIGHT_MATERIAL_SIG = "R1B1P6vR1B1P6"           # non_pawn_piece_count == 4
_FULL_MATERIAL_SIG = "Q1R2B2N2P7vQ1R2B2N2P7"    # non_pawn_piece_count == 14


def _seed_time_pressure_move(conn, game_id, clock_seconds, base_seconds,
                              classification, cpl=100, fen_before=None,
                              best_move_san="Nf3", actual_move_san="Ng1",
                              move_number=20):
    """One game (base_seconds set for the time-pressure fraction), one
    move row shaped for get_time_pressure_drill_positions (classification/
    cpl/clock_seconds, NOT the win_prob columns _seed_loss_game seeds --
    that helper is decisive-moment-shaped, this query is motif-drill-
    positions-shaped, mirroring get_motif_drill_positions)."""
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, player_color, base_seconds) "
        "VALUES (?, 'W', 'B', 'loss', 'white', ?)",
        (game_id, base_seconds))
    fen_before = fen_before or f"fen_{game_id}"
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before, "
        "best_move_san, clock_seconds, cpl, classification, is_player_move) "
        "VALUES (?, ?, ?, 'w', ?, ?, ?, ?, ?, ?, 1)",
        (game_id, move_number * 2 - 1, move_number, actual_move_san,
         fen_before, best_move_san, clock_seconds, cpl, classification))
    conn.commit()


def _seed_loss_game(conn, game_id, wp_before, wp_after, move_number,
                     material_sig, fen_before=None, best_move_san="Nf3",
                     actual_move_san="Ng1", rating_diff=None):
    """One loss game, one contested decisive-moment-eligible move row.

    rating_diff defaults to None (not a collapse) so existing non-collapse
    tests are unaffected -- pass rating_diff=300+ to seed a "collapse"
    (player_rating - opponent_rating, per games.rating_diff)."""
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, player_color, rating_diff) "
        "VALUES (?, 'W', 'B', 'loss', 'white', ?)",
        (game_id, rating_diff))
    fen_before = fen_before or f"fen_{game_id}"
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before, "
        "best_move_san, win_prob_before, win_prob_after, material_sig, "
        "is_player_move) VALUES (?, ?, ?, 'w', ?, ?, ?, ?, ?, ?, 1)",
        (game_id, move_number * 2 - 1, move_number, actual_move_san,
         fen_before, best_move_san, wp_before, wp_after, material_sig))
    conn.commit()


@pytest.mark.integration
class TestGetDecisiveMomentPositionsPhaseFilter:
    def test_no_phase_arg_unaffected_ordering_and_top_n(self, migrated_db):
        """No `phase` arg must behave identically to the old SQL LIMIT
        path: same rows, same wp_drop-descending order, top_n still
        truncates -- now via pandas .head() instead of SQL LIMIT."""
        from data.drills import get_decisive_moment_positions

        _seed_loss_game(migrated_db, "g1", wp_before=0.60, wp_after=0.30,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG)   # wp_drop 0.30
        _seed_loss_game(migrated_db, "g2", wp_before=0.55, wp_after=0.35,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG)   # wp_drop 0.20
        _seed_loss_game(migrated_db, "g3", wp_before=0.50, wp_after=0.45,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG)   # wp_drop 0.05

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            df = get_decisive_moment_positions(duck, top_n=2)
            assert list(df.game_id) == ["g1", "g2"]
            assert len(df) == 2
            assert list(df.wp_drop) == sorted(df.wp_drop, reverse=True)
            # material_sig must not leak into the output columns.
            assert "material_sig" not in df.columns
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def test_phase_endgame_excludes_heavy_material(self, migrated_db):
        """move_number > 30 alone puts a row in phase='endgame', but a
        real long-middlegame material count (> endgame_max_pieces) must
        be excluded when phase='endgame' is requested -- the 15.6%
        mislabeling rate this filter exists to fix."""
        from data.drills import get_decisive_moment_positions

        _seed_loss_game(migrated_db, "g_heavy", wp_before=0.60, wp_after=0.30,
                         move_number=35, material_sig=_HEAVY_MATERIAL_SIG)

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            df = get_decisive_moment_positions(duck, top_n=20, phase="endgame")
            assert "g_heavy" not in set(df.game_id)
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def test_phase_endgame_includes_light_material(self, migrated_db):
        """move_number > 30 AND real light material (<= endgame_max_pieces)
        must be included."""
        from data.drills import get_decisive_moment_positions

        _seed_loss_game(migrated_db, "g_light", wp_before=0.60, wp_after=0.30,
                         move_number=35, material_sig=_LIGHT_MATERIAL_SIG)

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            df = get_decisive_moment_positions(duck, top_n=20, phase="endgame")
            assert "g_light" in set(df.game_id)
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestGetDecisiveMomentPositionsCollapseFilter:
    def test_collapse_only_excludes_non_collapse_loss(self, migrated_db):
        """collapse_only=True must keep a loss as a 300+-rated favorite
        (a "collapse") but drop an otherwise-identical loss with no rating
        edge -- and rating_diff itself must not leak into the returned
        columns (same discipline as material_sig)."""
        from data.drills import get_decisive_moment_positions

        _seed_loss_game(migrated_db, "g_collapse", wp_before=0.60, wp_after=0.30,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG,
                         fen_before="fen_g_collapse", rating_diff=300)
        _seed_loss_game(migrated_db, "g_plain", wp_before=0.60, wp_after=0.30,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG,
                         fen_before="fen_g_plain", rating_diff=0)

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            df = get_decisive_moment_positions(duck, top_n=20, collapse_only=True)
            assert set(df.game_id) == {"g_collapse"}
            assert "rating_diff" not in df.columns
            assert "material_sig" not in df.columns
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestBuildDrillCardsEndgameMoments:
    def test_include_endgame_moments_produces_labeled_cards(self, migrated_db):
        from data.drills import build_drill_cards

        _seed_loss_game(migrated_db, "g_light", wp_before=0.60, wp_after=0.30,
                         move_number=35, material_sig=_LIGHT_MATERIAL_SIG,
                         fen_before="fen_g_light")

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            cards = build_drill_cards(
                migrated_db, duck, sources={"endgame_moments"}, top_n=20)
            assert len(cards) == 1
            assert cards[0]["source"] == "Endgame Turning Point"
            assert cards[0]["fen"] == "fen_g_light"
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def test_endgame_moments_collected_before_moments_wins_label(self, migrated_db):
        """A position qualifying for BOTH include_moments (generic decisive
        moment, no phase filter) and include_endgame_moments (phase=
        'endgame' + light material) must end up labeled by the
        endgame-specific source -- proving the deliberate ordering
        (endgame collected first in the `cards` list) actually decides
        which label wins once add_cards() dedupes by UNIQUE(fen) via
        INSERT OR IGNORE (first occurrence in the list wins the insert;
        the second is silently ignored)."""
        from data.drills import build_drill_cards
        from data.srs import add_cards

        _seed_loss_game(migrated_db, "g_both", wp_before=0.60, wp_after=0.30,
                         move_number=35, material_sig=_LIGHT_MATERIAL_SIG,
                         fen_before="fen_g_both")

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            cards = build_drill_cards(
                migrated_db, duck,
                sources={"moments", "endgame_moments"},
                top_n=20)
            # Both sources legitimately produce a card for this fen at the
            # build_drill_cards() list stage -- dedup only happens at
            # add_cards() insert time (UNIQUE(fen) via INSERT OR IGNORE).
            matching = [c for c in cards if c["fen"] == "fen_g_both"]
            assert len(matching) == 2
            assert matching[0]["source"] == "Endgame Turning Point"
            assert matching[1]["source"] == "Decisive Moment"

            add_cards(migrated_db, cards)
            row = migrated_db.execute(
                "SELECT source FROM srs_cards WHERE fen = ?", ("fen_g_both",)
            ).fetchone()
            assert row is not None
            assert row[0] == "Endgame Turning Point"
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestBuildDrillCardsCollapseMoments:
    def test_collapse_moments_produces_labeled_cards(self, migrated_db):
        from data.drills import build_drill_cards

        _seed_loss_game(migrated_db, "g_collapse", wp_before=0.60, wp_after=0.30,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG,
                         fen_before="fen_g_collapse", rating_diff=300)

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            cards = build_drill_cards(
                migrated_db, duck, sources={"collapse_moments"}, top_n=20)
            assert len(cards) == 1
            assert cards[0]["source"] == "Collapse"
            assert cards[0]["fen"] == "fen_g_collapse"
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def test_collapse_moments_collected_before_moments_wins_label(self, migrated_db):
        """A position qualifying for BOTH generic `moments` (no phase/
        collapse filter) and `collapse_moments` (rating_diff >= 300) must
        end up labeled "Collapse" -- proving collapse_moments' place in
        _SOURCE_ORDER (before moments) actually decides which label wins
        once add_cards() dedupes by UNIQUE(fen) via INSERT OR IGNORE
        (first occurrence in the list wins the insert)."""
        from data.drills import build_drill_cards
        from data.srs import add_cards

        _seed_loss_game(migrated_db, "g_both", wp_before=0.60, wp_after=0.30,
                         move_number=20, material_sig=_FULL_MATERIAL_SIG,
                         fen_before="fen_g_both", rating_diff=300)

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            cards = build_drill_cards(
                migrated_db, duck,
                sources={"moments", "collapse_moments"},
                top_n=20)
            matching = [c for c in cards if c["fen"] == "fen_g_both"]
            assert len(matching) == 2
            assert matching[0]["source"] == "Collapse"
            assert matching[1]["source"] == "Decisive Moment"

            add_cards(migrated_db, cards)
            row = migrated_db.execute(
                "SELECT source FROM srs_cards WHERE fen = ?", ("fen_g_both",)
            ).fetchone()
            assert row is not None
            assert row[0] == "Collapse"
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def test_unknown_source_raises_value_error(self, migrated_db):
        from data.drills import build_drill_cards

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            with pytest.raises(ValueError):
                build_drill_cards(
                    migrated_db, duck, sources={"not_a_real_source"}, top_n=20)
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestGetTimePressureDrillPositions:
    def test_critical_clock_blunder_included(self, migrated_db):
        """clock_seconds/base_seconds < 0.05 (critical band) with a
        blunder classification must be returned."""
        from data.drills import get_time_pressure_drill_positions

        _seed_time_pressure_move(
            migrated_db, "g_critical", clock_seconds=10, base_seconds=300,
            classification="blunder", fen_before="fen_g_critical")

        df = get_time_pressure_drill_positions(migrated_db, top_n=20)
        assert "fen_g_critical" in set(df.fen_before)

    def test_comfortable_clock_excluded(self, migrated_db):
        """Same classification, but a comfortable clock fraction (0.5)
        must be excluded."""
        from data.drills import get_time_pressure_drill_positions

        _seed_time_pressure_move(
            migrated_db, "g_comfortable", clock_seconds=150, base_seconds=300,
            classification="blunder", fen_before="fen_g_comfortable")

        df = get_time_pressure_drill_positions(migrated_db, top_n=20)
        assert "fen_g_comfortable" not in set(df.fen_before)

    def test_non_mistake_classification_excluded(self, migrated_db):
        """Critical clock but a classification outside ('mistake',
        'blunder') must be excluded."""
        from data.drills import get_time_pressure_drill_positions

        _seed_time_pressure_move(
            migrated_db, "g_best", clock_seconds=10, base_seconds=300,
            classification="best", fen_before="fen_g_best")

        df = get_time_pressure_drill_positions(migrated_db, top_n=20)
        assert "fen_g_best" not in set(df.fen_before)


@pytest.mark.integration
class TestBuildDrillCardsTimePressure:
    def test_time_pressure_produces_labeled_cards(self, migrated_db):
        from data.drills import build_drill_cards

        _seed_time_pressure_move(
            migrated_db, "g_critical", clock_seconds=10, base_seconds=300,
            classification="blunder", fen_before="fen_g_critical")

        duck, disk, tmp_path = _duck_from_conn(migrated_db)
        try:
            cards = build_drill_cards(
                migrated_db, duck, sources={"time_pressure"}, top_n=20)
            assert len(cards) == 1
            assert cards[0]["source"] == "Time Pressure"
            assert cards[0]["fen"] == "fen_g_critical"
        finally:
            duck.close()
            disk.close()
            pathlib.Path(tmp_path).unlink(missing_ok=True)
