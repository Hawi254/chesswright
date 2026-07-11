"""Unit tests for dashboard/data/search.py (Global Search, roadmap §25).
Pure functions -- no Streamlit runtime, no DB fixture needed, simpler
than tests/unit/test_insights.py's mixed pattern since search.py takes
only plain Python/pandas values.
"""
import pandas as pd

from data.search import build_dynamic_candidates, rank_candidates


def _openings_df(rows):
    return pd.DataFrame(rows, columns=["opening_family", "player_color"])


def test_build_dynamic_candidates_dedupes_opening_family_across_colors():
    openings_df = _openings_df([
        ("Sicilian Defense", "white"),
        ("Sicilian Defense", "black"),
        ("Queen's Gambit", "white"),
    ])
    findings = []

    candidates = build_dynamic_candidates(openings_df, findings)

    opening_candidates = [c for c in candidates if c["category"] == "opening"]
    assert len(opening_candidates) == 2
    titles = {c["title"] for c in opening_candidates}
    assert titles == {"Sicilian Defense", "Queen's Gambit"}
    for c in opening_candidates:
        assert c["url_path"] == "openings"
        assert c["preset"] == {"opening_family": c["title"]}


def test_build_dynamic_candidates_maps_finding_titles():
    openings_df = _openings_df([])
    findings = [
        {"title": "Piece blunder hot-spot", "severity": "high"},
        {"title": "Toughest opponent", "severity": "medium"},
    ]

    candidates = build_dynamic_candidates(openings_df, findings)

    finding_candidates = [c for c in candidates if c["category"] == "finding"]
    assert len(finding_candidates) == 2
    assert {c["title"] for c in finding_candidates} == {
        "Piece blunder hot-spot", "Toughest opponent"}
    for c in finding_candidates:
        assert c["url_path"] == "insights"
        assert c["preset"] is None


def test_rank_candidates_empty_query_returns_nothing():
    candidates = [{"category": "page", "title": "Overview", "url_path": "overview"}]
    assert rank_candidates("", candidates) == []
    assert rank_candidates("   ", candidates) == []


def test_rank_candidates_preserves_full_dicts_not_just_titles():
    candidates = [
        {"category": "opening", "title": "Sicilian Defense", "url_path": "openings",
         "preset": {"opening_family": "Sicilian Defense"}},
        {"category": "page", "title": "Settings", "url_path": "settings"},
    ]
    results = rank_candidates("sicilian", candidates)
    assert len(results) == 1
    assert results[0] is candidates[0]
    assert results[0]["preset"] == {"opening_family": "Sicilian Defense"}


def test_rank_candidates_respects_limit():
    candidates = [
        {"category": "opening", "title": f"Opening Variation {i}", "url_path": "openings"}
        for i in range(20)
    ]
    results = rank_candidates("Opening Variation", candidates, limit=3)
    assert len(results) == 3


def test_rank_candidates_excludes_unrelated_below_score_cutoff():
    candidates = [
        {"category": "page", "title": "Settings", "url_path": "settings"},
        {"category": "page", "title": "Overview", "url_path": "overview"},
    ]
    results = rank_candidates("zzzzqqqqxxxx totally unrelated", candidates)
    assert results == []
