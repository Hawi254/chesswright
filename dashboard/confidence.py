"""Shared sample-size confidence tiering + badge rendering.

Roadmap §15 unit #1 ("Reconciled Start-Here Sequence", BRIEF.md/
docs/implementation_roadmap.md). Before this module, six different
dashboard/data/*.py functions each hard-coded their own single "enough
data?" cutoff (MIN_PIECE_MOVES, min_games=5, etc.) with no shared
vocabulary for "yes, but only barely" vs. "yes, solidly" -- just a binary
gate. This module gives them one place to express that same cutoff as a
tier scheme, without changing any existing gating behavior: the "low"
tier threshold is always set to today's existing hard cutoff value at
every migrated call site.

Tier scheme: given a caller-supplied "low" threshold, medium and high are
derived by one fixed multiplier scheme rather than picked ad hoc per
module -- medium = 3x low, high = 8x low. Use default_thresholds(low) to
get that derived dict instead of writing the 3x/8x math out per call
site.
"""
from __future__ import annotations

MEDIUM_MULTIPLIER = 3
HIGH_MULTIPLIER = 8


def default_thresholds(low: int | float) -> dict:
    """Derive the standard {low, medium, high} thresholds dict from a
    single low cutoff, using this module's 3x/8x scheme. Callers that
    need a bespoke medium/high (rare) can still build their own dict by
    hand -- confidence_tier() accepts thresholds in any dict order."""
    return {
        "low": low,
        "medium": low * MEDIUM_MULTIPLIER,
        "high": low * HIGH_MULTIPLIER,
    }


def confidence_tier(n, thresholds: dict) -> str:
    """Return the name of the highest tier in *thresholds* whose value
    *n* meets or exceeds, or "insufficient" if *n* is below the smallest
    ("low") threshold. *thresholds* is a {tier_name: cutoff} mapping and
    may be passed in any order -- sorted internally by cutoff value so
    callers don't need to pre-sort."""
    ordered = sorted(thresholds.items(), key=lambda kv: kv[1])
    tier = "insufficient"
    for name, cutoff in ordered:
        if n >= cutoff:
            tier = name
    return tier


# Tier -> (chip CSS class, label). Reuses theme.py's existing .chip/
# .chip-positive/.chip-neutral/.chip-negative pattern (see BADGE_CHIPS,
# chip_row_html) plus one new muted variant added alongside them in
# theme.py's CSS block -- "one pattern, not ad hoc per panel." No entry
# for "insufficient": call sites that reach that tier already skip
# rendering entirely (a finding returns None, thin_data_message() is
# shown instead) rather than showing a muted badge next to nothing.
_TIER_CHIPS = {
    "high": ("High confidence", "chip-positive"),
    "medium": ("Medium confidence", "chip-neutral"),
    "low": ("Low confidence", "chip-muted"),
}


def confidence_badge_html(tier: str) -> str:
    """Small chip/badge <span> for a confidence tier. Returns "" for
    "insufficient" or any unrecognized tier name -- callers should skip
    rendering the badge entirely in that case, same convention as
    theme.chip_row_html() returning "" when no badges qualify."""
    entry = _TIER_CHIPS.get(tier)
    if entry is None:
        return ""
    label, cls = entry
    return f'<span class="chip {cls}">{label}</span>'
