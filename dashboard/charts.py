"""
Phase 6c.4: shared Plotly chart builders. Every Career Dashboard panel
that used to be st.bar_chart/st.line_chart (no real hover tooltips, no
exact-value-on-hover for thin-sample buckets) or a pandas
Styler.background_gradient heatmap (a REAL, measured legibility bug --
see theme.py's module docstring) goes through one of these instead, so
the apply_plotly_theme() dark-theme rule and the no-in-cell-text heatmap
fix are each enforced in exactly one place, not re-typed per panel.
"""
import plotly.graph_objects as go

import theme


def _title_case(s):
    return s.replace("_", " ").title()


def bar_chart(df, x, y, color, height=320, x_title=None, y_title=None):
    """x_title/y_title: human-readable axis labels. Every user-facing call
    should pass them -- the _title_case(column_name) fallback exists only
    so an unlabeled chart degrades to Title Case rather than a raw
    snake_case column name (the pre-2026-07-05 behavior produced axis
    titles like "Acpl" and "Bucket", which read as leaked internals)."""
    x_title = x_title or _title_case(x)
    y_title = y_title or _title_case(y)
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y], marker_color=color,
        hovertemplate=f"%{{x}}<br>{y_title}: %{{y:.2f}}<extra></extra>",
    ))
    # automargin=True -- caught by actually looking at the rendered Game
    # Endings chart, not assumed fine: long category labels (e.g.
    # "time_forfeit") get auto-rotated by Plotly, and without this the
    # rotated labels visually overlap the x-axis title underneath them.
    # Exactly the kind of label-legibility bug this project treats as the
    # bar to clear (see the Opponents tab's score_pct->"sco" precedent).
    fig.update_layout(title_text="", height=height,
                       xaxis=dict(title=x_title, automargin=True),
                       yaxis=dict(title=y_title, automargin=True))
    return theme.apply_plotly_theme(fig)


def grouped_bar_chart(df, x, group_col, y, colors=None, height=320,
                      x_title=None, y_title=None):
    """Multi-series bar chart -- e.g. piece type (x) split by game phase
    (group_col), values = blunder rate (y). df is long-form: one row per
    (x, group) pair, same shape data.py's other functions already return.
    colors: optional {group_value: hex} dict; falls back to cycling the
    three theme accent colors in the order groups first appear.
    x_title/y_title: see bar_chart."""
    x_title = x_title or _title_case(x)
    y_title = y_title or _title_case(y)
    default_colors = [theme.ACCENT_GOLD, theme.POSITIVE, theme.NEGATIVE]
    groups = list(dict.fromkeys(df[group_col]))  # de-duped, order-preserving
    fig = go.Figure()
    for i, group in enumerate(groups):
        color = (colors or {}).get(group, default_colors[i % len(default_colors)])
        sub = df[df[group_col] == group]
        fig.add_trace(go.Bar(
            x=sub[x], y=sub[y], name=str(group), marker_color=color,
            hovertemplate=f"%{{x}}<br>{group}<br>{y_title}: %{{y:.2f}}<extra></extra>",
        ))
    fig.update_layout(title_text="", height=height, barmode="group",
                       xaxis=dict(title=x_title, automargin=True),
                       yaxis=dict(title=y_title, automargin=True))
    return theme.apply_plotly_theme(fig)


def line_chart(df, x, y, color, height=320, x_title=None, y_title=None, hover_extra=None):
    """x_title/y_title: see bar_chart. hover_extra: optional (column, label)
    pair -- appends "label: <value>" to each point's hover text via
    customdata, for a per-point caveat (e.g. sample size or coverage %)
    that doesn't belong on the axis itself. Column values are used as-is,
    so format them into display strings in the caller before passing."""
    x_title = x_title or _title_case(x)
    y_title = y_title or _title_case(y)
    hovertemplate = f"%{{x}}<br>{y_title}: %{{y:.2f}}"
    customdata = None
    if hover_extra is not None:
        extra_col, extra_label = hover_extra
        customdata = df[extra_col]
        hovertemplate += f"<br>{extra_label}: %{{customdata}}"
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers", line=dict(color=color, width=2),
        marker=dict(size=5), customdata=customdata,
        hovertemplate=hovertemplate + "<extra></extra>",
    ))
    fig.update_layout(title_text="", height=height,
                       xaxis=dict(title=x_title, automargin=True),
                       yaxis=dict(title=y_title, automargin=True))
    return theme.apply_plotly_theme(fig)


