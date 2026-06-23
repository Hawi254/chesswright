-- Real data-quality fix: lichess arena tournaments let a player "berserk"
-- at game start (halves their starting clock, cancels increment for that
-- game). No PGN tag exists for this -- derived in ingest.py from each
-- color's first %clk reading vs base_seconds (chess_utils.detect_berserk).
-- NULL means "couldn't determine" (no clock data), not "confirmed not berserk".
ALTER TABLE games ADD COLUMN white_berserk INTEGER;
ALTER TABLE games ADD COLUMN black_berserk INTEGER;
