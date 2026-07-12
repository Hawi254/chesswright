"""
Phase 6c.4: Overview, redesigned per the approved 6c.1 information
architecture -- the landing page now opens with an auto-generated
career-level narrative (mirroring the per-game story, applied to the
whole career) and a "most dramatic game" teaser that links straight into
Game Detail, instead of a bare stats dump.
"""
import html
import streamlit as st

import charts
import data
import narrative
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats
from game_explorer_view import cached_game_explorer_table


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


def _render_focus_card(findings, page_refs: dict) -> None:
    """Gold-accented card surfacing the top finding with a direct navigation link.
    Placed between the career narrative and the headline metrics so it's the
    first actionable element a returning user sees."""
    if not findings:
        return
    top = findings[0]
    ref_key, dest_name, dest_tab = _FINDING_DEST.get(top["title"], (None, top["title"], None))
    dest_page = page_refs.get(ref_key) if ref_key else None
    tab_note = f" ({dest_tab})" if dest_tab else ""

    theme.render_metric_card(
        eyebrow="🎯 Focus for your next session",
        headline=top["headline"],
        detail=top["detail"],
    )
    if dest_page is not None:
        col, _ = st.columns([3, 5])
        with col:
            if st.button(f"Explore in {dest_name}{tab_note} →", key="focus_card_goto"):
                st.switch_page(dest_page)


def _render_coaching_teaser(sqlite_conn, insights_page) -> None:
    """Points at Insights' existing "What to practice" coaching panel
    rather than duplicating any AI-call logic here -- Overview never
    calls Claude itself for this, it only reads whatever's already
    cached via the same claude_narrative.generate_coaching_recommendations
    output Insights writes."""
    if insights_page is None:
        return
    cached = data.get_cached_narrative(sqlite_conn, "coaching", "recommendations")
    with st.container(border=True):
        st.subheader("Your coaching plan")
        if cached:
            _coaching_text, generated_at = cached
            st.write(f"Personalized coaching notes ready, generated {generated_at}.")
            button_label = "View your coaching plan →"
        else:
            st.write("Concrete, specific practice recommendations grounded in your findings.")
            button_label = "Get your coaching plan →"
        if st.button(button_label, key="coaching_teaser_goto"):
            st.switch_page(insights_page)


def _render_quick_explore(page_refs: dict) -> None:
    """Static row of links into pages a returning user most plausibly wants
    next. Page-level only, no attempt to pre-select a tab within a
    destination page. Reuses the existing st.switch_page pattern already
    used elsewhere on this page -- no new nav infrastructure."""
    links = [
        ("insights", "🔍 Insights", page_refs.get("insights_page")),
        ("patterns", "📊 Patterns & Tendencies", page_refs.get("patterns_page")),
        ("openings", "♟️ Openings & Repertoire", page_refs.get("openings_page")),
    ]
    links = [(key, label, page) for key, label, page in links if page is not None]
    if not links:
        return
    st.subheader("Explore more")
    cols = st.columns(len(links))
    for col, (key, label, page) in zip(cols, links):
        with col:
            if st.button(label, key=f"quick_explore_{key}", width='stretch'):
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


