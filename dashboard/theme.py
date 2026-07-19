"""Phase 6b design system: the 'Midnight Study' palette, picked and
signed off by the user from 3 live-rendered options (see PROJECT_BRIEF.md).
One accent (gold) plus a green/red semantic pair for good/bad metrics --
not decorative extra colors, the green/red pair is what every chart needs
to encode win-vs-loss / mistake-rate anyway.

Phase 6c.2 reassessment (2026-06-22): palette re-evaluated against the
restructured information architecture (narrative-driven Overview,
drill-down navigation, highlight-reel framing) rather than assumed to
still fit. Verdict: kept as-is, not re-run as a fresh 3-option spike --
the dashboard's emotional register (quiet, contemplative, literary) is
if anything a better match for the narrative-heavy redesign than before,
and the actual problems found below are all USAGE bugs (how color gets
applied to text/labels), not hue choices. Confirmed via real WCAG
contrast ratios, not eyeballing -- the same "verify, don't assume"
discipline as the berserk-detection threshold:

    TEXT on BG                    14.27 : 1   (AA normal text needs 4.5)
    TEXT on BG_SECONDARY          12.36 : 1
    ACCENT_GOLD on BG              6.77 : 1
    ACCENT_GOLD on BG_SECONDARY    5.87 : 1
    POSITIVE on BG                 6.55 : 1
    POSITIVE on BG_SECONDARY       5.67 : 1
    NEGATIVE on BG                 3.69 : 1   (passes AA LARGE text only, >=3.0)
    NEGATIVE on BG_SECONDARY       3.20 : 1   (passes AA LARGE text only)
    Plotly's default tick/legend color (black) on BG_SECONDARY  1.36 : 1  FAIL

Two concrete rules that follow directly from these numbers:
1. NEGATIVE is for bars/large numbers/badges only -- never small body text
   or captions. If small red text is ever needed, use TEXT with a colored
   marker/icon instead of coloring the text itself.
2. Every Plotly chart MUST go through apply_plotly_theme() below before
   rendering. Plotly's default template assumes a light page background;
   used as-is on this dark theme, axis labels and legend text render in
   near-black at ~1.36:1 contrast -- invisible, not just suboptimal. This
   is the same class of bug as the Opponents tab's score_pct->"sco"
   clipping bug: a real, measured failure, not a hypothetical one.
"""

BG = "#14181F"
BG_SECONDARY = "#1E2530"
ACCENT_GOLD = "#C19A4B"
POSITIVE = "#6FA98C"
NEGATIVE = "#B0584F"
TEXT = "#E8E6E1"
TEXT_MUTED = "#E8E6E199"  # TEXT at ~60% opacity -- captions/secondary text,
                           # still 8.5:1+ on both backgrounds, well above AA

# Categorical series colors for IDENTITY encoding (e.g. the Opening Tree
# timeline's one-color-per-move chart). Deliberately NOT built from
# ACCENT_GOLD/POSITIVE/NEGATIVE: POSITIVE/NEGATIVE carry win/loss status
# semantics throughout this dashboard and must never double as "series 3".
# Chosen from the dataviz reference dark palette and machine-validated
# (validate_palette.js) against BG #14181F on 2026-07-05: all four inside
# the dark lightness band, chroma >= 0.1, worst adjacent-pair CVD dE 58
# (target >= 12), all >= 3:1 contrast on BG. Assign in this fixed order by
# series rank; fold overflow series into "Other" (CATEGORICAL_OTHER), never
# invent a 5th hue.
CATEGORICAL_SERIES = ["#3987e5", "#c98500", "#9085e9", "#d95926"]
CATEGORICAL_OTHER = "#8A8F98"  # neutral by design -- "Other" reads as gray

# ---------------------------------------------------------------------------
# Typography scale (Phase 6c.2) -- previously just Streamlit's unstyled
# st.title/st.subheader/st.caption defaults, no deliberate hierarchy.
# rem-based, applied via CSS injection (see CSS below) rather than per-call
# styling, so every page gets the same scale automatically.
# ---------------------------------------------------------------------------
TYPE_SCALE = {
    "page_title": ("2.4rem", 700),       # one per page, the page's own identity
    "section_header": ("1.4rem", 600),   # st.subheader -- one per logical panel
    "body": ("1rem", 400),
    "caption": ("0.85rem", 400),         # methodology/explanatory text -- see
                                           # CAPTION CONVENTION below
}

