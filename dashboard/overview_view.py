"""
Phase 6c.4: Overview, redesigned per the approved 6c.1 information
architecture -- the landing page now opens with an auto-generated
career-level narrative (mirroring the per-game story, applied to the
whole career) and a "most dramatic game" teaser that links straight into
Game Detail, instead of a bare stats dump.
"""
import html
import streamlit as st

import achievements
import charts
import data
import live_engine
import narrative
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats
from game_explorer_view import cached_game_explorer_table
from version import __version__


OVERVIEW_CSS = f"""<style>
.cw-ov {{ --cw-canvas:#0B0F14; --cw-panel:#131A22; --cw-panel-2:#0F141B;
    --cw-copper:#E08A3C; --cw-cyan:#4FB8C4; --cw-text:#ECEEF0;
    --cw-muted:#ECEEF099; --cw-line:#232B37; --cw-line-soft:#1a212b; }}

.cw-ov-zone-head {{ display:flex; align-items:baseline; gap:.8rem; margin:1.6rem 0 1rem; }}
.cw-ov-eyebrow {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.68rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--cw-cyan); white-space:nowrap; }}
.cw-ov-zone-head h2 {{ margin:0; font-family:"Archivo Narrow","Arial Narrow",sans-serif;
    font-weight:700; font-size:1.1rem; color:var(--cw-text); }}
.cw-ov-zone-head-rule {{ flex:1; height:1px; background:var(--cw-line); }}

.cw-ov-trait-tag {{ display:inline-block; font-family:"Archivo Narrow","Arial Narrow",sans-serif;
    font-size:.74rem; font-weight:600; padding:.4rem .75rem; margin:0 .4rem .4rem 0;
    border-radius:4px; background:var(--cw-panel); border:1px solid var(--cw-line); color:var(--cw-text); }}
.cw-ov-rating-num {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace;
    font-variant-numeric:tabular-nums; font-size:1.5rem; font-weight:600; color:var(--cw-text); }}
.cw-ov-rating-trend {{ font-size:.78rem; margin-left:.4rem; }}
.cw-ov-rating-trend.up {{ color:{theme.POSITIVE}; }}
.cw-ov-rating-trend.down {{ color:{theme.NEGATIVE}; }}
.cw-ov-exec-summary {{ font-style:italic; font-size:.98rem; line-height:1.6; color:var(--cw-muted);
    max-width:74ch; border-left:2px solid var(--cw-line); padding-left:.9rem; margin:0 0 1rem; }}

.cw-ov-status-strip {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.72rem;
    color:var(--cw-muted); display:flex; align-items:center; gap:.5rem; margin-bottom:.6rem; }}
.cw-ov-status-strip .dot {{ width:6px; height:6px; border-radius:50%; flex-shrink:0; }}
.cw-ov-status-strip .dot.on {{ background:var(--cw-cyan); }}
.cw-ov-status-strip .dot.off {{ background:var(--cw-line); }}

.cw-ov-rail {{ position:relative; background:var(--cw-panel-2); border-radius:3px; overflow:hidden;
    height:110px; border:1px solid var(--cw-line); }}
.cw-ov-rail-mid {{ position:absolute; left:0; right:0; top:50%; height:1px;
    background:rgba(236,238,240,.28); z-index:2; }}
.cw-ov-rail-fill {{ position:absolute; left:0; right:0; bottom:0; width:100%; z-index:1;
    background:linear-gradient(180deg, var(--cw-copper), #a95f22); }}
@keyframes cw-ov-rail-rise {{ from {{ height:50%; }} to {{ height: var(--cw-rail-target, 50%); }} }}

.cw-ov-milestone {{ display:inline-flex; align-items:center; gap:.55rem; background:var(--cw-panel);
    border:1px solid var(--cw-line); border-radius:5px; padding:.6rem .9rem; margin:0 .5rem .5rem 0;
    white-space:nowrap; }}
.cw-ov-milestone .tick {{ width:5px; height:5px; border-radius:50%; background:var(--cw-copper); flex-shrink:0; }}
.cw-ov-milestone .label {{ font-family:"Archivo Narrow","Arial Narrow",sans-serif; font-size:.78rem; color:var(--cw-text); }}
.cw-ov-milestone .date {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.68rem;
    color:var(--cw-muted); margin-left:.3rem; }}

.cw-ov-ticker {{ width:100%; border-collapse:collapse; }}
.cw-ov-ticker tr {{ border-bottom:1px solid var(--cw-line-soft); }}
.cw-ov-ticker tr:last-child {{ border-bottom:none; }}
.cw-ov-ticker td {{ padding:.5rem .3rem; }}
.cw-ov-res {{ font-family:"Archivo Narrow","Arial Narrow",sans-serif; font-size:.68rem; font-weight:700;
    padding:.15rem .5rem; border-radius:3px; letter-spacing:.04em; }}
.cw-ov-res.w {{ background:{theme.POSITIVE}29; color:{theme.POSITIVE}; }}
.cw-ov-res.l {{ background:{theme.NEGATIVE}29; color:{theme.NEGATIVE}; }}
.cw-ov-res.d {{ background:var(--cw-panel-2); color:var(--cw-muted); }}
.cw-ov-delta {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.8rem;
    font-variant-numeric:tabular-nums; text-align:right; }}
.cw-ov-delta.up {{ color:{theme.POSITIVE}; }}
.cw-ov-delta.down {{ color:{theme.NEGATIVE}; }}

.cw-ov-chip {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.66rem;
    padding:.2rem .55rem; border-radius:3px; background:var(--cw-panel-2); color:var(--cw-cyan);
    border:1px solid var(--cw-line); display:inline-block; margin:0 .35rem .35rem 0; }}

.cw-ov-balance-row {{ display:flex; align-items:flex-start; gap:.55rem; padding:.55rem 0;
    border-bottom:1px solid var(--cw-line-soft); }}
.cw-ov-balance-row:last-child {{ border-bottom:none; }}
.cw-ov-balance-row .mk {{ width:7px; height:7px; border-radius:50%; margin-top:.4rem; flex-shrink:0; }}
.cw-ov-balance-row.strength .mk {{ background:{theme.POSITIVE}; }}
.cw-ov-balance-row.weakness .mk {{ background:var(--cw-copper); }}
.cw-ov-balance-row .t {{ font-size:.86rem; color:var(--cw-text); font-weight:600; margin-bottom:.15rem;
    font-family:"Archivo Narrow","Arial Narrow",sans-serif; }}
.cw-ov-balance-row .d {{ font-size:.8rem; color:var(--cw-muted); line-height:1.45; }}

.cw-ov-severity {{ display:inline-flex; gap:3px; vertical-align:middle; margin-right:.6rem; }}
.cw-ov-severity .d {{ width:6px; height:6px; border-radius:50%; background:var(--cw-line); display:inline-block; }}
.cw-ov-severity .d.on {{ background:var(--cw-copper); }}

.st-key-cw_ov_progress[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_recent_form[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_highlight[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_coaching_list[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color:var(--cw-panel); border:1px solid var(--cw-line); border-radius:6px;
    box-shadow:0 1px 0 rgba(255,255,255,.04) inset, 0 8px 22px rgba(0,0,0,.38);
}}

@media (prefers-reduced-motion: reduce) {{
    .cw-ov-rail-fill {{ animation-duration:.01ms !important; }}
}}
</style>"""


