-- Opening Tree explorer point-looks-up moves by exact fen_before on every
-- row click (data/openings.py's get_opening_moves_from_fen). Without this
-- index the query has nothing to seek on -- confirmed live: DuckDB's
-- ATTACHed sqlite_scanner doesn't push filter predicates down as index
-- seeks across the ATTACH boundary (same phenomenon already documented for
-- zobrist_hash in get_most_repeated_positions), so that call path was moved
-- to query via the native sqlite3 connection instead, which DOES use this
-- index (measured: ~1s full scan -> ~0.2s worst case, microseconds typical).
CREATE INDEX IF NOT EXISTS idx_moves_fen_before ON moves(fen_before);