# ---------------------------------------------------------------------------
# Explanatory-text convention (Phase 6c.2): exactly ONE pattern, not ad hoc
# per panel. A caption goes directly under that panel's st.subheader(),
# in TEXT_MUTED, ONLY when the panel's meaning genuinely isn't obvious
# without already knowing this project's vocabulary (ACPL, material_sig,
# sharpness, drama_score, badge definitions) -- not decoration on panels
# that are already self-explanatory from their title + axis labels alone.
# No popovers, no tooltips, no inline asides -- one place, one look, so a
# reader learns where to find context instead of hunting per-panel.
# ---------------------------------------------------------------------------

# Spacing rhythm: a single scale, not ad hoc rem values scattered through
# app.py. Streamlit's default block-to-block gap (~1rem) is what produces
# the "large dead space" look once a page has 4-6 stacked panels -- the CSS
# below tightens inter-block spacing and relies on CARD styling (below) to
# provide the actual visual separation, instead of whitespace doing both
# jobs at once.
SPACE = {"xs": "0.4rem", "sm": "0.8rem", "md": "1.2rem", "lg": "2rem"}

# ---------------------------------------------------------------------------
# Card treatment (Phase 6c.2): use Streamlit's NATIVE st.container(border=True)
# as the card primitive -- same "use the native mechanism, don't build a
# custom workaround" principle as st.navigation/on_select in 6c.1 -- rather
# than hand-rolling div wrappers via unsafe_allow_html. The CSS below only
# RESTYLES that native bordered container to match the palette (background,
# border color, radius, padding); it doesn't replace the mechanism.
# CAVEAT, stated plainly rather than asserted with false confidence: the
# exact CSS selector Streamlit emits for a bordered container can shift
# between versions and needs confirming against the actually-running app
# (1.58.0) before this is relied on -- that verification belongs to 6c.3's
# build step, not this spec. Selector below is the current best-known one
# (`stVerticalBlockBorderWrapper`) and may need correcting then.
# ---------------------------------------------------------------------------

def rgba(hex_color, alpha):
    """Plotly color properties (shape/line/grid/etc.) reject CSS-style
    8-digit hex-with-alpha (e.g. f"{TEXT}40") -- caught by actually
    running the eval graph, not by inspection: Plotly only accepts
    hex/rgb/rgba/hsl/named colors, not hex+alpha. Use this instead,
    anywhere an alpha-blended theme color is passed to a Plotly property
    rather than HTML/CSS (where the f"{COLOR}40" pattern is fine, e.g.
    theme.CSS)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Plotly theme (Phase 6c.2): every st.plotly_chart call MUST pass its figure
# through apply_plotly_theme() before rendering. Plotly's default template
# assumes a light page -- left as-is, axis/legend/hover text renders in
# near-black at ~1.36:1 contrast against this dark background (see module
# docstring). This is the single enforcement point for that rule.
# ---------------------------------------------------------------------------
PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG,
    plot_bgcolor=BG_SECONDARY,
    font=dict(color=TEXT, size=13),
    title_font=dict(color=TEXT, size=18),
    legend=dict(bgcolor=BG_SECONDARY, font=dict(color=TEXT)),
    xaxis=dict(gridcolor=rgba(TEXT, 0.1), linecolor=rgba(TEXT, 0.33), tickfont=dict(color=TEXT),
               title_font=dict(color=TEXT)),
    yaxis=dict(gridcolor=rgba(TEXT, 0.1), linecolor=rgba(TEXT, 0.33), tickfont=dict(color=TEXT),
               title_font=dict(color=TEXT)),
    hoverlabel=dict(bgcolor=BG_SECONDARY, font=dict(color=TEXT)),
    margin=dict(l=40, r=20, t=40, b=40),
)


def apply_plotly_theme(fig):
    """Mandatory pass-through for every Plotly figure before st.plotly_chart.
    Returns the same figure (mutated), so this composes as
    `st.plotly_chart(theme.apply_plotly_theme(fig))`."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