# Maps each finding title -> (page_ref_key, human-readable page name, optional tab hint).
# page_ref_key matches the kwarg name passed to render() from app.py.
_FINDING_DEST = {
    "Piece blunder hot-spot":           ("patterns_page", "Patterns & Tendencies", "Piece Handling"),
    "Sharp positions and blunder rate": ("patterns_page", "Patterns & Tendencies", "Clock & Time"),
    "Thinking time vs. blunder rate":   ("patterns_page", "Patterns & Tendencies", "Clock & Time"),
    "Clock pressure and blunder rate":  ("patterns_page", "Patterns & Tendencies", "Clock & Time"),
    "Castling and win rate":            ("patterns_page", "Patterns & Tendencies", "Game Context"),
    "King moves off the back rank":     ("patterns_page", "Patterns & Tendencies", "Piece Handling"),
    "Toughest opponent":                ("matchups_page", "Matchups & Opponents", None),
    "Giant-killing and collapses":      ("matchups_page", "Matchups & Opponents", None),
    "Tactical highlights so far":       ("highlights_page", "Tactical Highlights", None),
    "How your games end":               ("endings_page", "Game Endings", None),
}


def _split_by_polarity(findings):
    """(strengths, weaknesses) -- top 2 of each, by the order
    get_career_findings() already returns (severity-ranked)."""
    strengths = [f for f in findings if f["polarity"] == "strength"][:2]
    weaknesses = [f for f in findings if f["polarity"] in ("weakness", "mixed")][:2]
    return strengths, weaknesses


_SEVERITY_DOTS = {"high": 3, "medium": 2, "low": 1}


