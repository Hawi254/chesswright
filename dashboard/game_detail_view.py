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

import chess_display
import claude_narrative
import components.chessboard as chessboard_component
import data
import live_engine
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


def _render_annotation_panel(sqlite_conn, variation_id: str, step: int,
                              current_fen: str) -> None:
    """Glyph selector + user comment + AI annotation for one variation position."""
    annotations = data.get_variation_annotations(sqlite_conn, variation_id)
    existing = annotations.get(step)

    with st.expander("Annotate this position", expanded=bool(existing)):
        glyphs = ["", "!", "!!", "?", "??", "!?", "?!"]
        glyph_key   = f"ann_glyph__{variation_id}__{step}"
        comment_key = f"ann_comment__{variation_id}__{step}"
        if glyph_key not in st.session_state:
            st.session_state[glyph_key]   = existing.glyph   if existing and existing.glyph   else ""
        if comment_key not in st.session_state:
            st.session_state[comment_key] = existing.comment if existing and existing.comment else ""

        selected_glyph = st.radio("Move quality", glyphs, horizontal=True, key=glyph_key,
                                   format_func=lambda g: g or "(none)")
        comment = st.text_area("Comment", key=comment_key, height=80,
                                placeholder="Your note on this position or move…")

        save_col, ai_col = st.columns(2)
        if save_col.button("Save annotation", key=f"ann_save__{variation_id}__{step}"):
            data.upsert_annotation(sqlite_conn, variation_id, step,
                                   glyph=selected_glyph or None,
                                   comment=comment or None)
            st.toast("Annotation saved.", icon="✅")

        ai_available = claude_narrative.api_key_available()
        ai_label = ("Regenerate Claude comment"
                    if existing and existing.ai_comment else "Ask Claude to comment")
        if not ai_available:
            ai_col.caption("Add API key in Settings to enable AI annotation.")
        elif ai_col.button(ai_label, key=f"ann_ai__{variation_id}__{step}"):
            live_result = st.session_state.get(f"live_result__{current_fen}")
            with st.spinner("Asking Claude…"):
                try:
                    ai_text = claude_narrative.annotate_position(
                        fen=current_fen,
                        eval_cp=live_result.eval_cp if live_result else None,
                        engine_best_san=live_result.best_move_san if live_result else None,
                        user_comment=comment or None,
                    )
                    data.upsert_annotation(sqlite_conn, variation_id, step,
                                           ai_comment=ai_text,
                                           ai_model=claude_narrative.MODEL)
                    st.rerun()
                except claude_narrative.MissingApiKeyError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Claude API call failed: {e}")

        if existing and existing.ai_comment:
            st.markdown(f"*Claude:* {existing.ai_comment}")
            if existing.generated_at:
                st.caption(f"Generated {existing.generated_at}")