# Plotly-native colorscales (Plotly wants [[position, color], ...] lists,
# not matplotlib Colormap objects) -- for the two heatmap tables currently
# rendered via pandas Styler.background_gradient, which has a REAL,
# CURRENTLY-PRESENT legibility bug: TEXT against the lightest end of either
# existing matplotlib colormap measures only ~2.1-2.2:1 contrast (fails even
# AA large-text). Fix is structural, not a color tweak: Plotly go.Heatmap
# with NO in-cell text at all, exact values via hover only (font color
# problem can't occur if there's no on-cell text to begin with), plus a
# themed colorbar. Replacing diverging_cmap()/sequential_gold_cmap()'s
# call sites is 6c.3/6c.4 work, not this spec -- kept below unchanged for
# any remaining matplotlib use, not yet removed.
DIVERGING_COLORSCALE = [[0.0, NEGATIVE], [0.5, BG_SECONDARY], [1.0, POSITIVE]]
SEQUENTIAL_GOLD_COLORSCALE = [[0.0, BG_SECONDARY], [1.0, ACCENT_GOLD]]


# ---------------------------------------------------------------------------
# Empty/thin-data state (Phase 6c.2 spec; built in 6c.5): a panel backed by
# too few analyzed games should never just render a near-blank chart and
# look broken. One consistent message, not a different ad hoc string per
# panel.
# ---------------------------------------------------------------------------
def thin_data_message(n_analyzed, min_required):
    return (f"Not enough data yet -- {n_analyzed} analyzed game(s), "
            f"need at least {min_required} for this view to be meaningful. "
            f"It'll fill in as more games are analyzed.")

# chess.svg.board(colors=...) -- recolors the board to sit inside the
# palette instead of clashing with python-chess's default orange/tan.
BOARD_COLORS = {
    "square light": "#D9C9A3",
    "square dark": "#7C5B3F",
    "square light lastmove": "#E3D9A8",
    "square dark lastmove": "#8C7330",
    "margin": BG_SECONDARY,
    "coord": TEXT,
    "inner border": "#10141A",
    "outer border": "#10141A",
}

# Per-move classification color coding for the annotated move list.
CLASSIFICATION_BG = {
    "blunder": f"background-color: {NEGATIVE}55",
    "mistake": f"background-color: {NEGATIVE}2C",
    "inaccuracy": f"background-color: {ACCENT_GOLD}2C",
    "good": "",
    "excellent": f"background-color: {POSITIVE}2C",
    "best": f"background-color: {POSITIVE}55",
}

# Story-worthiness badges -> (label, semantic class). Matches the booleans
# computed in data.get_game_badges().
BADGE_CHIPS = {
    "is_comeback": ("Comeback", "chip-positive"),
    "is_giant_killing": ("Giant-killing", "chip-positive"),
    "is_brilliant_find": ("Brilliant find", "chip-positive"),
    "is_blunder_fest": ("Blunder-fest", "chip-negative"),
    "is_nail_biter": ("Nail-biter", "chip-neutral"),
}

# One shared plain-language definition of the badges above -- shown as a
# caption wherever badge chips appear without other context (Overview,
# Game Detail, Game Explorer's filter). Keep the wording in sync with
# BADGE_CHIPS rather than re-writing it per page.
BADGE_LEGEND = ("Comeback: won/drew after being clearly lost. Giant-killing: beat a "
                "much higher-rated opponent. Brilliant find: a real sacrifice that "
                "worked. Blunder-fest: several big mistakes in one game. Nail-biter: "
                "result stayed in doubt until late.")