def multi_line_chart(df, x, series, height=320, y_title="", x_title=None):
    """Two-or-more lines over one x axis -- e.g. actual vs. potential
    points per month. series: list of (column, display_label, hex_color)
    tuples; long-form pivoting stays the caller's job, same as
    grouped_bar_chart."""
    fig = go.Figure()
    for col, label, color in series:
        fig.add_trace(go.Scatter(
            x=df[x], y=df[col], name=label, mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=5),
            hovertemplate=f"%{{x}}<br>{label}: %{{y:.2f}}<extra></extra>",
        ))
    fig.update_layout(title_text="", height=height,
                       xaxis=dict(title=x_title or _title_case(x), automargin=True),
                       yaxis=dict(title=y_title, automargin=True))
    return theme.apply_plotly_theme(fig)


def stacked_bar_chart(df, x, group_col, y, colors, height=320,
                      x_title=None, y_title=None, y_suffix="",
                      integer_x=False):
    """Composition-over-x stacked bars -- e.g. share of each move (group_col)
    per year (x). df is long-form like grouped_bar_chart's. colors is a
    REQUIRED {group_value: hex} dict: identity coloring must come from
    theme.CATEGORICAL_SERIES (validated set, fixed assignment order), not a
    cycling default, so a missing entry is a caller bug worth surfacing --
    Plotly renders a None color as its own default palette, which is exactly
    the unvalidated-color path this builder exists to close off.
    integer_x=True formats the x axis as plain integers (dtick=1, no
    thousands separator) -- for year axes, where Plotly's default numeric
    formatting would render 2019 as "2,019" or halve into "2019.5" ticks.
    marker_line in BG gives the 2px surface gap between stacked segments
    (dataviz mark spec), matching the heatmap's no-in-cell-text spirit:
    segment identity comes from the legend + hover, not cramped labels."""
    x_title = x_title or _title_case(x)
    y_title = y_title or _title_case(y)
    groups = list(dict.fromkeys(df[group_col]))  # de-duped, order-preserving
    fig = go.Figure()
    for group in groups:
        sub = df[df[group_col] == group]
        fig.add_trace(go.Bar(
            x=sub[x], y=sub[y], name=str(group), marker_color=colors[group],
            marker_line=dict(color=theme.BG, width=2),
            hovertemplate=f"%{{x}}<br>{group}: %{{y:.1f}}{y_suffix}<extra></extra>",
        ))
    xaxis: dict = dict(title=x_title, automargin=True)
    if integer_x:
        xaxis.update(tickformat="d", dtick=1)
    fig.update_layout(title_text="", height=height, barmode="stack",
                       xaxis=xaxis,
                       yaxis=dict(title=y_title, automargin=True))
    return theme.apply_plotly_theme(fig)


def heatmap(pivoted_df, colorscale, value_suffix="", height=380,
            x_title=None, y_title=None, colorbar_title=None, hover_extra=None):
    """pivoted_df: a DataFrame already shaped index=rows, columns=cols,
    values=cell values (data.py's heatmap-producing functions already
    return this shape). NO in-cell text -- the structural fix for the
    measured ~2.1-2.2:1 contrast failure on the old background_gradient
    tables (see theme.py docstring): exact values live in the hover
    tooltip and the colorbar, never as text rendered against a
    variable-lightness cell background.

    hover_extra: optional (extra_pivoted_df, label) pair -- the 2D
    analogue of line_chart's hover_extra (see its docstring for the
    mechanism). extra_pivoted_df must share pivoted_df's index/columns
    values (reindexed here defensively, so a caller's differently-sorted
    frame still lines up cell-for-cell); appends "label: <value>" to every
    cell's hover text via a 2D customdata array. Same contract as
    line_chart's hover_extra: values are used as-is with no numeric
    format spec applied (confirmed live -- %{customdata:+.0f} silently
    renders the raw unformatted float in this Plotly build), so the
    caller must pre-format extra_pivoted_df's values into display strings."""
    colorbar: dict = dict(outlinewidth=0, tickfont=dict(color=theme.TEXT))
    if colorbar_title:
        colorbar["title"] = dict(text=colorbar_title, font=dict(color=theme.TEXT))
    hovertemplate = f"%{{y}} / %{{x}}: %{{z:.1f}}{value_suffix}"
    customdata = None
    if hover_extra is not None:
        extra_df, extra_label = hover_extra
        customdata = extra_df.reindex(index=pivoted_df.index, columns=pivoted_df.columns).values
        hovertemplate += f"<br>{extra_label}: %{{customdata}}"
    fig = go.Figure(go.Heatmap(
        z=pivoted_df.values,
        x=[str(c) for c in pivoted_df.columns],
        y=[str(i) for i in pivoted_df.index],
        colorscale=colorscale,
        customdata=customdata,
        hovertemplate=hovertemplate + "<extra></extra>",
        colorbar=colorbar,
    ))
    fig.update_layout(title_text="", height=height,
                       xaxis=dict(title=x_title or "", automargin=True),
                       yaxis=dict(title=y_title or "", automargin=True))
    return theme.apply_plotly_theme(fig)
