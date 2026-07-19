"""Constants used across more than one topic module in this package --
promoted out of patterns.py's own top level during the largest-file
modularization split (docs/superpowers/specs/
2026-07-17-largest-file-modularization-design.md). Distinct from the
package-level dashboard/data/_shared.py one level up, which this package's
submodules reach via `from .._shared import ...`.
"""
# Mirrors analysis/sharpness_correlation.py's BUCKETS.
SHARPNESS_BUCKETS = [
    ("flat (<5cp gap)", 0, 5),
    ("mild (5-25cp)", 5, 25),
    ("moderate (25-75cp)", 25, 75),
    ("sharp (75-200cp)", 75, 200),
    ("forcing (200cp+)", 200, 10**9),
]

PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}