CSS = f"""
<style>
/* Off-brand default Streamlit chrome -- this is a finished personal
   dashboard, not a tool that needs its own deploy button surfaced. */
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
[data-testid="stToolbar"] {{visibility: hidden;}}
/* The sidebar's own re-expand control (shown only once the sidebar is
   collapsed) lives inside stToolbar in this Streamlit version -- CSS
   visibility is inherited, so hiding the whole toolbar above silently
   also hid this, leaving no way to re-open a collapsed sidebar. Confirmed
   live via computed-style + DOM inspection (element present, "visibility:
   hidden", ancestor chain running through stToolbar) before adding this
   override. */
[data-testid="stExpandSidebarButton"] {{visibility: visible;}}

.chip {{
    display: inline-block;
    padding: 0.15rem 0.7rem;
    margin: 0 0.35rem 0.35rem 0;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid;
}}
.chip-positive {{
    background-color: {POSITIVE}26;
    border-color: {POSITIVE};
    color: {POSITIVE};
}}
.chip-negative {{
    background-color: {NEGATIVE}26;
    border-color: {NEGATIVE};
    color: {NEGATIVE};
}}
.chip-neutral {{
    background-color: {ACCENT_GOLD}26;
    border-color: {ACCENT_GOLD};
    color: {ACCENT_GOLD};
}}
/* Muted variant (confidence.py's "low" tier badge) -- deliberately less
   prominent than chip-neutral, which is also used for the "medium" tier
   and story-worthiness badges elsewhere; low-confidence findings should
   read as quieter, not equal-weight. */
.chip-muted {{
    background-color: {TEXT}14;
    border-color: {TEXT}33;
    color: {TEXT_MUTED};
}}

.narrative-quote {{
    background-color: {BG_SECONDARY};
    border-left: 3px solid {ACCENT_GOLD};
    border-radius: 4px;
    padding: 1rem 1.4rem;
    margin: 0.5rem 0 1.3rem 0;
    font-size: 1.05rem;
    line-height: 1.65;
    font-style: italic;
}}

.game-id-caption {{
    color: {TEXT}99;
    font-size: 0.85rem;
    margin-top: -0.6rem;
}}

/* Typography scale (6c.2) -- previously default/unstyled st.title,
   st.subheader, st.caption with no deliberate hierarchy. */
h1 {{
    font-size: {TYPE_SCALE["page_title"][0]} !important;
    font-weight: {TYPE_SCALE["page_title"][1]} !important;
    letter-spacing: -0.01em;
    margin-bottom: {SPACE["md"]} !important;
}}
h3 {{
    font-size: {TYPE_SCALE["section_header"][0]} !important;
    font-weight: {TYPE_SCALE["section_header"][1]} !important;
    margin-top: {SPACE["lg"]} !important;
    margin-bottom: {SPACE["xs"]} !important;
}}
[data-testid="stCaptionContainer"] {{
    color: {TEXT_MUTED} !important;
    font-size: {TYPE_SCALE["caption"][0]} !important;
}}

/* Spacing rhythm (6c.2) -- tighten Streamlit's default block-to-block gap,
   which is what produces "large dead space" once a page stacks several
   panels; CARD styling below does the visual separation instead. */
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {{
    margin-bottom: {SPACE["xs"]};
}}

/* Streamlit's own default top-of-page padding (96px, confirmed live via
   getComputedStyle -- not a value this app ever set) reads as unused
   space above the fold, worst on short pages like Overview where it's a
   bigger fraction of the visible content. 96px -> 24px, confirmed live
   to not collide with the sidebar-collapse control. Not on the SPACE
   scale above -- that scale is for inter-element rhythm, this is a
   one-off page-edge margin, a different kind of measurement. */
[data-testid="stMainBlockContainer"] {{
    padding-top: 1.5rem;
}}

/* Card treatment (6c.2) -- restyles st.container(border=True), Streamlit's
   NATIVE bordered-container primitive, to match the palette. Selector
   needs confirming against the live 1.58.0 app in 6c.3 -- noted in the
   module docstring above, not asserted as already-verified here. */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color: {BG_SECONDARY};
    border: 1px solid {TEXT}1A;
    border-radius: 8px;
    padding: {SPACE["md"]};
    margin-bottom: {SPACE["md"]};
}}

/* st.spinner (23 call sites app-wide) -- last piece of native Streamlit
   chrome with zero custom styling in an otherwise fully-themed dark app.
   Confirmed live (Streamlit 1.58.0) it's a CSS border-ring, not an SVG:
   [data-testid="stSpinnerIcon"] is a bare <span> whose rotating ring is
   drawn via the border-color 3-value shorthand (top / left+right /
   bottom), solid on top and 20%-opacity on the other two sides. That
   border-color comes from an emotion-generated class of matching
   specificity, so !important is needed to reliably win. Message text
   already inherits {TEXT} from this app's .streamlit/config.toml
   textColor, but set it explicitly here too so the whole element's
   theming lives in one place rather than half in config.toml, half
   implicit. */
[data-testid="stSpinner"] {{
    color: {TEXT};
}}
[data-testid="stSpinnerIcon"] {{
    border-color: {ACCENT_GOLD} {ACCENT_GOLD}33 {ACCENT_GOLD}33 !important;
}}

/* Generalized gold-tinted card treatment (roadmap Sec.15 unit #2) -- was
   .focus-card, a one-off for Overview's "focus for next session" card;
   renamed to .metric-card and extended (value/delta/label rows added
   below) so render_metric_card() in this file can serve both that
   eyebrow/headline/detail shape AND a KPI/value shape (big number +
   delta + optional sparkline/confidence/sample-size), reusing exactly
   this same background tint + left gold border rather than forking the
   styling per shape. Visually distinct from .narrative-quote (also a
   gold border) via the background tint and the eyebrow label treatment. */
.metric-card {{
    background-color: {ACCENT_GOLD}0D;
    border-left: 3px solid {ACCENT_GOLD};
    border-radius: 4px;
    padding: 1rem 1.4rem;
    margin: 0 0 1rem 0;
}}
.metric-card-eyebrow {{
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {ACCENT_GOLD};
    margin-bottom: 0.4rem;
}}
.metric-card-headline {{
    font-size: 1.05rem;
    font-weight: 600;
    color: {TEXT};
    margin-bottom: 0.25rem;
}}
.metric-card-detail {{
    font-size: 0.85rem;
    color: {TEXT_MUTED};
}}
/* KPI/value shape additions -- big value, optional colored delta next to
   it (reuses POSITIVE/NEGATIVE per the module docstring's rule 1: color
   is fine here since it's a large number, not small body text), optional
   label underneath. */
.metric-card-value-row {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    flex-wrap: wrap;
}}
.metric-card-value {{
    font-size: 1.8rem;
    font-weight: 700;
    color: {TEXT};
    line-height: 1.1;
}}
.metric-card-delta-positive {{
    font-size: 0.95rem;
    font-weight: 600;
    color: {POSITIVE};
}}
.metric-card-delta-negative {{
    font-size: 0.95rem;
    font-weight: 600;
    color: {NEGATIVE};
}}
.metric-card-label {{
    font-size: 0.8rem;
    color: {TEXT_MUTED};
    margin-top: 0.15rem;
}}

/* Engine-move explanation block in Game Detail -- italic lightbulb style,
   same gold family as the focus card, shorter padding since it's inline
   with the move caption area. */
.explain-block {{
    background-color: {ACCENT_GOLD}0D;
    border-left: 3px solid {ACCENT_GOLD};
    border-radius: 4px;
    padding: 0.55rem 1rem;
    margin: 0.3rem 0 0.5rem 0;
    font-size: 0.95rem;
    line-height: 1.6;
    font-style: italic;
    color: {TEXT};
}}
</style>
"""


