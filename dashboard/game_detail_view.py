"""
Phase 6c.3: per-game story view, rebuilt as its own module (was inline in
app.py) -- the highest-stakes single screen in the dashboard, used as the
validation case for the broader Phase 6c redesign. Reached only via
navigation (Game Explorer, Tactical Highlights, etc. -- see 6c.4), never
shown in the sidebar nav itself (st.Page(..., visibility="hidden")).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import chess
import chess.svg

import claude_narrative
import data
import narrative
import theme
from _common import get_connections
from game_explorer_view import cached_game_explorer_table


@st.cache_data
def cached_game_detail(_duck_conn, game_id):
    return data.get_game_detail(_duck_conn, game_id)


def _eval_graph(moves, ply, on_point_click_ply_key):
    wp = narrative.player_win_prob_series(moves)
    if len(wp) < 2:
        # win_prob_after is only populated once BOTH worker.py (analysis)
        # AND annotate.py (annotation) have run on this game -- a game
        # that's been analyzed but not yet annotated has zero rows here,
        # not a partial trace. Previously a silent `return` -- left the
        # user with no chart and no explanation (reported live as "I
        # can't see the evaluation graph"). Tell them why, and point at
        # the Analysis Jobs page, which now surfaces exactly this gap.
        st.info("Not enough annotated moves yet to draw an evaluation graph for this game. "
                "It's likely been analyzed but not yet annotated -- check the Analysis Jobs "
                "page for games awaiting annotation.")
        return
    fig = go.Figure()
    fig.add_hline(y=0.5, line_dash="dot", line_color=theme.rgba(theme.TEXT, 0.25))
    fig.add_trace(go.Scatter(
        x=wp.ply, y=wp.player_win_prob, mode="lines", line=dict(color=theme.ACCENT_GOLD, width=2),
        fill="tozeroy", fillcolor=theme.rgba(theme.ACCENT_GOLD, 0.08), hoverinfo="skip",
    ))
    # A second, invisible-line scatter purely to host larger, easier-to-click
    # markers without cluttering the trace itself with a marker every ply.
    fig.add_trace(go.Scatter(
        x=wp.ply, y=wp.player_win_prob, mode="markers",
        marker=dict(size=6, color=theme.ACCENT_GOLD, opacity=0.0),
        hovertemplate="Move %{customdata}<br>Win prob: %{y:.0%}<extra></extra>",
        customdata=[(p + 1) // 2 for p in wp.ply],
    ))
    fig.add_vline(x=ply, line_color=theme.TEXT, line_width=1.5)
    # title_text="" (an explicit EMPTY STRING), not just absent -- found via
    # direct DOM inspection that an unset title still renders a <text
    # class="gtitle"> element through Streamlit's st.plotly_chart specifically
    # (not via Plotly's own raw HTML export, which omits it cleanly), and its
    # tspan content was the literal JS string "undefined" rather than blank.
    # The section header ("Browse the game") + the caption below already
    # explain this chart, so no real title text is wanted -- just not via
    # leaving the property absent.
    fig.update_layout(title_text="", showlegend=False, height=220,
                       xaxis_title="Move", yaxis_title="Your win probability",
                       yaxis=dict(range=[0, 1], tickformat=".0%"))
    theme.apply_plotly_theme(fig)
    event = st.plotly_chart(fig, on_select="rerun", selection_mode="points", key="eval_graph",
                             theme=None)
    if event and event.selection and event.selection.points:
        clicked_ply = int(wp.iloc[event.selection.points[0]["point_index"]].ply)
        st.session_state[on_point_click_ply_key] = clicked_ply


@st.cache_data
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


def render():
    sqlite_conn, duck_conn = get_connections()
    selected_game_id = st.session_state.get("selected_game_id")
    if not selected_game_id:
        st.warning("No game selected -- go back and click a game first.")
        return

    return_page = st.session_state.get("return_page")
    return_label = st.session_state.get("return_page_label", "Game Explorer")
    if return_page is not None and st.button(f"← Back to {return_label}"):
        st.switch_page(return_page)

    header, moves = cached_game_detail(duck_conn, selected_game_id)
    if moves.empty:
        st.warning(f"{selected_game_id} has no recorded moves (abandoned/forfeit game).")
        return

    badges_df = cached_game_explorer_table(duck_conn)
    badge_row = badges_df.loc[badges_df.game_id == selected_game_id]
    chips_html = theme.chip_row_html(badge_row.iloc[0]) if not badge_row.empty else ""

    st.title(f"{header.opponent_name} ({header.utc_date})")
    st.markdown(f'<p class="game-id-caption">Game {selected_game_id}</p>', unsafe_allow_html=True)
    if chips_html:
        st.markdown(chips_html, unsafe_allow_html=True)
    st.markdown(f'<div class="narrative-quote">{narrative.generate_narrative(header, moves)}</div>',
                unsafe_allow_html=True)

    critical_moments, turning_point, _n_other = narrative.select_critical_moments(moves)

    with st.container(border=True):
        st.subheader("Browse the game")
        num_plies = int(moves.ply.max())
        ply_key = f"browse_ply__{selected_game_id}"
        if ply_key not in st.session_state:
            st.session_state[ply_key] = critical_moments[0].ply if critical_moments else 1

        _eval_graph(moves, st.session_state[ply_key], ply_key)
        st.caption("Your win probability across the game, from the engine's evaluation at "
                   "each move -- click a point on the line to jump there.")

        if critical_moments:
            st.caption("Jump to a critical moment:")
            jump_cols = st.columns(len(critical_moments))
            for col, row in zip(jump_cols, critical_moments):
                is_tp = turning_point is not None and row.ply == turning_point.ply
                label = f"{(row.ply + 1) // 2}. {row.san}" + (" (turning point)" if is_tp else "")
                if col.button(label, key=f"jump__{selected_game_id}__{row.ply}"):
                    st.session_state[ply_key] = row.ply

        nav_prev, nav_slider, nav_next = st.columns([1, 8, 1])
        with nav_prev:
            if st.button("< Prev", key=f"prev__{selected_game_id}"):
                st.session_state[ply_key] = max(1, st.session_state[ply_key] - 1)
        with nav_next:
            if st.button("Next >", key=f"next__{selected_game_id}"):
                st.session_state[ply_key] = min(num_plies, st.session_state[ply_key] + 1)
        with nav_slider:
            ply = st.slider("Move", 1, num_plies, key=ply_key)

        row = moves[moves.ply == ply].iloc[0]
        board_before = chess.Board(row.fen_before)
        move = board_before.parse_san(row.san)
        fen_after = narrative.position_after_ply(moves, ply)
        board_after = chess.Board(fen_after)
        svg = chess.svg.board(board_after, size=420, lastmove=move,
                               flipped=(header.player_color == "black"),
                               colors=theme.BOARD_COLORS)
        st.markdown(svg, unsafe_allow_html=True)

        move_no = (ply + 1) // 2
        who = "White" if ply % 2 == 1 else "Black"
        mover = "You" if row.is_player_move else header.opponent_name
        detail = f" -- {row.classification}, cpl={int(row.cpl)}" if pd.notna(row.cpl) else ""
        st.caption(f"Move {move_no} ({who}, {mover}): {row.san}{detail}")

    with st.container(border=True):
        st.subheader("Tell me the story of this game")
        cached = data.get_cached_narrative(sqlite_conn, "game", selected_game_id)
        if cached:
            response_text, generated_at = cached
            st.caption(f"Generated {generated_at}")
            st.markdown(response_text)
        button_label = "Regenerate story" if cached else "Generate richer story"

        if not claude_narrative.api_key_available():
            st.info("Add your own Anthropic API key on the Settings page to enable this.")
        if st.button(button_label, disabled=not claude_narrative.api_key_available()):
            template_text = narrative.generate_narrative(header, moves)
            stats = cached_headline_stats(duck_conn, sqlite_conn)
            with st.spinner("Asking Claude..."):
                try:
                    rich_text = claude_narrative.generate_rich_narrative(
                        header, moves, template_text, critical_moments, turning_point,
                        stats["analyzed_games"], stats["total_games"])
                    data.save_narrative(sqlite_conn, "game", selected_game_id,
                                         rich_text, claude_narrative.MODEL)
                    st.rerun()
                except claude_narrative.MissingApiKeyError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Claude API call failed: {e}")

    with st.container(border=True):
        st.subheader("Full annotated move list")
        display_moves = moves.drop(
            columns=["fen_before", "win_prob_before", "win_prob_after"], errors="ignore").copy()
        for flag_col in ("is_player_move", "is_brilliant_candidate", "is_puzzle_trigger"):
            if flag_col in display_moves.columns:
                display_moves[flag_col] = display_moves[flag_col].map(
                    {1: "✓", 0: ""}).fillna("")
        styled_moves = display_moves.style.map(
            lambda v: theme.CLASSIFICATION_BG.get(v, ""), subset=["classification"])
        st.dataframe(styled_moves, width='stretch', column_config={
            "ply": "Ply",
            "san": "Move",
            "is_player_move": "Yours",
            "classification": "Quality",
            "cpl": "Centipawn Loss",
            "sharpness": "Sharpness",
            "is_brilliant_candidate": "Brilliant",
            "is_puzzle_trigger": "Puzzle Trigger",
        })
