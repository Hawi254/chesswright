PRAGMA journal_mode = WAL;  -- better concurrent read/write behavior for the long engine pass later

CREATE TABLE IF NOT EXISTS games (
    id                  TEXT PRIMARY KEY,      -- game id: parsed from the Site URL (lichess)
                                                 -- or the Link URL (chess.com -- Site is just
                                                 -- the literal string "Chess.com" there)
    event               TEXT,
    site                TEXT,
    pgn_raw             TEXT,                  -- full original PGN text, kept for reference/debugging

    -- raw header fields
    white               TEXT,
    black               TEXT,
    result              TEXT,
    white_elo           INTEGER,
    black_elo           INTEGER,
    white_rating_diff   INTEGER,
    black_rating_diff   INTEGER,
    variant             TEXT,
    time_control_raw    TEXT,
    eco                 TEXT,
    opening_raw         TEXT,
    termination         TEXT,

    -- date/time, split out for easy grouping
    utc_date            TEXT,
    utc_time            TEXT,
    year                INTEGER,
    month               INTEGER,
    day_of_week         INTEGER,               -- 0=Monday .. 6=Sunday
    hour_utc            INTEGER,

    -- time control, parsed
    base_seconds        INTEGER,
    increment_seconds   INTEGER,
    time_control_category TEXT,                -- bullet/blitz/rapid/classical/correspondence

    -- opening, normalized
    opening_family      TEXT,                  -- e.g. "Italian Game" stripped of ": variation" suffix

    -- derived, relative to PLAYER_NAME
    player_color        TEXT,                  -- 'white' or 'black'
    player_rating        INTEGER,
    opponent_rating       INTEGER,
    opponent_name         TEXT,
    rating_diff          INTEGER,              -- player_rating - opponent_rating
    player_rating_change  INTEGER,
    outcome_for_player    TEXT,                -- 'win' / 'loss' / 'draw'

    num_plies            INTEGER,

    -- engine-analysis bookkeeping (Phase 2 will use/update these; defined now so schema is stable)
    analysis_status       TEXT DEFAULT 'pending',  -- pending / in_progress / done / failed
    last_analyzed_ply      INTEGER DEFAULT 0,
    queue_order            INTEGER,             -- stratified processing order, computed at ingestion
    analysis_started_at    TEXT,
    analysis_completed_at   TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS moves (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL REFERENCES games(id),
    ply             INTEGER NOT NULL,           -- 1-indexed, both colors
    move_number     INTEGER NOT NULL,           -- full move number (1,1,2,2,3,3...)
    color           TEXT NOT NULL,              -- 'w' or 'b'
    san             TEXT NOT NULL,
    uci             TEXT,
    from_square     TEXT,
    to_square       TEXT,
    piece           TEXT,                       -- piece type that moved (P,N,B,R,Q,K)
    is_capture      INTEGER DEFAULT 0,
    is_check        INTEGER DEFAULT 0,
    is_castle       INTEGER DEFAULT 0,
    is_promotion    INTEGER DEFAULT 0,
    clock_seconds   INTEGER,                    -- remaining clock after this move, from %clk
    time_spent_seconds REAL,                     -- derived: prev clock - this clock + increment

    -- engine fields, NULL until Phase 2 fills them in
    eval_cp         INTEGER,
    eval_mate       INTEGER,
    best_move_san   TEXT,
    cpl             INTEGER,
    classification  TEXT,                       -- best/excellent/good/inaccuracy/mistake/blunder
    win_prob_before REAL,
    win_prob_after  REAL,

    UNIQUE(game_id, ply)
);

CREATE INDEX IF NOT EXISTS idx_games_queue ON games(analysis_status, queue_order);
CREATE INDEX IF NOT EXISTS idx_moves_game ON moves(game_id, ply);