def diverging_cmap():
    """Red (bad) -> secondary bg -> green (good), for win-rate-style heatmaps,
    built from the same palette instead of matplotlib's default RdYlGn."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(
        "midnight_diverging", [NEGATIVE, BG_SECONDARY, POSITIVE])


def sequential_gold_cmap():
    """Secondary bg -> gold, for plain-intensity (non good/bad) heatmaps."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(
        "midnight_sequential", [BG_SECONDARY, ACCENT_GOLD])


def chip_row_html(flags) -> str:
    """flags: mapping (or pandas Series/row) of badge column -> truthy value.
    Returns an empty string if no badges qualify (caller should skip
    rendering the container entirely in that case)."""
    spans = [
        f'<span class="chip {cls}">{label}</span>'
        for col, (label, cls) in BADGE_CHIPS.items()
        if bool(flags.get(col))
    ]
    return "".join(spans)


def _confidence_html(confidence) -> str:
    """confidence: None, a bare tier name (e.g. what
    dashboard/confidence.py's confidence_tier() returns), or ready-made
    badge HTML (confidence.confidence_badge_html()'s return value).
    Deliberately no hard import of dashboard/confidence.py at module load
    time -- render_metric_card() must degrade gracefully whether or not
    that module is present, per roadmap Sec.15 unit #2's brief. A bare
    string containing "<" is assumed to already be markup and passed
    through as-is; otherwise this tries the real badge renderer and falls
    back to a plain chip-neutral span if that module can't be imported or
    doesn't recognize the tier name."""
    if not confidence:
        return ""
    if "<" in confidence:
        return confidence
    try:
        import confidence as confidence_mod
        html = confidence_mod.confidence_badge_html(confidence)
        if html:
            return html
    except Exception:
        pass
    return f'<span class="chip chip-neutral">{confidence}</span>'


