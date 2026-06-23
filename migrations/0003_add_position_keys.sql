-- Position-identity fields for two different kinds of insight:
--
-- zobrist_hash: exact position fingerprint (piece placement, side to move,
-- castling rights, en passant -- the standard chess "transposition key").
-- Most valuable in the opening, where you genuinely revisit the exact same
-- position across hundreds of games via a repertoire. Computed via
-- chess.polyglot.zobrist_hash(), the same tool used by opening books.
--
-- material_sig: compact material-balance signature (e.g. "R2B1N2P8vR2B2N1P7"),
-- used to cluster structurally similar middlegame/endgame positions that
-- will almost never share an exact FEN but represent the same kind of
-- position (rook endgame, opposite-coloured bishops, queenless middlegame...).
--
-- Both are derivable purely from fen_before, already stored by the worker --
-- no engine re-run required, hence a plain backfill script rather than a
-- change to worker.py.
ALTER TABLE moves ADD COLUMN zobrist_hash INTEGER;
ALTER TABLE moves ADD COLUMN material_sig TEXT;

CREATE INDEX IF NOT EXISTS idx_moves_zobrist ON moves(zobrist_hash);
CREATE INDEX IF NOT EXISTS idx_moves_material_sig ON moves(material_sig);
