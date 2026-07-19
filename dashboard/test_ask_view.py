"""Unit tests for ask_view.py's remaining Streamlit-only surface after the
data-brief assembly was extracted to dashboard/data/ask_brief.py -- see
docs/superpowers/specs/2026-07-17-ask-page-design.md.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.unit
def test_build_data_brief_delegates_to_extracted_module(monkeypatch):
    import streamlit as st
    import ask_view
    import data

    # _build_data_brief's @st.cache_data has both params underscore-prefixed
    # (connections aren't hashable), so with zero hashable args its cache key
    # is constant process-wide -- whichever test calls it first "wins" the
    # cache for every later test in the same pytest run. Found live: this
    # test failed only when tests/unit/test_ask_brief.py happened to run
    # first and populated the cache with a real (non-sentinel) brief.
    st.cache_data.clear()

    monkeypatch.setattr(data, "build_ask_data_brief", lambda duck_conn, sqlite_conn: "SENTINEL BRIEF")

    result = ask_view._build_data_brief("fake_duck_conn", "fake_sqlite_conn")

    assert result == "SENTINEL BRIEF"