def _render_identity_zone(stats, rating_snapshot, streak, strengths, weaknesses, narrative_text):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">Who you are</span>'
                '<h2>Your chess identity</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    tags = [f["title"] for f in (strengths + weaknesses)[:3]]

    rail_col, id_col = st.columns([1, 14])
    with rail_col:
        win_pct = stats.get("win_pct") or 0
        st.markdown(
            f'<div class="cw-ov-rail" style="--cw-rail-target: {win_pct:.0f}%;">'
            f'<div class="cw-ov-rail-mid"></div>'
            f'<div class="cw-ov-rail-fill" '
            f'style="height:{win_pct:.0f}%; animation: cw-ov-rail-rise 1.4s cubic-bezier(.16,.9,.25,1) .1s both;">'
            f'</div></div>', unsafe_allow_html=True)
    with id_col:
        tags_html = "".join(f'<span class="cw-ov-trait-tag">{html.escape(t)}</span>' for t in tags)
        st.markdown(f'<div>{tags_html}</div>', unsafe_allow_html=True)

        current = rating_snapshot.get("current_rating")
        peak = rating_snapshot.get("peak_rating")
        if current is not None:
            trend_html = ""
            if peak is not None and current < peak:
                trend_html = f'<span class="cw-ov-rating-trend down">peak {peak}</span>'
            elif peak is not None:
                trend_html = '<span class="cw-ov-rating-trend up">at peak</span>'
            streak_bit = ""
            if streak.get("length", 0) >= 2:
                streak_bit = f' · {streak["length"]}-game {streak["outcome"]} streak'
            st.markdown(
                f'<div><span class="cw-ov-rating-num">{current}</span>{trend_html}'
                f'<div style="font-family:\'SF Mono\',monospace; font-size:.68rem; color:var(--cw-muted); '
                f'margin-top:.2rem;">Current rating{streak_bit}</div></div>',
                unsafe_allow_html=True)

    st.markdown(f'<p class="cw-ov-exec-summary">{html.escape(narrative_text)}</p>',
                unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}",
                help="Every game synced from your online accounts.")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}",
                help="Games your engine has analyzed so far — accuracy stats only "
                     "count these. Run more batches from Analysis Jobs to grow this.")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--",
                help="Wins as a share of all games.")
    col4.metric("ACPL", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--",
                help="Average centipawn loss — measures move accuracy across analyzed games. Lower is better.")


def _render_evolution_zone(duck_conn, sqlite_conn, top_game, self_page, detail_page):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">How you\'ve evolved</span>'
                '<h2>Progress &amp; milestones</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    with st.container(border=True, key="cw_ov_progress"):
        st.subheader("Rating & accuracy over time")
        rating_df = cached_rating_trajectory(duck_conn)
        acpl_df = cached_acpl_trajectory(duck_conn)
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(charts.line_chart(rating_df, "year", "avg_rating", theme.ACCENT_GOLD,
                                                x_title="Year", y_title="Average rating", height=200),
                             theme=None, width='stretch')
        with chart_col2:
            acpl_df = acpl_df.assign(
                hover_coverage=acpl_df.apply(
                    lambda r: f"{int(r.n_games)} of {int(r.n_total_games)} games ({r.coverage_pct:.1f}%)",
                    axis=1))
            st.plotly_chart(charts.line_chart(acpl_df, "year", "acpl", theme.NEGATIVE, height=200,
                                                x_title="Year", y_title="ACPL",
                                                hover_extra=("hover_coverage", "Analyzed")),
                             theme=None, width='stretch')
        if len(acpl_df) >= 2:
            min_row = acpl_df.loc[acpl_df.coverage_pct.idxmin()]
            max_row = acpl_df.loc[acpl_df.coverage_pct.idxmax()]
            if max_row.coverage_pct >= 2 * max(min_row.coverage_pct, 0.1):
                st.caption(f"⚠️ Analysis coverage varies sharply by year — from "
                           f"{min_row.coverage_pct:.1f}% in {int(min_row.year)} to "
                           f"{max_row.coverage_pct:.1f}% in {int(max_row.year)}.")

    milestones = cached_unlocked_achievements(sqlite_conn)
    if milestones:
        chips = "".join(
            f'<div class="cw-ov-milestone"><span class="tick"></span>'
            f'<span class="label">{html.escape(m["name"])}</span>'
            f'<span class="date">{html.escape(m["unlocked_at"][:10])}</span></div>'
            for m in milestones)
        st.markdown(f'<div>{chips}</div>', unsafe_allow_html=True)

    with st.container(border=True, key="cw_ov_recent_form"):
        st.subheader("Recent form")
        form_df = cached_recent_form(duck_conn)
        if len(form_df) == 0:
            st.caption("No games yet.")
        else:
            rows_html = ""
            for _, row in form_df.iterrows():
                outcome = row["outcome_for_player"]
                res_class = {"win": "w", "loss": "l", "draw": "d"}.get(outcome, "d")
                delta = row["player_rating_change"]
                delta_html = "—"
                if delta is not None:
                    delta_class = "up" if delta >= 0 else "down"
                    sign = "+" if delta >= 0 else ""
                    delta_html = f'<span class="cw-ov-delta {delta_class}">{sign}{int(delta)}</span>'
                rows_html += (
                    f'<tr><td><span class="cw-ov-res {res_class}">{outcome.upper()}</span></td>'
                    f'<td>{html.escape(row["opponent_name"] or "Unknown")}</td>'
                    f'<td style="color:var(--cw-muted); font-size:.8rem;">{row["utc_date"]}</td>'
                    f'<td>{delta_html}</td></tr>')
            st.markdown(f'<table class="cw-ov-ticker">{rows_html}</table>', unsafe_allow_html=True)

    if top_game is not None:
        with st.container(border=True, key="cw_ov_highlight"):
            st.subheader("Career highlight")
            chips_html = theme.chip_row_html(top_game)
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)
                st.caption(theme.BADGE_LEGEND)
            st.write(f"vs. {top_game.opponent_name} on {top_game.utc_date} "
                     f"({top_game.outcome_for_player})")
            if st.button("View this game →", key="cw_ov_view_highlight"):
                st.session_state["selected_game_id"] = top_game.game_id
                st.session_state["return_page"] = self_page
                st.session_state["return_page_label"] = "Overview"
                st.switch_page(detail_page)


