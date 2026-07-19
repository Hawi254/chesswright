-- AI Coach (Pro feature): a conversational chat assistant over a player's own
-- chess-analysis data. This app has exactly one local player per database, so
-- ai_coach_profile is a singleton row keyed id=1 -- a rolling summary of what
-- the coach has learned about the player, regenerated periodically from
-- conversation history. ai_coach_conversations/ai_coach_turns hold the actual
-- multi-turn chat log, including thumbs up/down feedback per assistant turn
-- so a later profile regeneration can avoid reinforcing advice the player
-- marked wrong. This migration is core (MIT) plumbing only -- the tool set,
-- prompts, and Claude API wiring that use these tables are a later, private
-- chesswright_pro phase.
CREATE TABLE IF NOT EXISTS ai_coach_profile (
    id           INTEGER PRIMARY KEY,
    summary_text TEXT NOT NULL,
    source_turns INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    model        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_coach_conversations (
    id         INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_coach_turns (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES ai_coach_conversations(id),
    role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    feedback        INTEGER  -- NULL (none), 1 (thumbs up), -1 (thumbs down); only meaningful when role='assistant'
);
CREATE INDEX IF NOT EXISTS idx_ai_coach_turns_conversation ON ai_coach_turns(conversation_id);
