"""Response-shaping helpers shared across router modules. Moved out of
api/main.py (docs/superpowers/specs/2026-07-17-api-main-router-split-design.md)
so every router module can import them without importing all of main.py's
routes.
"""
import math


def _json_safe(value):
    """Recursively replaces NaN floats with None. Unanalyzed moves (past
    a game's last_analyzed_ply) leave pandas' missing-value marker (NaN)
    in columns like cpl/win_prob_before/win_prob_after -- found live
    against the real dev chess.db, where any such game 500'd because
    starlette's JSONResponse sets allow_nan=False and json.dumps raises
    on NaN rather than silently emitting invalid JSON for it."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _narrative_response(cached):
    if cached is None:
        return {"narrative": None, "generated_at": None}
    response_text, generated_at = cached
    return {"narrative": response_text, "generated_at": generated_at}
