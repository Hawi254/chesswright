"""Unit tests for achievements.py's evaluation engine mechanics --
skip-if-unlocked, trigger filtering, and check()-exception containment.
Uses fake Achievement entries (monkeypatched onto CATALOG), not the real
seed catalog -- that's covered separately in tests/integration/test_achievements.py
once Tasks 3-6 populate CATALOG for real. No foreign_keys pragma or full
migration here, matching tests/unit/test_worker.py's own minimal-schema-
replica convention -- this table's REFERENCES games(id) isn't enforced
without PRAGMA foreign_keys=ON, so a bare achievements_unlocked table is
enough to exercise the engine in isolation."""
import sqlite3

import pytest

import achievements
from achievements import Achievement


def _minimal_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE achievements_unlocked "
        "(achievement_id TEXT PRIMARY KEY, unlocked_at TEXT NOT NULL, source_game_id TEXT)")
    return conn


@pytest.mark.unit
class TestEvaluateEngine:
    def test_unlocks_matching_achievement(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_a", "Fake A", "desc", "milestone",
                            frozenset({"sync"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == ["fake_a"]
        row = conn.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='fake_a'"
        ).fetchone()
        assert row[0] is None

    def test_records_source_game_id_when_check_returns_a_string(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_b", "Fake B", "desc", "narrative",
                            frozenset({"sync"}), lambda c, cfg: "g42")
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        achievements.evaluate(conn, "sync")
        row = conn.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='fake_b'"
        ).fetchone()
        assert row[0] == "g42"

    def test_already_unlocked_is_skipped_without_calling_check_again(self, monkeypatch):
        conn = _minimal_db()
        conn.execute(
            "INSERT INTO achievements_unlocked VALUES ('fake_c', '2025-01-01T00:00:00', NULL)")
        conn.commit()
        calls = []

        def _check(c, cfg):
            calls.append(1)
            return True

        fake = Achievement("fake_c", "Fake C", "desc", "milestone",
                            frozenset({"sync"}), _check)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == []
        assert calls == []

    def test_filters_by_trigger(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_d", "Fake D", "desc", "milestone",
                            frozenset({"analysis"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == []
        assert conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0] == 0

    def test_trigger_none_runs_full_catalog_regardless_of_triggers(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_e", "Fake E", "desc", "milestone",
                            frozenset({"analysis"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, trigger=None)
        assert unlocked == ["fake_e"]

    def test_a_failing_check_is_caught_and_does_not_block_others(self, monkeypatch, capsys):
        conn = _minimal_db()

        def _boom(c, cfg):
            raise RuntimeError("boom")

        broken = Achievement("fake_f", "Fake F", "desc", "milestone",
                              frozenset({"sync"}), _boom)
        ok = Achievement("fake_g", "Fake G", "desc", "milestone",
                          frozenset({"sync"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [broken, ok])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == ["fake_g"]
        assert "fake_f" in capsys.readouterr().out
