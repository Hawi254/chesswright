-- Free byproducts of the search call: seldepth is in the same info dict,
-- search_time_ms is just wall-clock around a call we're already making.
ALTER TABLE moves ADD COLUMN seldepth INTEGER;
ALTER TABLE moves ADD COLUMN search_time_ms INTEGER;
