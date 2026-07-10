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
import re
import sys
import pathlib
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests
import streamlit as st

from version import __version__

import analytics
import theme
from _common import get_config, get_connections
import overview_view
import patterns_view
import openings_view
import matchups_view
import game_endings_view
import tactical_highlights_view
import game_explorer_view
import game_detail_view
import insights_view
import points_view
import evolution_view
import settings_view
import onboarding_view
import analysis_jobs_view
import batch_impact_view
import ask_view
import drill_export_view
import srs_drill_view
import training_queue_view
import opening_tree_view
import prep_view
import annotate
import job_runner
import joblock

st.set_page_config(page_title="Chesswright", layout="wide", page_icon="♟️")
st.markdown(theme.CSS, unsafe_allow_html=True)

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
    with st.status("Getting ready — happens once per session, takes about 20 seconds...",
                    expanded=True) as status:
        status.write("Indexing position types (endgame, middlegame, etc.)...")
        analytics.ensure_structure_ctx(sqlite_conn, cfg)
        status.write("Indexing game-by-game sequencing (session, tilt patterns)...")
        analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
        status.update(label="Ready.", state="complete", expanded=False)
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
    # Duck-side reads run against a private snapshot, not the live file
    # (see _common.py's snapshot-isolation comment) -- this button is the
    # explicit point where that snapshot picks up newly synced/analyzed
    # games, exactly like st.cache_data above.
    duck_conn.refresh_snapshot()
    sqlite_conn.execute("DROP TABLE IF EXISTS structure_ctx")
    sqlite_conn.execute("DROP TABLE IF EXISTS session_ctx")
    # No TEMP TABLE fast path for opening_position_stats_cache (see
    # analytics.ensure_opening_position_stats) -- its own session-level
    # bypass is this session_state flag instead, so drop that too.
    st.session_state.pop("ot_stats_cache_ready", None)
    warm_up()  # warm_up() already shows its own st.status steps
    st.rerun()
