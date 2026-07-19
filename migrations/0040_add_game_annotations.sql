-- Mainline (non-variation) per-position annotations -- new in Game
-- Detail Slice 4. A separate table rather than extending
-- variation_annotations with nullable dual-key columns: keeps
-- variation_annotations' semantics (and variation_to_pgn's
-- move-index-scoped annotation dict) unambiguous -- every reader of
-- that table can keep assuming a row always belongs to exactly one
-- variation. See
-- docs/superpowers/specs/2026-07-14-game-detail-slice4-annotations-design.md
-- "Backend: mainline annotations" for the full rejected-alternative
-- reasoning (nullable variation_id + a CHECK constraint was considered
-- and rejected as a schema-level workaround for a conceptually
-- different kind of annotation).

CREATE TABLE IF NOT EXISTS game_annotations (
    id           TEXT    PRIMARY KEY,
    game_id      TEXT    NOT NULL,
    ply          INTEGER NOT NULL,
    glyph        TEXT,
    comment      TEXT,
    ai_comment   TEXT,
    ai_model     TEXT,
    generated_at TEXT,
    UNIQUE (game_id, ply),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);
