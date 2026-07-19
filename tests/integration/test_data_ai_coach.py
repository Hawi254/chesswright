"""Integration tests for dashboard/data/ai_coach.py -- split from
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
class TestAiCoachData:
    """dashboard/data/ai_coach.py -- AI Coach (Pro feature) CRUD: plain core
    plumbing, no Claude API calls, no tool-set/prompt logic."""

    def test_start_conversation_and_add_turns_in_order(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        assert isinstance(conv_id, int)
        t1 = C.add_turn(migrated_db, conv_id, "user", "How's my endgame?")
        t2 = C.add_turn(migrated_db, conv_id, "assistant", "Let's look at your rook endings.")
        assert t2 > t1
        messages = C.get_conversation_messages(migrated_db, conv_id)
        assert messages == [
            {"role": "user", "content": "How's my endgame?"},
            {"role": "assistant", "content": "Let's look at your rook endings."},
        ]

    def test_add_turn_rejects_invalid_role(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        with pytest.raises(ValueError):
            C.add_turn(migrated_db, conv_id, "system", "not allowed")

    def test_get_conversation_messages_scoped_to_one_conversation(self, migrated_db):
        from data import ai_coach as C
        conv1 = C.start_conversation(migrated_db)
        conv2 = C.start_conversation(migrated_db)
        C.add_turn(migrated_db, conv1, "user", "conv1 question")
        C.add_turn(migrated_db, conv2, "user", "conv2 question")
        assert len(C.get_conversation_messages(migrated_db, conv1)) == 1
        assert C.get_conversation_messages(migrated_db, conv1)[0]["content"] == "conv1 question"

    def test_record_feedback_on_assistant_turn(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "Some advice.")
        C.record_feedback(migrated_db, turn_id, -1)
        turns = C.get_all_turns(migrated_db)
        assert turns[0]["feedback"] == -1

    def test_record_feedback_rejects_invalid_turn_id(self, migrated_db):
        from data import ai_coach as C
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, 999999, 1)

    def test_record_feedback_rejects_non_assistant_turn(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        user_turn_id = C.add_turn(migrated_db, conv_id, "user", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, user_turn_id, 1)

    def test_record_feedback_rejects_invalid_value(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, turn_id, 2)

    def test_get_all_turns_ordering_and_thumbs_down_filter(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        t1 = C.add_turn(migrated_db, conv_id, "user", "q1")
        t2 = C.add_turn(migrated_db, conv_id, "assistant", "bad advice")
        t3 = C.add_turn(migrated_db, conv_id, "assistant", "good advice")
        C.record_feedback(migrated_db, t2, -1)
        C.record_feedback(migrated_db, t3, 1)

        all_turns = C.get_all_turns(migrated_db)
        assert [t["id"] for t in all_turns] == [t1, t2, t3]

        filtered = C.get_all_turns(migrated_db, exclude_thumbs_down=True)
        assert [t["id"] for t in filtered] == [t1, t3]

    def test_get_all_turns_since_timestamp(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'old message', '2026-01-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new message', '2026-06-01T00:00:00')
        """, [conv_id])
        migrated_db.commit()

        since = C.get_all_turns(migrated_db, since="2026-03-01T00:00:00")
        assert [t["content"] for t in since] == ["new message"]

        combined = C.get_all_turns(migrated_db, exclude_thumbs_down=True,
                                    since="2026-03-01T00:00:00")
        assert [t["content"] for t in combined] == ["new message"]

    def test_profile_get_returns_none_before_any_upsert(self, migrated_db):
        from data import ai_coach as C
        assert C.get_profile(migrated_db) is None

    def test_profile_upsert_round_trip(self, migrated_db):
        from data import ai_coach as C
        C.upsert_profile(migrated_db, "Player struggles in rook endings.",
                          12, "2026-06-01T00:00:00", "claude-sonnet-5")
        profile = C.get_profile(migrated_db)
        assert profile == {
            "summary_text": "Player struggles in rook endings.",
            "source_turns": 12,
            "generated_at": "2026-06-01T00:00:00",
            "model": "claude-sonnet-5",
        }
        # upsert again -- always writes back to id=1, replacing the row
        C.upsert_profile(migrated_db, "Updated summary.", 20,
                          "2026-07-01T00:00:00", "claude-sonnet-5")
        profile2 = C.get_profile(migrated_db)
        assert profile2["summary_text"] == "Updated summary."
        assert profile2["source_turns"] == 20
        # still a single row (id=1 singleton, not a second row)
        n_rows = migrated_db.execute(
            "SELECT COUNT(*) FROM ai_coach_profile").fetchone()[0]
        assert n_rows == 1

    def test_count_turns_since_staleness_helper(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'old', '2026-01-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new1', '2026-06-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new2', '2026-06-02T00:00:00')
        """, [conv_id])
        migrated_db.commit()
        assert C.count_turns_since(migrated_db, "2026-03-01T00:00:00") == 2
        assert C.count_turns_since(migrated_db, "2026-12-31T00:00:00") == 0

    def test_record_and_get_capability_gaps_newest_first(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn1 = C.add_turn(migrated_db, conv_id, "assistant", "partial answer one")
        turn2 = C.add_turn(migrated_db, conv_id, "assistant", "partial answer two")

        gap1_id = C.record_capability_gap(
            migrated_db, turn1, "average move time by opening",
            "no per-opening move-time aggregation exists")
        assert isinstance(gap1_id, int)
        gap2_id = C.record_capability_gap(
            migrated_db, turn2, "best performing time control",
            "no per-time-control win-rate breakdown exists")
        assert gap2_id > gap1_id

        gaps = C.get_capability_gaps(migrated_db)
        # newest first (created_at DESC) -- gap2 was recorded after gap1.
        assert [g["id"] for g in gaps] == [gap2_id, gap1_id]
        assert gaps[0]["turn_id"] == turn2
        assert gaps[0]["question_summary"] == "best performing time control"
        assert gaps[0]["missing_data_description"] == (
            "no per-time-control win-rate breakdown exists")
        assert gaps[1]["turn_id"] == turn1

    def test_get_capability_gaps_respects_limit(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "answer")
        for i in range(5):
            C.record_capability_gap(migrated_db, turn_id, f"question {i}", f"missing {i}")
        assert len(C.get_capability_gaps(migrated_db, limit=3)) == 3
        assert len(C.get_capability_gaps(migrated_db)) == 5

    def test_record_capability_gap_requires_real_turn_id(self, migrated_db):
        """ai_coach_capability_gaps.turn_id REFERENCES ai_coach_turns(id) --
        this migrated_db fixture connection runs with foreign_keys ON (see
        conftest.py's migrated_db fixture and db.py's get_connection, which
        both explicitly set this PRAGMA every connection since it's not a
        database-file-level setting in SQLite), so inserting against a
        turn_id that doesn't exist must raise, not silently succeed."""
        from data import ai_coach as C
        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                migrated_db, 999999, "some question", "some missing data")

