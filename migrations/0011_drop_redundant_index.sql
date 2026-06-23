-- idx_move_lines_move(move_id) is redundant: the UNIQUE(move_id, pv_rank)
-- constraint already creates an index with move_id as its leading column,
-- which SQLite already uses for "WHERE move_id = ?" lookups. Keeping both
-- just pays index-maintenance cost on every insert for no read benefit.
DROP INDEX IF EXISTS idx_move_lines_move;