def _render_sparkline(sparkline, key=None) -> None:
    """sparkline: a plotly Figure, or a plain sequence of y-values (plotted
    as a minimal axis-free line). Always routed through
    apply_plotly_theme() per this module's own house rule, then stripped
    down further (no axes/gridlines/legend/modebar) since a sparkline's
    only job is showing shape, not being read precisely."""
    import plotly.graph_objects as go
    import streamlit as st

    if isinstance(sparkline, go.Figure):
        fig = sparkline
    else:
        y = list(sparkline)
        fig = go.Figure(go.Scatter(
            x=list(range(len(y))), y=y, mode="lines",
            line=dict(color=ACCENT_GOLD, width=2)))
    fig = apply_plotly_theme(fig)
    fig.update_layout(height=48, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
    fig.update_xaxes(visible=False, showgrid=False)
    fig.update_yaxes(visible=False, showgrid=False)
    st.plotly_chart(fig, theme=None, use_container_width=True,
                     config={"displayModeBar": False},
                     key=f"metric_card_sparkline_{key}" if key else None)


def render_metric_card(*, value=None, label=None, delta=None, sparkline=None,
                        confidence=None, sample_size=None,
                        eyebrow=None, headline=None, detail=None,
                        key=None) -> None:
    """One shared `.metric-card` treatment (gold-tinted background, left
    gold border -- see the CSS block above) for two real shapes, so a
    caller passes whichever param group matches what it needs and only
    the non-None fields render:

    KPI/value shape (net-new; roadmap Sec.15 unit #2's named target
    signature, no current caller):
        render_metric_card(value="62%", label="Win rate", delta="+4",
                            sparkline=[54, 58, 55, 60, 62],
                            confidence="high", sample_size="128 games")
    Headline/detail shape (overview_view.py's "focus for your next
    session" card -- the one real, existing call site, migrated here from
    its old raw st.markdown(f'<div class="focus-card">...') block):
        render_metric_card(eyebrow="Focus for your next session",
                            headline="...", detail="...")
    A caller needing a nav button below the card (overview_view.py's
    "Explore in X ->") still renders that itself underneath -- button
    placement/st.columns layout stays the caller's job, not this
    component's.

    `confidence` accepts either a bare tier name or ready-made badge HTML
    -- see _confidence_html() above; works with or without
    dashboard/confidence.py present. `delta` is shown in NEGATIVE if its
    string form starts with "-", POSITIVE otherwise (per this module's
    own contrast rule: color on a short badge-like span is fine, this is
    not small body text). `sparkline` accepts a plotly Figure or a plain
    sequence of y-values. `key` disambiguates the sparkline's Streamlit
    element key when multiple KPI cards render on one page.
    """
    import streamlit as st

    parts = ['<div class="metric-card">']
    if eyebrow:
        parts.append(f'<div class="metric-card-eyebrow">{eyebrow}</div>')
    if headline:
        parts.append(f'<div class="metric-card-headline">{headline}</div>')
    if detail:
        parts.append(f'<div class="metric-card-detail">{detail}</div>')

    if value is not None:
        delta_html = ""
        if delta is not None:
            delta_str = str(delta)
            delta_cls = ("metric-card-delta-negative" if delta_str.strip().startswith("-")
                         else "metric-card-delta-positive")
            delta_html = f'<span class="{delta_cls}">{delta_str}</span>'
        parts.append(
            '<div class="metric-card-value-row">'
            f'<span class="metric-card-value">{value}</span>'
            f'{delta_html}{_confidence_html(confidence)}'
            '</div>'
        )
        if label:
            parts.append(f'<div class="metric-card-label">{label}</div>')

    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)

    if sparkline is not None:
        _render_sparkline(sparkline, key=key)
    if sample_size:
        st.caption(sample_size)


