"""Stockfish/UCI engine discovery, configuration, and validation, plus
now_iso() -- one of four sibling modules split out of worker.py (largest-
file modularization, 2026-07-17). now_iso() lives here rather than
staying in worker.py itself (as the design spec originally proposed)
because worker_analysis.py's analyze_game() and worker_calibration.py's
calibrate() both need it, and worker.py needs to import FROM those two
files -- keeping now_iso in worker.py would make that a circular import.
This file has no dependency on any of this split's other three siblings,
which is what makes it safe for all of them (and worker.py itself) to
import from.
"""
import datetime
import os
import shutil

import chess
import chess.engine


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def find_engine_path(explicit_path):
    if explicit_path:
        return explicit_path
    for candidate in ("stockfish", "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        found = shutil.which(candidate) or (candidate if candidate.startswith("/") else None)
        if found:
            import os
            if os.path.exists(found) and os.access(found, os.X_OK):
                return found
    return None


def configure_supported(engine, desired: dict):
    """Like engine.configure(desired), but silently drops any option name
    the connected engine doesn't actually report supporting, rather than
    letting python-chess raise. "Threads"/"Hash" are near-universal across
    classical UCI engines (Stockfish, Komodo, Ethereal, ...) but not every
    UCI-compliant engine exposes both -- some NN-based engines don't -- and
    this app now accepts ANY UCI engine the user points it at (the
    Settings/onboarding engine picker), not just Stockfish specifically."""
    supported = {name: value for name, value in desired.items() if name in engine.options}
    if supported:
        engine.configure(supported)


def validate_engine_path(path: str) -> str:
    """Confirms `path` is a real, working UCI engine by actually performing
    the UCI handshake (popen_uci already does this) -- returns the engine's
    self-reported name (engine.id["name"]), or raises RuntimeError with a
    clear message on any failure. Used by the engine-picker UI (onboarding
    + Settings) to reject a wrong file before it's accepted as engine.path,
    rather than discovering the problem on the next real analysis run."""
    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
    except Exception as e:
        raise RuntimeError(
            f"Couldn't start this as a UCI chess engine: {e}") from e
    try:
        return engine.id.get("name", "unknown engine")
    finally:
        engine.quit()
