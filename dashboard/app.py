#!/usr/bin/env python3
"""
Career Dashboard entry point. Phase 6c.4: the Career Dashboard's old
9-tab single page is now 6 real pages (Overview, Patterns & Tendencies,
Openings & Repertoire, Matchups & Opponents, Game Endings, Tactical
Highlights), per the approved 6c.1 information architecture regroup --
each lives in its own module (overview_view.py, patterns_view.py, etc.),
following the same pattern game_explorer_view.py/game_detail_view.py
established in 6c.3. This file just owns shared setup (connections,
warm_up, the Refresh button) and the navigation wiring.

Run: streamlit run dashboard/app.py
"""
import sys
import pathlib
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st

import analytics
import theme
from migrate import migrate
from _common import get_config, get_connections, resolve_db_path
import overview_view
import patterns_view
import openings_view
import matchups_view
import game_endings_view
import tactical_highlights_view
import game_explorer_view
import game_detail_view
import settings_view
import onboarding_view
import analysis_jobs_view
import annotate
import job_runner
import joblock

st.set_page_config(page_title="Chesswright", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)

# A truly fresh install has a database file with no tables at all yet --
# every warm_up()/page query below assumes games/moves exist (even if
# empty). Migrating here (idempotent, see migrate.py) guarantees that's
# true before anything else touches the database, instead of every page
# needing its own "does this table exist yet" guard.
migrate(resolve_db_path())

sqlite_conn, duck_conn = get_connections()

# Decided ONCE per session, not recomputed every rerun -- the wizard
# itself adds games and sets player.name as it progresses (the fetch
# step alone is enough to flip both conditions below to "false"), so
# recomputing this live would yank the user off the Setup page and back
# to Overview mid-wizard, well before calibration or the batch run even
# happen. Freezing it for the session means only the wizard's own
# explicit "Go to dashboard" button (a real st.switch_page call, not a
# default-page fallback) ever actually leaves Setup once it's started.
if "needs_onboarding" not in st.session_state:
    cfg_for_onboarding_check = get_config()
    _games_count = sqlite_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    st.session_state["needs_onboarding"] = (
        (_games_count == 0) or (cfg_for_onboarding_check["player"]["name"] == "CHANGE_ME"))
NEEDS_ONBOARDING = st.session_state["needs_onboarding"]


# First load after a server (re)start does real one-time work (building
# structure_ctx/session_ctx by scanning the full moves table once) --
# measured at ~20s. Streamlit's own "Running" indicator covers reruns,
# but a first-ever load with no prior context is worth a visible message:
# this user has killed a process before assuming a silent wait meant it
# had hung (see CLAUDE.md feedback), so don't leave this load looking blank.
def warm_up():
    """6c.5: st.status with explicit step labels instead of one bare
    st.spinner for the whole ~20s -- a single static spinner message for
    20 seconds reads the same as a hung process to this user (see
    CLAUDE.md's "long-running batches" feedback); concrete step-by-step
    text gives genuine, truthful progress instead of just "still alive"
    animation."""
    cfg = get_config()
    with st.status("Building session/structure caches from the full game history "
                    "(one-time after a restart, ~20s -- subsequent loads are fast)...",
                    expanded=True) as status:
        status.write("Scanning material structures (middlegame/endgame signatures)...")
        analytics.ensure_structure_ctx(sqlite_conn, cfg)
        status.write("Scanning session/tilt context (game-by-game sequencing)...")
        analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
        status.update(label="Caches ready.", state="complete", expanded=False)
    st.session_state["warmed_up"] = True
    st.session_state["last_refreshed"] = datetime.datetime.now()


if not NEEDS_ONBOARDING and "warmed_up" not in st.session_state:
    warm_up()

# New games synced in via sync.py (Phase 7) won't appear without this:
# st.cache_data has no ttl, and structure_ctx/session_ctx are temp tables
# built once per connection and never rebuilt on their own (see
# get_connections()'s docstring in _common.py). A manual button is
# deliberate, not an oversight -- given the user's actual usage pattern
# (periodic batch syncs, not live play-tracking), an explicit refresh is
# simpler and cheaper than re-running the ~20s structure rebuild on some
# unlucky page load via a ttl.
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    sqlite_conn.execute("DROP TABLE IF EXISTS structure_ctx")
    sqlite_conn.execute("DROP TABLE IF EXISTS session_ctx")
    warm_up()  # warm_up() already shows its own st.status steps
    st.rerun()
