-- Board chat: a game-scoped, multi-turn Claude conversation embedded in
-- Game Detail's variation explorer -- complementary to AI Coach, not a
-- mode of it. See docs/scoping/ai-coach-board-interaction-2026-07-08.md
-- §3 for why this needs its own tables rather than a game_id column
-- bolted onto ai_coach_conversations (that table is deliberately a
-- singleton-style, account-wide relationship, not per-game -- see
-- migration 0034's own comment). Core (MIT) plumbing only -- the tool
-- set, prompts, and Claude wiring are chesswright_pro/board_chat.py, a
-- later, private phase, same split as 0034/ai_coach.py.
CREATE TABLE IF NOT EXISTS board_chat_conversations (
    id         INTEGER PRIMARY KEY,
    game_id    TEXT NOT NULL REFERENCES games(id),
    started_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_chat_conversations_game
    ON board_chat_conversations(game_id);

CREATE TABLE IF NOT EXISTS board_chat_turns (
    id               INTEGER PRIMARY KEY,
    conversation_id  INTEGER NOT NULL REFERENCES board_chat_conversations(id),
    role             TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content          TEXT NOT NULL,
    board_directives TEXT,  -- JSON array of {tool, ...} dicts shown alongside
                             -- this turn (show_arrow/highlight_squares calls),
                             -- or NULL. See board_chat.py's add_turn().
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_chat_turns_conversation
    ON board_chat_turns(conversation_id);

-- A DEDICATED capability-gap log, deliberately NOT a reuse of
-- ai_coach_capability_gaps despite the scoping doc's original §3/§11
-- recommendation to share it: migration 0035 gives that table's turn_id
-- a hard `REFERENCES ai_coach_turns(id)` FK, and every connection this
-- app opens runs with PRAGMA foreign_keys = ON (db.py) -- a
-- board_chat_turns.id inserted there would violate that FK. Same shape
-- as 0035 otherwise.
CREATE TABLE IF NOT EXISTS board_chat_capability_gaps (
    id                        INTEGER PRIMARY KEY,
    turn_id                   INTEGER NOT NULL REFERENCES board_chat_turns(id),
    question_summary          TEXT NOT NULL,
    missing_data_description  TEXT NOT NULL,
    created_at                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_chat_capability_gaps_turn
    ON board_chat_capability_gaps(turn_id);
