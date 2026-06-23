-- Confirmed via direct inspection of engine.analyse() output (not assumed):
-- hashfull/tbhits/nps/time are global to the whole search call, identical
-- across all multipv ranks -- so they belong on `moves` only, once per
-- position, not duplicated per line.
ALTER TABLE moves ADD COLUMN hashfull INTEGER;            -- transposition table fill, per-mille
ALTER TABLE moves ADD COLUMN tbhits INTEGER;               -- tablebase hits (0 unless you add Syzygy later)
ALTER TABLE moves ADD COLUMN nps INTEGER;                   -- engine-reported nodes/sec
ALTER TABLE moves ADD COLUMN engine_reported_time_ms INTEGER; -- engine's own timing, vs our wall-clock search_time_ms
ALTER TABLE moves ADD COLUMN score_is_exact INTEGER;          -- 0 if score was an upper/lower bound, not exact

-- seldepth DOES vary slightly per rank (confirmed empirically) so it's kept
-- per-line here; nodes does NOT vary per rank (it was a global stat
-- incorrectly duplicated per row) so it's removed.
ALTER TABLE move_lines ADD COLUMN score_is_exact INTEGER;
ALTER TABLE move_lines ADD COLUMN seldepth INTEGER;
ALTER TABLE move_lines DROP COLUMN nodes;
