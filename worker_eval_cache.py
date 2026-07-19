"""batch_eval_cache fetch/store and the raw-engine-lines-to-JSON-payload
helpers -- one of four sibling modules split out of worker.py (largest-
file modularization, 2026-07-17). A leaf module: imports nothing from
this split's other three siblings, only stdlib `json`.
"""
import json

# Cache/consult batch_eval_cache only for plies at or below this cutoff. Dup
# mass is front-loaded (measured ~70% exact-FEN repeat rate for ply<=20,
# falling off sharply deeper into the game -- see migrations/0033 +
# explore/batch-cloud-eval/DEDUP_CACHE_PLAN.md), so a shallow cutoff captures
# almost all of the reuse benefit while keeping the table small. A constant,
# not a config knob -- revisit by editing this, not config.yaml.
REUSE_EVAL_MAX_PLY = 24


def score_to_fields(score, mover_color):
    """Score relative to the player to move. Returns (eval_cp, eval_mate)."""
    pov = score.pov(mover_color)
    if pov.is_mate():
        return None, pov.mate()
    return pov.score(), None


def fetch_cached_eval(conn, fen_before, engine_version, depth, multipv):
    """PK lookup into batch_eval_cache. Returns the parsed lines_json -- a
    list of dicts, one per pv_rank ascending, shaped like
    lines_payload_from_engine_lines()'s output -- on a hit, or None on a
    miss. engine_version/depth/multipv are part of the key, so an engine
    upgrade or a config change is a clean miss (falls through to a fresh
    search) rather than mixing eval scales from a different search."""
    row = conn.execute("""
        SELECT lines_json FROM batch_eval_cache
        WHERE fen_before=? AND engine_version=? AND requested_depth=? AND multipv=?
    """, (fen_before, engine_version, depth, multipv)).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def store_cached_eval(conn, fen_before, engine_version, depth, multipv, lines_payload):
    """INSERT OR IGNORE -- first-analysis-wins if this exact key is ever
    raced (not possible with today's single-engine-process worker, but
    cheap insurance against ever becoming one)."""
    conn.execute("""
        INSERT OR IGNORE INTO batch_eval_cache
            (fen_before, engine_version, requested_depth, multipv, lines_json)
        VALUES (?,?,?,?,?)
    """, (fen_before, engine_version, depth, multipv, json.dumps(lines_payload)))


def lines_payload_from_engine_lines(lines, board, mover_color, pv_max_len):
    """Builds the JSON-able per-rank payload batch_eval_cache stores --
    eval_cp/eval_mate/move_san/pv_san/score_is_exact for every multipv
    rank, ascending. Excludes telemetry (seldepth, nodes, ...): that
    describes THIS search call, not the position, so it has no business
    being replayed onto a future cache hit (see migrations/0033)."""
    payload = []
    for rank, line in enumerate(lines, start=1):
        line_cp, line_mate = score_to_fields(line["score"], mover_color)
        line_exact = 0 if (line.get("upperbound") or line.get("lowerbound")) else 1
        line_pv = line.get("pv", [])[:pv_max_len]
        lb = board.copy()
        line_san_list = []
        line_best_san = None
        for i, mv in enumerate(line_pv):
            s = lb.san(mv)
            if i == 0:
                line_best_san = s
            line_san_list.append(s)
            lb.push(mv)
        payload.append({
            "pv_rank": rank, "eval_cp": line_cp, "eval_mate": line_mate,
            "move_san": line_best_san, "pv_san": line_san_list,
            "score_is_exact": line_exact,
        })
    return payload
