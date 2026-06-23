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


def bar_chart(df, x, y, color, height=320):
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y], marker_color=color,
        hovertemplate=f"%{{x}}<br>{_title_case(y)}: %{{y:.2f}}<extra></extra>",
    ))
    # automargin=True -- caught by actually looking at the rendered Game
    # Endings chart, not assumed fine: long category labels (e.g.
    # "time_forfeit") get auto-rotated by Plotly, and without this the
    # rotated labels visually overlap the x-axis title underneath them.
    # Exactly the kind of label-legibility bug this project treats as the
    # bar to clear (see the Opponents tab's score_pct->"sco" precedent).
    fig.update_layout(title_text="", height=height,
                       xaxis=dict(title=_title_case(x), automargin=True),
                       yaxis=dict(title=_title_case(y), automargin=True))
    return theme.apply_plotly_theme(fig)


def grouped_bar_chart(df, x, group_col, y, colors=None, height=320):
    """Multi-series bar chart -- e.g. piece type (x) split by game phase
    (group_col), values = blunder rate (y). df is long-form: one row per
    (x, group) pair, same shape data.py's other functions already return.
    colors: optional {group_value: hex} dict; falls back to cycling the
    three theme accent colors in the order groups first appear."""
    default_colors = [theme.ACCENT_GOLD, theme.POSITIVE, theme.NEGATIVE]
    groups = list(dict.fromkeys(df[group_col]))  # de-duped, order-preserving
    fig = go.Figure()
    for i, group in enumerate(groups):
        color = (colors or {}).get(group, default_colors[i % len(default_colors)])
        sub = df[df[group_col] == group]
        fig.add_trace(go.Bar(
            x=sub[x], y=sub[y], name=str(group), marker_color=color,
            hovertemplate=f"%{{x}}<br>{group}<br>{_title_case(y)}: %{{y:.2f}}<extra></extra>",
        ))
    fig.update_layout(title_text="", height=height, barmode="group",
                       xaxis=dict(title=_title_case(x), automargin=True),
                       yaxis=dict(title=_title_case(y), automargin=True))
    return theme.apply_plotly_theme(fig)


def line_chart(df, x, y, color, height=320):
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers", line=dict(color=color, width=2),
        marker=dict(size=5),
        hovertemplate=f"%{{x}}<br>{_title_case(y)}: %{{y:.2f}}<extra></extra>",
    ))
    fig.update_layout(title_text="", height=height,
                       xaxis_title=_title_case(x), yaxis_title=_title_case(y))
    return theme.apply_plotly_theme(fig)


def heatmap(pivoted_df, colorscale, value_suffix="", height=380):
    """pivoted_df: a DataFrame already shaped index=rows, columns=cols,
    values=cell values (data.py's heatmap-producing functions already
    return this shape). NO in-cell text -- the structural fix for the
    measured ~2.1-2.2:1 contrast failure on the old background_gradient
    tables (see theme.py docstring): exact values live in the hover
    tooltip and the colorbar, never as text rendered against a
    variable-lightness cell background."""
    fig = go.Figure(go.Heatmap(
        z=pivoted_df.values,
        x=[str(c) for c in pivoted_df.columns],
        y=[str(i) for i in pivoted_df.index],
        colorscale=colorscale,
        hovertemplate=f"%{{y}} / %{{x}}: %{{z:.1f}}{value_suffix}<extra></extra>",
        colorbar=dict(outlinewidth=0, tickfont=dict(color=theme.TEXT)),
    ))
    fig.update_layout(title_text="", height=height)
    return theme.apply_plotly_theme(fig)