def _render_saved_variations(sqlite_conn, gid: str) -> None:
    """List saved variations for the current game with Load/Delete actions."""
    variations = data.list_variations(sqlite_conn, gid)
    if not variations:
        return
    with st.container(border=True):
        st.subheader("Saved variations")
        for var in variations:
            c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
            branch_move_no = (var.branch_ply + 1) // 2
            title = var.title or f"From move {branch_move_no}"
            n = len(var.moves)
            c1.write(f"**{title}** — {n} move{'s' if n != 1 else ''}, branching at move {branch_move_no}")
            if c2.button("Load", key=f"var_load__{var.id}"):
                st.session_state[f"var_mode__{gid}"]       = True
                st.session_state[f"var_branch_ply__{gid}"] = var.branch_ply
                st.session_state[f"var_branch_fen__{gid}"] = var.branch_fen
                st.session_state[f"var_moves__{gid}"]      = var.moves
                st.session_state[f"var_step__{gid}"]       = len(var.moves)
                st.session_state[f"var_id__{gid}"]         = var.id
                st.session_state[f"var_load_ply__{gid}"]   = var.branch_ply
                st.rerun()
            annotations = data.get_variation_annotations(sqlite_conn, var.id)
            pgn_bytes = chess_display.variation_to_pgn(
                var.branch_fen, var.moves, annotations, title=var.title,
            ).encode()
            safe_title = (var.title or f"var_{var.id[:8]}").replace(" ", "_")
            c3.download_button("PGN ↓", data=pgn_bytes,
                               file_name=f"{safe_title}.pgn", mime="application/x-chess-pgn",
                               key=f"var_pgn__{var.id}")
            if c4.button("Delete", key=f"var_delete__{var.id}"):
                data.delete_variation(sqlite_conn, var.id)
                if st.session_state.get(f"var_id__{gid}") == var.id:
                    for k in [f"var_mode__{gid}", f"var_branch_ply__{gid}",
                              f"var_branch_fen__{gid}", f"var_moves__{gid}",
                              f"var_step__{gid}", f"var_id__{gid}",
                              f"var_last_fen__{gid}"]:
                        st.session_state.pop(k, None)
                st.rerun()


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
        # Must apply the pending load-variation ply BEFORE the slider renders;
        # setting a widget-bound key after render raises a Streamlit error.
        _load_ply_key = f"var_load_ply__{selected_game_id}"
        if _load_ply_key in st.session_state:
            st.session_state[ply_key] = st.session_state.pop(_load_ply_key)

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
        game_fen_after = narrative.position_after_ply(moves, ply)
        orientation = "black" if header.player_color == "black" else "white"
        in_variation = st.session_state.get(f"var_mode__{selected_game_id}", False)

        if in_variation:
            branch_fen  = st.session_state[f"var_branch_fen__{selected_game_id}"]
            var_moves   = st.session_state.get(f"var_moves__{selected_game_id}", [])
            var_step    = st.session_state.get(f"var_step__{selected_game_id}", 0)
            current_fen = data.compute_variation_fen(branch_fen, var_moves, var_step)

            branch_ply_val = st.session_state.get(f"var_branch_ply__{selected_game_id}", ply)
            hdr_col, exit_col = st.columns([5, 1])
            hdr_col.markdown(f"**Variation from move {(branch_ply_val + 1) // 2}** — "
                             f"{var_step} of {len(var_moves)} moves")
            if exit_col.button("Exit", key=f"var_exit__{selected_game_id}"):
                for k in [f"var_mode__{selected_game_id}", f"var_branch_ply__{selected_game_id}",
                          f"var_branch_fen__{selected_game_id}", f"var_moves__{selected_game_id}",
                          f"var_step__{selected_game_id}", f"var_last_fen__{selected_game_id}"]:
                    st.session_state.pop(k, None)
                st.rerun()

            # Look up engine result BEFORE rendering board so arrows can be passed in.
            live_var_key = f"live_result__{current_fen}"
            live_var     = st.session_state.get(live_var_key)
            var_engine_arrows = []
            if live_var and live_var.best_move_san:
                try:
                    _var_board = chess.Board(current_fen)
                    _em = _var_board.parse_san(live_var.best_move_san)
                    var_engine_arrows = [{"from": chess.square_name(_em.from_square),
                                          "to":   chess.square_name(_em.to_square),
                                          "color": f"{theme.POSITIVE}90"}]
                except Exception:
                    pass

            board_result = chessboard_component.render(
                fen=current_fen, orientation=orientation, interactive=True,
                arrows=var_engine_arrows,
                key=f"var_board__{selected_game_id}__{var_step}",
            )
            if board_result and board_result.get("fen") != current_fen:
                last_processed = st.session_state.get(f"var_last_fen__{selected_game_id}")
                if board_result["fen"] != last_processed:
                    uci = board_result["uci"]
                    # Validate UCI against the actual current position before storing.
                    # A stale component result (from Bug 1) could carry a UCI that is
                    # illegal on current_fen and would crash compute_variation_fen.
                    try:
                        _chk = chess.Board(current_fen)
                        _chk.push_uci(uci)
                    except Exception:
                        uci = None  # silently discard stale / invalid move
                    if uci:
                        new_moves = var_moves[:var_step] + [uci]
                        new_step  = var_step + 1
                        st.session_state[f"var_moves__{selected_game_id}"]    = new_moves
                        st.session_state[f"var_step__{selected_game_id}"]     = new_step
                        st.session_state[f"var_last_fen__{selected_game_id}"] = board_result["fen"]
                        var_id = st.session_state.get(f"var_id__{selected_game_id}")
                        if var_id is None:
                            var_id = data.save_variation(
                                sqlite_conn, selected_game_id, branch_ply_val, branch_fen, new_moves)
                            st.session_state[f"var_id__{selected_game_id}"] = var_id
                        else:
                            data.update_variation_moves(sqlite_conn, var_id, new_moves)
                        st.rerun()

            # Eval bar — shown only when a result is already available so
            # the bar doesn't appear empty before the user clicks Analyse.
            if live_var:
                st.markdown(
                    chess_display.eval_bar_html(live_var.eval_cp, live_var.eval_mate, current_fen),
                    unsafe_allow_html=True,
                )

            # SAN sequence display + prev/next navigation
            pv_col, nav_col = st.columns([6, 2])
            with pv_col:
                try:
                    vboard = chess.Board(branch_fen)
                    san_parts = []
                    for i, uci in enumerate(var_moves[:var_step]):
                        m = chess.Move.from_uci(uci)
                        san = vboard.san(m)
                        if vboard.turn == chess.WHITE:
                            san_parts.append(f"{vboard.fullmove_number}. {san}")
                        elif i == 0:
                            san_parts.append(f"{vboard.fullmove_number}… {san}")
                        else:
                            san_parts.append(san)
                        vboard.push(m)
                    st.caption("Line: " + " ".join(san_parts) if san_parts else "Branch point")
                except Exception:
                    pass
            with nav_col:
                nc1, nc2 = st.columns(2)
                if nc1.button("< Prev", key=f"var_prev__{selected_game_id}",
                              disabled=(var_step == 0)):
                    st.session_state[f"var_step__{selected_game_id}"] = var_step - 1
                    st.rerun()
                if nc2.button("Next >", key=f"var_next__{selected_game_id}",
                              disabled=(var_step >= len(var_moves))):
                    st.session_state[f"var_step__{selected_game_id}"] = var_step + 1
                    st.rerun()

            # Engine eval display / analyse button
            if live_var:
                eval_label = chess_display.eval_str(live_var.eval_cp, live_var.eval_mate)
                pv         = chess_display.pv_str(current_fen, live_var.pv_json)
                depth_str  = f" (depth {live_var.depth})" if live_var.depth else ""
                st.caption("Engine: " + eval_label + (f" — {pv}" if pv else "") + depth_str)
            else:
                engine_svc = live_engine.get_engine_service()
                if engine_svc and not live_engine.batch_running():
                    if st.button("Analyse position",
                                 key=f"var_analyse__{selected_game_id}__{var_step}"):
                        with st.spinner("Analysing..."):
                            result = engine_svc.analyse(current_fen)
                        if result:
                            st.session_state[live_var_key] = result
                            data.store_position_analysis(sqlite_conn, current_fen, result)
                        st.rerun()

            var_id = st.session_state.get(f"var_id__{selected_game_id}")
            if var_id:
                _render_annotation_panel(sqlite_conn, var_id, var_step, current_fen)

            if st.button("Discard variation", key=f"var_discard__{selected_game_id}",
                         type="secondary"):
                vid = st.session_state.get(f"var_id__{selected_game_id}")
                if vid:
                    data.delete_variation(sqlite_conn, vid)
                for k in [f"var_mode__{selected_game_id}", f"var_branch_ply__{selected_game_id}",
                          f"var_branch_fen__{selected_game_id}", f"var_moves__{selected_game_id}",
                          f"var_step__{selected_game_id}", f"var_id__{selected_game_id}",
                          f"var_last_fen__{selected_game_id}"]:
                    st.session_state.pop(k, None)
                st.rerun()

        else:
            live_detail_key = f"live_detail__{selected_game_id}__{ply}"
            live_result     = st.session_state.get(live_detail_key)

            engine_arrows = []
            if live_result and live_result.best_move_san:
                try:
                    board_after_obj = chess.Board(game_fen_after)
                    em = board_after_obj.parse_san(live_result.best_move_san)
                    engine_arrows = [{"from": chess.square_name(em.from_square),
                                      "to":   chess.square_name(em.to_square),
                                      "color": f"{theme.POSITIVE}90"}]
                except Exception:
                    pass

            board_result = chessboard_component.render(
                fen=game_fen_after,
                orientation=orientation,
                arrows=engine_arrows,
                interactive=True,
                lastmove_from=chess.square_name(move.from_square),
                lastmove_to=chess.square_name(move.to_square),
                key=f"game_board__{selected_game_id}",
            )
            if board_result and board_result.get("fen") != game_fen_after:
                uci = board_result["uci"]
                # Validate before entering variation mode -- a stale component
                # result could carry a UCI legal on a previous ply but illegal here.
                try:
                    _chk = chess.Board(game_fen_after)
                    _chk.push_uci(uci)
                except Exception:
                    uci = None
                if uci:
                    st.session_state[f"var_mode__{selected_game_id}"]       = True
                    st.session_state[f"var_branch_ply__{selected_game_id}"] = ply
                    st.session_state[f"var_branch_fen__{selected_game_id}"] = game_fen_after
                    st.session_state[f"var_moves__{selected_game_id}"]      = [uci]
                    st.session_state[f"var_step__{selected_game_id}"]       = 1
                    st.session_state[f"var_last_fen__{selected_game_id}"]   = board_result["fen"]
                    var_id = data.save_variation(sqlite_conn, selected_game_id, ply,
                                                 game_fen_after, [uci])
                    st.session_state[f"var_id__{selected_game_id}"] = var_id
                    st.rerun()

            move_no = (ply + 1) // 2
            who   = "White" if ply % 2 == 1 else "Black"
            mover = "You" if row.is_player_move else header.opponent_name
            detail = f" — {row.classification}, cpl={int(row.cpl)}" if pd.notna(row.cpl) else ""
            st.caption(f"Move {move_no} ({who}, {mover}): {row.san}{detail}")

            if live_result:
                eval_label = chess_display.eval_str(live_result.eval_cp, live_result.eval_mate)
                pv         = chess_display.pv_str(game_fen_after, live_result.pv_json)
                depth_str  = f" (depth {live_result.depth})" if live_result.depth else ""
                st.caption("Engine: " + eval_label + (f" — {pv}" if pv else "") + depth_str)
            elif game_fen_after:
                engine_svc = live_engine.get_engine_service()
                if engine_svc is not None:
                    if live_engine.batch_running():
                        st.caption("Batch analysis running — live engine paused.")
                    elif st.button("Analyse position",
                                   key=f"analyse_btn__{selected_game_id}__{ply}"):
                        with st.spinner("Analysing..."):
                            result = engine_svc.analyse(game_fen_after)
                        if result:
                            st.session_state[live_detail_key] = result
                            data.store_position_analysis(sqlite_conn, game_fen_after, result)
                        st.rerun()

    _render_saved_variations(sqlite_conn, selected_game_id)

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
