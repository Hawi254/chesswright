-- Number of legal replies at fen_before, computed via python-chess. Only
-- populated for moves with time_spent_seconds = 0 (the "instant move"
-- candidate population -- see BRIEF.md's premove-detection design): a
-- position with few legal replies is more plausible as a genuinely
-- pre-queued move than one with dozens of options. NULL on every other
-- move -- this is deliberately narrow (like the existing motif column),
-- not computed for all 2.3M rows. Populated going forward by ingest.py at
-- ingest time; backfill_legal_reply_count.py fills in pre-existing rows.
ALTER TABLE moves ADD COLUMN legal_reply_count INTEGER;
