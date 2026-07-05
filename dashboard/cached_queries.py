"""Shared @st.cache_data wrappers for the two most expensive cross-page
queries. st.cache_data keys its cache on FUNCTION IDENTITY, so a
copy-pasted `cached_headline_stats` in each view module is six separate
cache entries -- six full computations of the identical result (~0.4s
each), and worse for `cached_career_findings` (~4.3s each, previously
recomputed from scratch on Overview, Insights, AND Ask's data brief).
Same hazard _common.get_connections's docstring already documents for
st.cache_resource, applied to cache_data.

Any view needing these must import THIS module's wrappers rather than
defining its own -- a new local `@st.cache_data def cached_headline_...`
silently reintroduces the duplicate-computation bug this module exists
to fix.

Lives in dashboard/ (not dashboard/data/) because it imports streamlit;
the data package stays streamlit-free and testable without a Streamlit
runtime.
"""
import streamlit as st

import data


@st.cache_data(show_spinner="Loading your headline stats…")
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


@st.cache_data(show_spinner="Scanning your games for career findings…")
def cached_career_findings(_duck_conn, baseline_blunder_rate):
    return data.get_career_findings(_duck_conn, baseline_blunder_rate)
