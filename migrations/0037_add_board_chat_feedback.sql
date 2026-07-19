-- Board Chat feedback: thumbs up/down per assistant turn, mirroring
-- migration 0034's ai_coach_turns.feedback column exactly. On thumbs-down,
-- the Pro UI (chesswright_pro/board_chat.py) also auto-logs a capability
-- gap via record_capability_gap() into the existing
-- board_chat_capability_gaps table (migration 0036) -- this is the
-- "gets better over time" mechanism for this per-game-scoped feature, not
-- a rolling cross-session profile (that's explicitly out of scope; see
-- docs/scoping/board-chat-plans-feedback-cache-2026-07-09.md §3).
ALTER TABLE board_chat_turns ADD COLUMN feedback INTEGER; -- NULL (none), 1 (thumbs up), -1 (thumbs down); only meaningful when role='assistant'