def render(self_page, detail_page, *, patterns_page=None, matchups_page=None,
           endings_page=None, highlights_page=None, insights_page=None,
           openings_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.title("Overview")

    if st.session_state.pop("just_completed_onboarding", False):
        st.info("Your starter batch is analyzed and ready. Use the sidebar to explore — "
                "each section looks at your games from a different angle.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    rating_df = cached_rating_trajectory(duck_conn)
    explorer_df = cached_game_explorer_table(duck_conn)
    top_game = explorer_df.iloc[0] if len(explorer_df) else None

    st.markdown(
        f'<div class="narrative-quote">'
        f'{html.escape(narrative.generate_career_narrative(stats, rating_df, top_game))}</div>',
        unsafe_allow_html=True)

    if stats.get("analyzed_games", 0) > 0:
        findings = cached_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
        _render_focus_card(findings, {
            "patterns_page": patterns_page,
            "matchups_page": matchups_page,
            "endings_page":  endings_page,
            "highlights_page": highlights_page,
        })

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}",
                help="Every game synced from your online accounts.")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}",
                help="Games your engine has analyzed so far — accuracy stats only "
                     "count these. Run more batches from Analysis Jobs to grow this.")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--",
                help="Wins as a share of all games. Online pairing aims for even "
                     "matches, so most players sit near 50%.")
    col4.metric("ACPL", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--",
                help="Average centipawn loss — measures move accuracy across analyzed games. Lower is better.")

    if top_game is not None:
        with st.container(border=True):
            chips_html = theme.chip_row_html(top_game)
            st.subheader("Most dramatic game on record")
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)
                st.caption(theme.BADGE_LEGEND)
            st.write(f"vs. {top_game.opponent_name} on {top_game.utc_date} "
                     f"({top_game.outcome_for_player})")
            if st.button("View this game →"):
                st.session_state["selected_game_id"] = top_game.game_id
                st.session_state["return_page"] = self_page
                st.session_state["return_page_label"] = "Overview"
                st.switch_page(detail_page)

    with st.container(border=True):
        st.subheader("Rating trajectory")
        st.plotly_chart(charts.line_chart(rating_df, "year", "avg_rating", theme.ACCENT_GOLD,
                                            x_title="Year", y_title="Average rating"),
                         theme=None)

        acpl_df = cached_acpl_trajectory(duck_conn)
        st.caption(f"ACPL (average centipawn loss -- lower is more accurate play) trend, "
                    f"analyzed games only: based on {acpl_df.n_games.sum()} analyzed games "
                    f"across {len(acpl_df)} years, treat as preliminary given the small sample.")
        if len(acpl_df) >= 2:
            min_row = acpl_df.loc[acpl_df.coverage_pct.idxmin()]
            max_row = acpl_df.loc[acpl_df.coverage_pct.idxmax()]
            if max_row.coverage_pct >= 2 * max(min_row.coverage_pct, 0.1):
                st.caption(f"⚠️ Analysis coverage varies sharply by year -- from "
                           f"{min_row.coverage_pct:.1f}% in {int(min_row.year)} to "
                           f"{max_row.coverage_pct:.1f}% in {int(max_row.year)} (analysis "
                           "prioritizes recently-synced games, so older years lean on far "
                           "fewer analyzed games per point). Hover a point for its own "
                           "coverage before reading a shift as a real accuracy change.")
        acpl_df = acpl_df.assign(
            hover_coverage=acpl_df.apply(
                lambda r: f"{int(r.n_games)} of {int(r.n_total_games)} games ({r.coverage_pct:.1f}%)",
                axis=1))
        st.plotly_chart(charts.line_chart(acpl_df, "year", "acpl", theme.NEGATIVE,
                                          x_title="Year", y_title="ACPL (lower = more accurate)",
                                          hover_extra=("hover_coverage", "Analyzed")), theme=None)

    with st.container(border=True):
        st.subheader("Win rate by color")
        color_df = cached_win_rate_by_color(duck_conn)
        st.plotly_chart(charts.bar_chart(color_df, "player_color", "win_pct", theme.POSITIVE,
                                          x_title="Color played", y_title="Win rate (%)"),
                         theme=None)

    progress_df = cached_progress_by_month(duck_conn)
    if len(progress_df) >= 2:
        with st.container(border=True):
            st.subheader("Progress over time")
            st.caption("Monthly averages across analyzed games — months with fewer than 3 analyzed "
                       "games are excluded to avoid single-game noise.")
            min_row = progress_df.loc[progress_df.coverage_pct.idxmin()]
            max_row = progress_df.loc[progress_df.coverage_pct.idxmax()]
            if max_row.coverage_pct >= 2 * max(min_row.coverage_pct, 0.1):
                st.caption(f"⚠️ Coverage still varies by month -- from {min_row.coverage_pct:.1f}% "
                           f"in {min_row.period} to {max_row.coverage_pct:.1f}% in {max_row.period}. "
                           "Hover a point for its own coverage before reading a shift as a real change.")
            progress_df = progress_df.assign(
                hover_coverage=progress_df.apply(
                    lambda r: f"{int(r.n_analyzed)} of {int(r.n_total_games)} games ({r.coverage_pct:.1f}%)",
                    axis=1))
            acpl_col, win_col = st.columns(2)
            with acpl_col:
                st.caption("ACPL by month (lower = more accurate)")
                st.plotly_chart(
                    charts.line_chart(progress_df, "period", "acpl", theme.NEGATIVE, height=240,
                                      x_title="Month", y_title="ACPL",
                                      hover_extra=("hover_coverage", "Analyzed")),
                    theme=None, width='stretch')
            with win_col:
                st.caption("Win rate % by month")
                st.plotly_chart(
                    charts.line_chart(progress_df, "period", "win_pct", theme.POSITIVE, height=240,
                                      x_title="Month", y_title="Win rate (%)",
                                      hover_extra=("hover_coverage", "Analyzed")),
                    theme=None, width='stretch')

    _render_coaching_teaser(sqlite_conn, insights_page)

    _render_quick_explore({
        "insights_page": insights_page,
        "patterns_page": patterns_page,
        "openings_page": openings_page,
    })
