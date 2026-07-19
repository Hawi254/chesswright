"""Integration tests for dashboard/data/board_chat.py -- split from
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


class TestBoardChatData:
    """dashboard/data/board_chat.py -- Board Chat (Pro feature) CRUD: a
    game-scoped, multi-turn Claude conversation embedded in Game Detail's
    variation explorer. Plain core plumbing, no Claude API calls, no
    tool-set/prompt logic. Mirrors TestAiCoachData's shape for the
    functions shared in spirit with ai_coach.py, plus new tests for
    get_turns_for_display and list_conversations_for_game, which have no
    ai_coach.py analog."""

    def test_start_conversation_and_add_turns_in_order(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        assert isinstance(conv_id, int)
        t1 = C.add_turn(populated_db, conv_id, "user", "What was the best move here?")
        t2 = C.add_turn(populated_db, conv_id, "assistant", "Nf3 was strongest.")
        assert t2 > t1
        messages = C.get_conversation_messages(populated_db, conv_id)
        assert messages == [
            {"role": "user", "content": "What was the best move here?"},
            {"role": "assistant", "content": "Nf3 was strongest."},
        ]

    def test_add_turn_rejects_invalid_role(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        with pytest.raises(ValueError):
            C.add_turn(populated_db, conv_id, "system", "not allowed")

    def test_get_conversation_messages_scoped_to_one_conversation(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv1 = C.start_conversation(populated_db, game_id)
        conv2 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv1, "user", "conv1 question")
        C.add_turn(populated_db, conv2, "user", "conv2 question")
        assert len(C.get_conversation_messages(populated_db, conv1)) == 1
        assert C.get_conversation_messages(populated_db, conv1)[0]["content"] == "conv1 question"

    def test_get_turns_for_display_board_directives_round_trip(self, populated_db):
        from data import board_chat as C
        import json as json_mod
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        t1 = C.add_turn(populated_db, conv_id, "user", "what about e4?")
        directives = json_mod.dumps([
            {"tool": "show_arrow", "from_square": "e2", "to_square": "e4", "style": "player_move"},
        ])
        t2 = C.add_turn(populated_db, conv_id, "assistant", "e4 is fine.",
                         board_directives=directives)

        turns = C.get_turns_for_display(populated_db, conv_id)
        assert [t["id"] for t in turns] == [t1, t2]
        assert turns[0]["role"] == "user"
        assert turns[0]["board_directives"] is None
        assert turns[1]["role"] == "assistant"
        assert turns[1]["board_directives"] == [
            {"tool": "show_arrow", "from_square": "e2", "to_square": "e4", "style": "player_move"},
        ]
        assert turns[1]["content"] == "e4 is fine."
        assert "created_at" in turns[0]

    def test_list_conversations_for_game_newest_first_with_turn_counts(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv1 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv1, "user", "q1")
        conv2 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv2, "user", "q1")
        C.add_turn(populated_db, conv2, "assistant", "a1")
        C.add_turn(populated_db, conv2, "user", "q2")

        conversations = C.list_conversations_for_game(populated_db, game_id)
        # newest first -- conv2 was started after conv1.
        assert [c["id"] for c in conversations] == [conv2, conv1]
        counts = {c["id"]: c["turn_count"] for c in conversations}
        assert counts[conv1] == 1
        assert counts[conv2] == 3
        assert "started_at" in conversations[0]

    def test_list_conversations_for_game_empty_case(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        assert C.list_conversations_for_game(populated_db, game_id) == []

    def test_record_and_get_capability_gaps_newest_first(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn1 = C.add_turn(populated_db, conv_id, "assistant", "partial answer one")
        turn2 = C.add_turn(populated_db, conv_id, "assistant", "partial answer two")

        gap1_id = C.record_capability_gap(
            populated_db, turn1, "average move time by opening",
            "no per-opening move-time aggregation exists")
        assert isinstance(gap1_id, int)
        gap2_id = C.record_capability_gap(
            populated_db, turn2, "best performing time control",
            "no per-time-control win-rate breakdown exists")
        assert gap2_id > gap1_id

        gaps = C.get_capability_gaps(populated_db)
        # newest first (created_at DESC) -- gap2 was recorded after gap1.
        assert [g["id"] for g in gaps] == [gap2_id, gap1_id]
        assert gaps[0]["turn_id"] == turn2
        assert gaps[0]["question_summary"] == "best performing time control"
        assert gaps[0]["missing_data_description"] == (
            "no per-time-control win-rate breakdown exists")
        assert gaps[1]["turn_id"] == turn1

    def test_get_capability_gaps_respects_limit(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "answer")
        for i in range(5):
            C.record_capability_gap(populated_db, turn_id, f"question {i}", f"missing {i}")
        assert len(C.get_capability_gaps(populated_db, limit=3)) == 3
        assert len(C.get_capability_gaps(populated_db)) == 5

    def test_record_capability_gap_requires_real_turn_id(self, populated_db):
        """board_chat_capability_gaps.turn_id REFERENCES board_chat_turns(id)
        -- this populated_db fixture connection runs with foreign_keys ON
        (see conftest.py), so inserting against a turn_id that doesn't
        exist at all must raise, not silently succeed."""
        from data import board_chat as C
        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                populated_db, 999999, "some question", "some missing data")

    def test_record_capability_gap_rejects_ai_coach_turn_id(self, populated_db):
        """Direct regression test for the schema fix in migration 0036 /
        docs/scoping/ai-coach-board-interaction-implementation-plan-
        2026-07-08.md §0.2: board_chat_capability_gaps.turn_id is FK'd to
        board_chat_turns(id), NOT ai_coach_turns(id) -- reusing
        ai_coach_capability_gaps for board-chat gap reports would have let
        a board_chat_turns.id collide with an unrelated ai_coach_turns.id,
        or (correctly, as tested here) simply fail the FK check when the
        id only exists in the OTHER table. A turn_id that is a real,
        valid ai_coach_turns.id (but not a board_chat_turns.id) must still
        raise IntegrityError against board_chat_capability_gaps -- proving
        the FK is real and scoped to the right table, not just present."""
        from data import ai_coach as ai_coach_data
        from data import board_chat as C
        ai_coach_conv_id = ai_coach_data.start_conversation(populated_db)
        ai_coach_turn_id = ai_coach_data.add_turn(
            populated_db, ai_coach_conv_id, "assistant", "an ai coach reply")

        # Sanity check: this id is real, just in the wrong table.
        assert populated_db.execute(
            "SELECT 1 FROM ai_coach_turns WHERE id = ?", [ai_coach_turn_id]
        ).fetchone() is not None
        assert populated_db.execute(
            "SELECT 1 FROM board_chat_turns WHERE id = ?", [ai_coach_turn_id]
        ).fetchone() is None

        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                populated_db, ai_coach_turn_id, "some question", "some missing data")

    def test_record_feedback_on_assistant_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "Nf3 is strongest.")
        C.record_feedback(populated_db, turn_id, -1)
        row = populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [turn_id]).fetchone()
        assert row[0] == -1

    def test_record_feedback_rejects_invalid_turn_id(self, populated_db):
        from data import board_chat as C
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, 999999, 1)

    def test_record_feedback_rejects_non_assistant_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        user_turn_id = C.add_turn(populated_db, conv_id, "user", "what about e4?")
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, user_turn_id, 1)

    def test_record_feedback_rejects_invalid_value(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, turn_id, 2)

    def test_record_feedback_scoped_to_correct_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        t1 = C.add_turn(populated_db, conv_id, "user", "q1")
        t2 = C.add_turn(populated_db, conv_id, "assistant", "bad advice")
        t3 = C.add_turn(populated_db, conv_id, "assistant", "good advice")
        C.record_feedback(populated_db, t2, -1)
        C.record_feedback(populated_db, t3, 1)

        turns = C.get_turns_for_display(populated_db, conv_id)
        by_id = {t["id"]: t for t in turns}
        assert by_id[t1]["role"] == "user"
        # get_turns_for_display doesn't select feedback (display shape only
        # needs id/role/content/board_directives/created_at) -- confirm the
        # persisted value directly against the table instead.
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t2]).fetchone()[0] == -1
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t3]).fetchone()[0] == 1
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t1]).fetchone()[0] is None
