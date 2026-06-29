-- Saved game variations and per-move annotations (v0.1.12).
-- A variation is a line of moves branching from a specific ply in a game,
-- created interactively via the chessboard component. Annotations attach
-- a glyph, free-text comment, and/or AI comment to any position within a
-- saved variation.

CREATE TABLE IF NOT EXISTS variations (
    id          TEXT    PRIMARY KEY,
    game_id     TEXT    NOT NULL,
    branch_ply  INTEGER NOT NULL,
    branch_fen  TEXT    NOT NULL,
    moves_json  TEXT    NOT NULL DEFAULT '[]',
    title       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variation_annotations (
    id           TEXT    PRIMARY KEY,
    variation_id TEXT    NOT NULL,
    move_index   INTEGER NOT NULL,
    glyph        TEXT,
    comment      TEXT,
    ai_comment   TEXT,
    ai_model     TEXT,
    generated_at TEXT,
    UNIQUE (variation_id, move_index),
    FOREIGN KEY (variation_id) REFERENCES variations(id) ON DELETE CASCADE
);
