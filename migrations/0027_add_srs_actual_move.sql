-- Store the move the player actually played in their game for each SRS card.
-- NULL for repertoire-hole cards (no single game move applies there).
ALTER TABLE srs_cards ADD COLUMN actual_move_san TEXT;