def _render_coaching_zone(strengths, weaknesses, findings, sqlite_conn, insights_page, page_refs):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">What to work on</span>'
                '<h2>Your coaching plan</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    if strengths or weaknesses:
        bal_col1, bal_col2 = st.columns(2)
        with bal_col1:
            st.markdown('<div style="font-family:\'Archivo Narrow\',sans-serif; font-size:.7rem; '
                        f'letter-spacing:.12em; text-transform:uppercase; color:{theme.POSITIVE}; '
                        'font-weight:700; margin-bottom:.6rem;">Strengths</div>', unsafe_allow_html=True)
            for f in strengths:
                st.markdown(
                    f'<div class="cw-ov-balance-row strength"><span class="mk"></span><div>'
                    f'<div class="t">{html.escape(f["title"])}</div>'
                    f'<div class="d">{html.escape(f["detail"])}</div></div></div>',
                    unsafe_allow_html=True)
            if not strengths:
                st.caption("Nothing surfaced yet — check back after more games are analyzed.")
        with bal_col2:
            st.markdown('<div style="font-family:\'Archivo Narrow\',sans-serif; font-size:.7rem; '
                        'letter-spacing:.12em; text-transform:uppercase; color:var(--cw-copper); '
                        'font-weight:700; margin-bottom:.6rem;">Focus areas</div>', unsafe_allow_html=True)
            for f in weaknesses:
                st.markdown(
                    f'<div class="cw-ov-balance-row weakness"><span class="mk"></span><div>'
                    f'<div class="t">{html.escape(f["title"])}</div>'
                    f'<div class="d">{html.escape(f["detail"])}</div></div></div>',
                    unsafe_allow_html=True)
            if not weaknesses:
                st.caption("Nothing surfaced yet — check back after more games are analyzed.")

    ranked = sorted(weaknesses, key=lambda f: _SEVERITY_DOTS.get(f["severity"], 0), reverse=True)[:3]
    if ranked:
        with st.container(border=True, key="cw_ov_coaching_list"):
            for f in ranked:
                dots_on = _SEVERITY_DOTS.get(f["severity"], 0)
                dots_html = "".join(
                    f'<span class="d{" on" if i < dots_on else ""}"></span>' for i in range(3))
                ref_key, dest_name, dest_tab = _FINDING_DEST.get(f["title"], (None, None, None))
                dest_page = page_refs.get(ref_key) if ref_key else None
                row_col, link_col = st.columns([6, 1])
                with row_col:
                    st.markdown(
                        f'<div><span class="cw-ov-severity">{dots_html}</span>'
                        f'<strong>{html.escape(f["title"])}</strong><br>'
                        f'<span style="color:var(--cw-muted); font-size:.85rem;">{html.escape(f["detail"])}</span>'
                        f'</div>', unsafe_allow_html=True)
                with link_col:
                    if dest_page is not None:
                        if st.button(dest_name or "View", key=f"cw_ov_coach_{f['title']}"):
                            st.switch_page(dest_page)

    top_weakness = ranked[0]["title"] if ranked else None
    cached = data.get_cached_narrative(sqlite_conn, "coaching", "recommendations")
    cta_col, links_col = st.columns([2, 3])
    with cta_col:
        if top_weakness:
            st.caption(f"Because **{top_weakness}** is your top focus area —")
        button_label = "View your coaching plan →" if cached else "Get your coaching plan →"
        if st.button(button_label, key="cw_ov_coaching_cta") and insights_page is not None:
            st.switch_page(insights_page)
    with links_col:
        links = [
            ("insights", "🔍 Insights", page_refs.get("insights_page")),
            ("patterns", "📊 Patterns & Tendencies", page_refs.get("patterns_page")),
            ("openings", "♟️ Openings & Repertoire", page_refs.get("openings_page")),
        ]
        links = [(key, label, page) for key, label, page in links if page is not None]
        if links:
            cols = st.columns(len(links))
            for col, (key, label, page) in zip(cols, links):
                with col:
                    if st.button(label, key=f"cw_ov_quick_{key}", width='stretch'):
                        st.switch_page(page)