if "last_refreshed" in st.session_state:
    st.sidebar.caption(f"Last refreshed: {st.session_state['last_refreshed']:%H:%M}")


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_latest_version() -> str | None:
    """Check GitHub Releases for the latest tag. Returns tag string or None on failure."""
    try:
        r = requests.get(
            "https://api.github.com/repos/Hawi254/chesswright/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        return r.json().get("tag_name")
    except Exception:
        return None


def _parse_ver(v: str) -> tuple:
    v = v.lstrip("v")
    try:
        parts = [int(x) for x in v.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)
    except Exception:
        return (0, 0, 0)


if not NEEDS_ONBOARDING:
    latest_tag = _fetch_latest_version()
    if (latest_tag
            and re.match(r'^v\d+\.\d+\.\d+$', latest_tag)
            and _parse_ver(latest_tag) > _parse_ver(__version__)):
        st.sidebar.info(
            f"Chesswright {latest_tag} is available — "
            f"[download it](https://github.com/Hawi254/chesswright/releases/latest)"
        )


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


# Pro extension point -- chesswright_pro is an optional proprietary package
# that contributes additional nav pages when installed and licensed.
# get_nav_groups() returns a dict of {group_name: [st.Page, ...]} that is
# merged into the navigation below. The core never imports Pro code directly;
# all Pro behaviour is contributed by the package itself through this boundary.
_pro_nav_groups: dict = {}
try:
    import chesswright_pro  # type: ignore[import]
    if chesswright_pro.is_licensed():
        _pro_nav_groups = chesswright_pro.get_nav_groups()
except ImportError:
    pass

# Active Pro profile indicator -- shown whenever a student/alt-account profile
# is active, regardless of whether the Pro package is fully loaded (the profile
# file is written by the Pro package but read here by the core so the indicator
# appears on every page without the Pro package needing to inject sidebar UI).
from config import get_active_profile as _get_active_profile, clear_active_profile as _clear_active_profile
_active_profile = _get_active_profile()

if not NEEDS_ONBOARDING:
    with st.sidebar:
        if _active_profile:
            st.info(f"Viewing: **{_active_profile}**")
            if st.button("← My account", key="_pro_return_own"):
                _clear_active_profile()
                for _k in ("warmed_up", "needs_onboarding", "last_refreshed"):
                    st.session_state.pop(_k, None)
                st.cache_resource.clear()
                st.rerun()
        st.divider()
        _sidebar_job_status()


# ---------- Navigation ----------
# visibility="hidden" -- Game Detail is reachable only via st.switch_page
# from a row click (Game Explorer, Tactical Highlights, Matchups &
# Opponents' comeback/collapse lists, the Overview "most dramatic game"
# teaser), never a sidebar nav item itself.
detail_page = st.Page(game_detail_view.render, title="Game Detail",
                       url_path="game-detail", visibility="hidden")
overview_page = st.Page(
    lambda: overview_view.render(
        overview_page, detail_page,
        patterns_page=patterns_page,
        matchups_page=matchups_page,
        endings_page=endings_page,
        highlights_page=highlights_page,
        insights_page=insights_page,
        openings_page=openings_page,
    ),
    title="Overview", url_path="overview", default=not NEEDS_ONBOARDING)
patterns_page = st.Page(patterns_view.render, title="Patterns & Tendencies",
                         url_path="patterns")
openings_page = st.Page(
    lambda: openings_view.render(drill_export_page=drill_export_page),
    title="Openings & Repertoire", url_path="openings",
)
matchups_page = st.Page(lambda: matchups_view.render(matchups_page, detail_page,
                                                     prep_page=prep_page),
                         title="Matchups & Opponents", url_path="matchups")
endings_page = st.Page(game_endings_view.render, title="Game Endings",
                        url_path="game-endings")
highlights_page = st.Page(
    lambda: tactical_highlights_view.render(
        highlights_page, detail_page, drill_export_page=drill_export_page,
        analysis_jobs_page=analysis_jobs_page),
    title="Tactical Highlights", url_path="tactical-highlights",
)
insights_page = st.Page(
    lambda: insights_view.render(drill_export_page=drill_export_page, prep_page=prep_page),
    title="Insights", url_path="insights",
)
points_page = st.Page(lambda: points_view.render(points_page, detail_page),
                       title="Where Your Points Go", url_path="points")
evolution_page = st.Page(evolution_view.render, title="Repertoire Evolution",
                          url_path="evolution")
explorer_page = st.Page(lambda: game_explorer_view.render(explorer_page, detail_page),
                         title="Game Explorer", url_path="game-explorer")
drill_export_page = st.Page(drill_export_view.render, title="Drill Export",
                             url_path="drill-export")
# Training Center MVP (roadmap S17 Q4 / S19) -- placed in "Explore" next to
# the practice tools it feeds into (Drill Export, Opponent Prep), not in
# "Career" alongside the read-only reporting pages it draws its findings
# from. No new "Training Center" nav group yet: the roadmap's full Phase 5
# vision (trainers, plans, achievements) doesn't exist yet, and standing up
# a whole new sidebar group for one page would be premature -- revisit once
# more Phase 5 pages actually land.
training_queue_page = st.Page(
    lambda: training_queue_view.render(drill_export_page=drill_export_page,
                                        prep_page=prep_page,
                                        analysis_jobs_page=analysis_jobs_page),
    title="Training Queue", url_path="training-queue",
)
srs_drill_page = st.Page(srs_drill_view.render, title="SRS Drills ✦",
                          url_path="srs-drills")
opening_tree_page = st.Page(opening_tree_view.render, title="Opening Tree ✦",
                             url_path="opening-tree")
prep_page = st.Page(prep_view.render, title="Opponent Prep", url_path="opponent-prep")
ask_page = st.Page(ask_view.render, title="Ask", url_path="ask")
settings_page = st.Page(settings_view.render, title="Settings", url_path="settings")
analysis_jobs_page = st.Page(
    lambda: analysis_jobs_view.render(batch_impact_page=batch_impact_page),
    title="Analysis Jobs", url_path="analysis-jobs",
)
batch_impact_page = st.Page(
    lambda: batch_impact_view.render(batch_impact_page, detail_page),
    title="Batch Impact", url_path="batch-impact",
)
# BRIEF.md Phase B: defaults to first when the database has no games yet
# or player.name is still the placeholder -- a fresh install should never
# land on Overview with nothing to show before walking through setup.
onboarding_page = st.Page(lambda: onboarding_view.render(overview_page),
                           title="Setup" if NEEDS_ONBOARDING else "Sync Games",
                           url_path="setup", default=NEEDS_ONBOARDING)

pg = st.navigation({
    "Career": [overview_page, patterns_page, openings_page, matchups_page,
               endings_page, highlights_page, insights_page, points_page,
               evolution_page],
    "Explore": [explorer_page, drill_export_page, training_queue_page, srs_drill_page,
                opening_tree_page, prep_page, ask_page, detail_page],
    "App": [settings_page, analysis_jobs_page, batch_impact_page, onboarding_page],
    **_pro_nav_groups,
})
pg.run()