def render_comparison_panel(panes, mode="side_by_side", *, shared_caption=None,
                             x_title=None, y_title=None, height=320):
    """Generalizes the `col1, col2 = st.columns(2)` pattern duplicated
    across patterns_view.py (win_pct/ACPL chart pairs, each followed by
    ONE caption spanning both columns -- see `_coverage_caption`) and
    matchups_view.py (metric pairs, each with its OWN caption underneath).
    *panes* is a 2-item sequence of dicts; which keys matter depends on
    *mode*.

    mode="side_by_side" (the only mode with a real caller today):
        pane["render"]: callable() -> None, rendering that pane's content
            (a plotly chart, an st.metric, a table -- anything) into its
            own column. Required.
        pane["caption"]: optional str, rendered via st.caption() under
            THAT column only (matchups_view.py's per-pane pattern).
        *shared_caption*: optional str, rendered via st.caption() below
            BOTH columns instead (patterns_view.py's pattern) -- takes
            priority over per-pane captions if both are supplied, since
            no current call site needs both at once.

    mode="overlay" / "difference" (no current caller -- Phase 2's
    Favorite vs Underdog comparison, roadmap Sec.15 unit #3, is the
    first; kept deliberately simple since nothing exercises these yet).
    Each pane instead needs pane["df"]/pane["x"]/pane["y"], long-form data
    the same shape charts.py's other builders take, plus optional
    pane["label"] (trace/series name) and pane["color"]:
        "overlay": both panes' (x, y) series plotted as two grouped bar
            traces on one chart -- e.g. favorite's win_pct next to
            underdog's win_pct across the same x categories.
        "difference": a single delta chart of pane[1].y - pane[0].y per
            matching x category (outer-joined on x; a category missing
            from one side is treated as 0 for that side).
    Both non-side_by_side modes return the built, already-themed Figure
    instead of rendering it (no st.plotly_chart call) -- the first real
    caller decides how/whether to display it and add its own caption.
    """
    import streamlit as st

    if len(panes) != 2:
        raise ValueError("render_comparison_panel needs exactly 2 panes")

    if mode == "side_by_side":
        col1, col2 = st.columns(2)
        for col, pane in zip((col1, col2), panes):
            with col:
                pane["render"]()
                if shared_caption is None and pane.get("caption"):
                    st.caption(pane["caption"])
        if shared_caption:
            st.caption(shared_caption)
        return None

    import pandas as pd
    import plotly.graph_objects as go

    pane_a, pane_b = panes
    default_colors = [ACCENT_GOLD, POSITIVE]

    if mode == "overlay":
        fig = go.Figure()
        for i, pane in enumerate((pane_a, pane_b)):
            df, x, y = pane["df"], pane["x"], pane["y"]
            color = pane.get("color", default_colors[i % len(default_colors)])
            fig.add_trace(go.Bar(x=df[x], y=df[y],
                                  name=pane.get("label", f"Series {i + 1}"),
                                  marker_color=color))
        fig.update_layout(barmode="group", height=height,
                           xaxis=dict(title=x_title, automargin=True),
                           yaxis=dict(title=y_title, automargin=True))
        return apply_plotly_theme(fig)

    if mode == "difference":
        df_a, x_a, y_a = pane_a["df"], pane_a["x"], pane_a["y"]
        df_b, x_b, y_b = pane_b["df"], pane_b["x"], pane_b["y"]
        merged = pd.merge(
            df_a[[x_a, y_a]].rename(columns={x_a: "_x", y_a: "_a"}),
            df_b[[x_b, y_b]].rename(columns={x_b: "_x", y_b: "_b"}),
            on="_x", how="outer").fillna(0)
        merged["_delta"] = merged["_b"] - merged["_a"]
        colors = [POSITIVE if v >= 0 else NEGATIVE for v in merged["_delta"]]
        label_a = pane_a.get("label", "A")
        label_b = pane_b.get("label", "B")
        fig = go.Figure(go.Bar(x=merged["_x"], y=merged["_delta"], marker_color=colors))
        fig.update_layout(height=height,
                           xaxis=dict(title=x_title, automargin=True),
                           yaxis=dict(title=y_title or f"{label_b} minus {label_a}",
                                      automargin=True))
        return apply_plotly_theme(fig)

    raise ValueError(f"Unknown render_comparison_panel mode: {mode!r}")