@st.cache_data(show_spinner="Loading your rating history…")
def cached_rating_trajectory(_duck_conn):
    return data.get_rating_trajectory(_duck_conn)


@st.cache_data(show_spinner="Loading your accuracy trend…")
def cached_acpl_trajectory(_duck_conn):
    return data.get_acpl_trajectory(_duck_conn)


@st.cache_data(show_spinner="Computing win rate by color…")
def cached_win_rate_by_color(_duck_conn):
    return data.get_win_rate_by_color(_duck_conn)


@st.cache_data(show_spinner="Loading monthly progress…")
def cached_progress_by_month(_duck_conn):
    return data.get_progress_by_month(_duck_conn)


@st.cache_data(show_spinner="Loading your rating snapshot…")
def cached_rating_snapshot(_duck_conn):
    return data.get_rating_snapshot(_duck_conn)


@st.cache_data(show_spinner="Loading your current streak…")
def cached_current_streak(_duck_conn):
    return data.get_current_streak(_duck_conn)


@st.cache_data(show_spinner="Loading your recent games…")
def cached_recent_form(_duck_conn):
    return data.get_recent_form_snapshot(_duck_conn, n=5)


@st.cache_data(show_spinner="Loading your milestones…")
def cached_unlocked_achievements(_sqlite_conn):
    return achievements.get_unlocked_achievements(_sqlite_conn, limit=4)


def _status_strip_html(stats, engine_status):
    dot_class = "on" if engine_status["connected"] else "off"
    version_bit = f'Stockfish {engine_status["version"]}' if engine_status["version"] else "Engine not detected"
    return (
        f'<div class="cw-ov-status-strip"><span class="dot {dot_class}"></span>'
        f'Chesswright v{__version__} · {stats["total_games"]:,} games · '
        f'{stats["analyzed_games"]:,} analyzed · {version_bit}</div>')


def render(self_page, detail_page, *, patterns_page=None, matchups_page=None,
           endings_page=None, highlights_page=None, insights_page=None,
           openings_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.markdown(OVERVIEW_CSS, unsafe_allow_html=True)
    st.title("Overview")

    if st.session_state.pop("just_completed_onboarding", False):
        st.info("Your starter batch is analyzed and ready. Use the sidebar to explore — "
                "each section looks at your games from a different angle.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    engine_status = live_engine.get_engine_status_summary()
    st.markdown(_status_strip_html(stats, engine_status), unsafe_allow_html=True)

    rating_df = cached_rating_trajectory(duck_conn)
    rating_snapshot = cached_rating_snapshot(duck_conn)
    streak = cached_current_streak(duck_conn)
    explorer_df = cached_game_explorer_table(duck_conn)
    top_game = explorer_df.iloc[0] if len(explorer_df) else None

    findings = []
    if stats.get("analyzed_games", 0) > 0:
        findings = cached_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
    strengths, weaknesses = _split_by_polarity(findings)

    narrative_text = narrative.generate_career_narrative(stats, rating_df, top_game)

    page_refs = {
        "patterns_page": patterns_page, "matchups_page": matchups_page,
        "endings_page": endings_page, "highlights_page": highlights_page,
        "insights_page": insights_page, "openings_page": openings_page,
    }

    _render_identity_zone(stats, rating_snapshot, streak, strengths, weaknesses, narrative_text)
    _render_evolution_zone(duck_conn, sqlite_conn, top_game, self_page, detail_page)
    _render_coaching_zone(strengths, weaknesses, findings, sqlite_conn, insights_page, page_refs)
