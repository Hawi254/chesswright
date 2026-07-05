-- SRS (Spaced Repetition System) drill cards and review log.
-- Cards are chess positions from the player's game history (motif misses,
-- decisive moments, repertoire holes). Scheduling uses a simplified SM-2
-- algorithm: ease_factor and interval_days stored per card, updated after
-- each review. UNIQUE(fen) prevents the same position being drilled twice.
CREATE TABLE IF NOT EXISTS srs_cards (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fen              TEXT    NOT NULL,
    source           TEXT    NOT NULL,
    best_move_san    TEXT    NOT NULL,
    context          TEXT,
    ease_factor      REAL    NOT NULL DEFAULT 2.5,
    interval_days    INTEGER NOT NULL DEFAULT 0,
    repetitions      INTEGER NOT NULL DEFAULT 0,
    next_due         TEXT    NOT NULL,
    added_at         TEXT    NOT NULL,
    last_reviewed_at TEXT,
    UNIQUE(fen)
);

CREATE TABLE IF NOT EXISTS srs_reviews (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id             INTEGER NOT NULL REFERENCES srs_cards(id),
    reviewed_at         TEXT    NOT NULL,
    rating              INTEGER NOT NULL CHECK(rating IN (0, 1, 2, 3)),
    interval_days_after INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_srs_cards_next_due ON srs_cards(next_due);
