-- AI Coach capability-gap telemetry: a structured record of turns where
-- Claude itself reported it could not fully answer using its available
-- tools, distinct from ai_coach_turns.feedback (a thumbs-down says an
-- answer was unhelpful; a capability-gap row says WHY in the model's own
-- words, at the moment it happened, without needing to re-read the
-- transcript). Local-only, never synced -- same posture as every other
-- table in this database. See BRIEF.md / ai-coach-robustness-brainstorm
-- 2026-07-08 §4 for the design rationale.
CREATE TABLE IF NOT EXISTS ai_coach_capability_gaps (
    id                        INTEGER PRIMARY KEY,
    turn_id                   INTEGER NOT NULL REFERENCES ai_coach_turns(id),
    question_summary          TEXT NOT NULL,
    missing_data_description  TEXT NOT NULL,
    created_at                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_coach_capability_gaps_turn
    ON ai_coach_capability_gaps(turn_id);