if "last_refreshed" in st.session_state:
    st.sidebar.caption(f"Last refreshed: {st.session_state['last_refreshed']:%Y-%m-%d %H:%M:%S}")


@st.fragment(run_every="5s")
def _sidebar_job_status():
    """Persistent indicator, visible from every page -- not a toast,
    since a batch running (or games piling up unannotated) while the
    user is elsewhere in the app is exactly the kind of state a one-shot
    toast (confirmed live: doesn't survive a rerun, let alone a page
    navigation) can't be relied on to surface. Mirrors the "Refresh
    data"/"Last refreshed" pattern just above, the one place this app
    already does a persistent sidebar status."""
    # A fragment can't call st.sidebar.X()/`with st.sidebar:` itself --
    # confirmed live, both raise the same StreamlitAPIException. The
    # `with st.sidebar:` has to wrap the CALL to this fragment function
    # instead (see below), with the fragment body just using plain
    # st.info/st.caption -- whatever container the fragment is called
    # from is where its output lands.
    if job_runner.is_running():
        state = job_runner.get_state()
        st.info(f"Analysis running: {state.get('games_done', 0)} game(s) so far.")
    else:
        lock_info = joblock.status()
        if lock_info is not None and lock_info.alive:
            st.warning(f"Analysis running (pid {lock_info.pid}, outside this app).")

    awaiting = annotate.count_games_awaiting_annotation(sqlite_conn)
    if awaiting:
        st.caption(f"{awaiting} game(s) awaiting annotation -- see Analysis Jobs.")


if not NEEDS_ONBOARDING:
    with st.sidebar:
        _sidebar_job_status()


# ---------- Navigation ----------
# visibility="hidden" -- Game Detail is reachable only via st.switch_page
# from a row click (Game Explorer, Tactical Highlights, Matchups &
# Opponents' comeback/collapse lists, the Overview "most dramatic game"
# teaser), never a sidebar nav item itself.
detail_page = st.Page(game_detail_view.render, title="Game Detail",
                       url_path="game-detail", visibility="hidden")
overview_page = st.Page(lambda: overview_view.render(overview_page, detail_page),
                         title="Overview", url_path="overview", default=not NEEDS_ONBOARDING)
patterns_page = st.Page(patterns_view.render, title="Patterns & Tendencies",
                         url_path="patterns")
openings_page = st.Page(openings_view.render, title="Openings & Repertoire",
                         url_path="openings")
matchups_page = st.Page(lambda: matchups_view.render(matchups_page, detail_page),
                         title="Matchups & Opponents", url_path="matchups")
endings_page = st.Page(game_endings_view.render, title="Game Endings",
                        url_path="game-endings")
highlights_page = st.Page(lambda: tactical_highlights_view.render(highlights_page, detail_page),
                           title="Tactical Highlights", url_path="tactical-highlights")
explorer_page = st.Page(lambda: game_explorer_view.render(explorer_page, detail_page),
                         title="Game Explorer", url_path="game-explorer")
settings_page = st.Page(settings_view.render, title="Settings", url_path="settings")
analysis_jobs_page = st.Page(analysis_jobs_view.render, title="Analysis Jobs", url_path="analysis-jobs")
# BRIEF.md Phase B: defaults to first when the database has no games yet
# or player.name is still the placeholder -- a fresh install should never
# land on Overview with nothing to show before walking through setup.
onboarding_page = st.Page(lambda: onboarding_view.render(overview_page), title="Setup",
                           url_path="setup", default=NEEDS_ONBOARDING)

pg = st.navigation({
    "Career": [overview_page, patterns_page, openings_page, matchups_page,
               endings_page, highlights_page],
    "Explore": [explorer_page],
    "App": [settings_page, analysis_jobs_page, onboarding_page],
    " ": [detail_page],
})
pg.run()
