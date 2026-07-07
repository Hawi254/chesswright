"""
Phase 6c.4: Openings & Repertoire -- the old Openings tab plus
"most-repeated positions" from the old Position Explorer tab. Both
answer the same question: what do you actually play, and how does it
work for you? (Material-structure win-rate, Position Explorer's OTHER
panel, moved to Patterns & Tendencies instead -- see that module's
docstring for why.)
"""
import chess
import chess.svg
import pandas as pd
import streamlit as st

import analytics
import charts
import chess_display
import claude_narrative
import data
import live_engine
import theme
from _common import get_connections
from cached_queries import cached_headline_stats


@st.cache_data(show_spinner="Loading your opening statistics…")
def cached_openings_table_full(_duck_conn, _sqlite_conn):
    """Deliberately NOT keyed on the min-games slider -- the expensive
    half of get_openings_table (a ~0.3s GROUP BY over all analyzed moves
    for the ACPL column) never depended on min_games, only the HAVING on
    the games-count half did, so keying on it made every slider move a
    fresh cache miss (~0.4s measured). One unfiltered fetch per session;
    callers filter `n >= min_games` in pandas. Also collapses what used
    to be two separate cache entries (section 1's slider value and
    section 4's fixed min_games=1) into one."""
    return data.get_openings_table(_duck_conn, _sqlite_conn, min_games=1)


@st.cache_data(show_spinner="Finding your most-repeated positions…")
def cached_most_repeated_positions(_sqlite_conn, top_n):
    return data.get_most_repeated_positions(_sqlite_conn, top_n=top_n)


@st.cache_data(show_spinner="Computing accuracy move by move…")
def cached_opening_ply_accuracy(_duck_conn, opening_family, player_color, min_appearances):
    return data.get_opening_ply_accuracy(
        _duck_conn, opening_family, player_color, min_appearances=min_appearances)


@st.cache_data(show_spinner="Scanning for repertoire holes…")
def cached_repertoire_holes(_sqlite_conn, min_appearances, top_n):
    return data.get_repertoire_holes(_sqlite_conn, min_appearances=min_appearances, top_n=top_n)


@st.cache_data(show_spinner=False)
def cached_position_fen(_sqlite_conn, ply, zobrist_hash):
    return data.get_position_fen(_sqlite_conn, ply, zobrist_hash)


@st.cache_data(show_spinner=False)
def cached_position_analysis(_sqlite_conn, fen_before):
    return data.get_position_analysis(_sqlite_conn, fen_before)


def _board_svg(fen: str, player_san: str | None = None, engine_san: str | None = None,
               flip: bool = False, size: int = 300) -> str:
    """Render a position SVG. Gold arrow = player's usual move; green = engine best."""
    board = chess.Board(fen)
    arrows = []
    if player_san:
        try:
            m = board.parse_san(player_san)
            arrows.append(chess.svg.Arrow(m.from_square, m.to_square,
                                          color=f"{theme.ACCENT_GOLD}90"))
        except Exception:
            pass
    if engine_san and engine_san != player_san:
        try:
            m = board.parse_san(engine_san)
            arrows.append(chess.svg.Arrow(m.from_square, m.to_square,
                                          color=f"{theme.POSITIVE}90"))
        except Exception:
            pass
    return chess.svg.board(board, size=size, flipped=flip,
                            arrows=arrows, colors=theme.BOARD_COLORS)


def render(drill_export_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.title("Openings & Repertoire")

    # Builds/refreshes repeated_positions_cache and repertoire_holes_cache
    # (migration 0030) only when their respective analyzed-move counts
    # have changed since the last build -- a no-op on every visit except
    # the first one after new games get analyzed. Each @st.fragment below
    # only reruns in isolation on its own widget interactions, so this has
    # to run here, in render()'s own top-level body, to guarantee it
    # completes before either fragment's first render -- not inside the
    # fragments themselves.
    if "openings_caches_ready" not in st.session_state:
        with st.spinner("Indexing your repertoire — happens once per new batch of analyzed games…"):
            analytics.ensure_repeated_positions_cache(sqlite_conn)
            analytics.ensure_repertoire_holes_cache(sqlite_conn)
        st.session_state["openings_caches_ready"] = True

    # Each section is its own @st.fragment -- confirmed independent
    # before splitting, unlike a first look might suggest: section 4
    # (below) used to read section 1's own min_games-filtered
    # openings_df directly, which would have silently frozen section
    # 4's opening list at whatever section 1's slider happened to be
    # set to the last time the whole page ran, the moment section 1
    # became its own fragment. Fixed by giving section 4 its own
    # independent, unfiltered query instead (see
    # _render_opening_ply_accuracy_section) -- every opening ever
    # played should be selectable there regardless of section 1's own
    # filter, which is arguably more correct than the accidental
    # coupling this replaces, not just a technical workaround.
    _render_openings_table_section(sqlite_conn, duck_conn)
    _render_most_repeated_positions_section(sqlite_conn)
    _render_repertoire_holes_section(sqlite_conn, drill_export_page)
    _render_opening_ply_accuracy_section(sqlite_conn, duck_conn)


@st.fragment
def _render_openings_table_section(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("Your openings")
        st.caption("Click a column header to sort. The slider hides openings "
                   "you've played fewer times than the minimum.")
        min_games = st.slider("Minimum games", 1, 50, 5)
        full_df = cached_openings_table_full(duck_conn, sqlite_conn)
        # Cheap pandas filter over the session-cached full table --
        # equivalent to the old per-slider-value HAVING COUNT(*) >= ?.
        openings_df = full_df[full_df.n >= min_games].reset_index(drop=True)
        # win_pct/draw_pct/loss_pct/n are always populated (ingest-time,
        # no engine needed); acpl needs analyzed games specifically in
        # that opening, and with only 185 of 32,295 games analyzed so
        # far, most openings show NaN here -- caught by checking real
        # output (55 of 78 rows), not assumed fine. A bare NaN reads as
        # broken, not "not analyzed yet" -- same fix as the Patterns &
        # Tendencies material-structure table.
        n_unanalyzed = int((openings_df.n_analyzed == 0).sum())
        if n_unanalyzed:
            st.caption(f"ACPL is blank for {n_unanalyzed} of {len(openings_df)} openings above "
                       f"-- no analyzed games have reached them yet, not a data error.")
        display_df = openings_df.copy()
        display_df["acpl"] = display_df["acpl"].apply(lambda v: "--" if pd.isna(v) else f"{v:.1f}")
        st.dataframe(display_df, width='stretch', hide_index=True, column_config={
            "opening_family": "Opening",
            "player_color": "Color",
            "n": "Games",
            "win_pct": st.column_config.NumberColumn("Win %", format="%.1f"),
            "draw_pct": st.column_config.NumberColumn("Draw %", format="%.1f"),
            "acpl": st.column_config.Column(
                "ACPL", help="Average centipawn loss of your moves in this opening -- "
                             "lower is more accurate. Blank until games in it are analyzed."),
            "n_analyzed": st.column_config.Column(
                "Analyzed games", help="How many of these games have engine analysis."),
        })

        if not openings_df.empty:
            opening_labels = [f"{r.opening_family} ({r.player_color})"
                               for r in openings_df.itertuples()]
            chosen_label = st.selectbox("Tell me about this opening", opening_labels,
                                         key="opening_commentary_select")
            chosen_row = openings_df.iloc[opening_labels.index(chosen_label)]
            subject_key = f"{chosen_row.opening_family}|{chosen_row.player_color}"

            cached = data.get_cached_narrative(sqlite_conn, "opening", subject_key)
            if cached:
                response_text, generated_at = cached
                st.caption(f"Generated {generated_at}")
                st.markdown(response_text)
            button_label = "Regenerate commentary" if cached else "Generate commentary"

            if not claude_narrative.api_key_available():
                st.info("Add your own Anthropic API key on the Settings page to enable this.")
            if st.button(button_label, key="opening_commentary_button",
                         disabled=not claude_narrative.api_key_available()):
                stats = cached_headline_stats(duck_conn, sqlite_conn)
                with st.spinner("Asking Claude..."):
                    try:
                        response_text = claude_narrative.generate_opening_commentary(
                            chosen_row, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
                        data.save_narrative(sqlite_conn, "opening", subject_key,
                                             response_text, claude_narrative.MODEL)
                        # Scoped, not a full app rerun -- nothing else on
                        # the page reads this narrative.
                        st.rerun(scope="fragment")
                    except claude_narrative.MissingApiKeyError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Claude API call failed: {e}")


@st.fragment
def _render_most_repeated_positions_section(sqlite_conn):
    with st.container(border=True):
        st.subheader("Most-repeated positions")
        st.caption("Positions you've reached more than once (matched by exact board state, "
                   "not just opening name) -- shows whether your most-repeated lines are "
                   "actually working out, win/loss-wise. Tick a row's checkbox to "
                   "view the board.")
        top_n_positions = st.slider("Show top N", 5, 50, 20, key="positions_top_n")
        positions_df = cached_most_repeated_positions(sqlite_conn, top_n_positions)
        pos_sel = st.dataframe(
            positions_df.drop(columns=["zobrist_hash"], errors="ignore")
                .assign(ply=lambda d: (d.ply + 1) // 2),
            width="stretch", on_select="rerun", selection_mode="single-row",
            key="most_repeated_sel", hide_index=True,
            column_config={
                "ply": st.column_config.NumberColumn(
                    "Move #", help="How deep into the game the position occurs "
                                   "(one move = one White and one Black turn)."),
                "n_games": "Times reached",
                "win_pct": st.column_config.NumberColumn("Win %", format="%.1f"),
                "draw_pct": st.column_config.NumberColumn("Draw %", format="%.1f"),
                "loss_pct": st.column_config.NumberColumn("Loss %", format="%.1f"),
                "common_opening": "Most common opening",
            })
        sel_rows = pos_sel.selection.rows if pos_sel and pos_sel.selection else []
        if sel_rows and not positions_df.empty:
            sel = positions_df.iloc[sel_rows[0]]
            fen = cached_position_fen(sqlite_conn, int(sel.ply), int(sel.zobrist_hash))
            if fen:
                analysis = cached_position_analysis(sqlite_conn, fen)
                analysis = live_engine.get_or_analyse_position(
                    sqlite_conn, fen, analysis, session_key=fen,
                    on_fresh_result=cached_position_analysis.clear)

                engine_san = analysis["best_move_san"] if analysis else None
                flip = st.toggle("Flip board", key="most_repeated_flip")
                col_bd, col_info = st.columns([1, 1])
                with col_bd:
                    st.markdown(_board_svg(fen, engine_san=engine_san, flip=flip),
                                unsafe_allow_html=True)
                with col_info:
                    st.markdown(
                        f"**Move {(int(sel.ply) + 1) // 2}** — reached {int(sel.n_games)} times\n\n"
                        f"Win {sel.win_pct:.0f}% · Draw {sel.draw_pct:.0f}%"
                        f" · Loss {sel.loss_pct:.0f}%\n\n"
                        f"Most common opening: {sel.common_opening or '—'}")
                    st.divider()
                    if analysis:
                        st.markdown(f"**Eval:** {chess_display.eval_str(analysis['eval_cp'], analysis['eval_mate'])}")
                        if engine_san:
                            st.markdown(f"**Best move:** {engine_san}")
                        pv = chess_display.pv_str(fen, analysis["pv_json"])
                        depth = analysis.get("depth")
                        depth_str = f" (depth {depth})" if depth else ""
                        if pv:
                            st.caption(f"Line: {pv}{depth_str}")
                        elif depth:
                            st.caption(f"depth {depth}")
                        if analysis.get("source") == "live":
                            st.caption("Live engine result (not from batch).")
                        elif analysis.get("source") == "lichess_cloud":
                            st.caption("From Lichess's cloud evaluation database.")
                    else:
                        st.caption("No analysis available for this position.")


@st.fragment
def _render_repertoire_holes_section(sqlite_conn, drill_export_page):
    with st.container(border=True):
        st.subheader("Repertoire holes")
        st.caption("A 'hole' is a position you've reached multiple times but keep playing "
                   "differently — a sign of genuine uncertainty about the right move. "
                   "Ranked by inconsistency × average CPL, so positions that are both "
                   "uncertain and costly appear first. Only analyzed games are included.")
        col_rep1, col_rep2 = st.columns(2)
        rep_min = col_rep1.slider("Min times reached", 3, 20, 5, key="rep_min_appearances")
        rep_top_n = col_rep2.slider("Show top N", 5, 50, 20, key="rep_top_n")
        holes_df = cached_repertoire_holes(sqlite_conn, rep_min, rep_top_n)
        if holes_df.empty:
            st.info(theme.thin_data_message(0, rep_min))
        else:
            display_holes = holes_df.drop(columns=["fen_before"], errors="ignore").copy()
            display_holes["avg_cpl"] = display_holes["avg_cpl"].apply(
                lambda v: "--" if v is None or pd.isna(v) else f"{v:.1f}")
            display_holes["hole_score"] = display_holes["hole_score"].apply(
                lambda v: "--" if v is None or pd.isna(v) else f"{v:.0f}")
            hole_sel = st.dataframe(
                display_holes, hide_index=True, on_select="rerun",
                selection_mode="single-row", key="rep_holes_sel",
                column_config={
                    "approx_move_number": "At move",
                    "opening":            "Opening",
                    "most_played_san":    "Usual move",
                    "n_games":            "Times reached",
                    "n_distinct_moves":   "Variations tried",
                    "avg_cpl":            st.column_config.Column(
                        "Avg CPL", help="Average centipawn loss of your moves from this "
                                        "position -- lower is more accurate."),
                    "hole_score":         st.column_config.Column(
                        "Hole score", help="Inconsistency × average CPL. A bigger number = "
                                           "a position you both keep playing differently "
                                           "and keep paying for. Use it to rank, not to "
                                           "measure."),
                })
            top_hole = holes_df.iloc[0]
            st.caption(
                f"Biggest hole: move {top_hole.approx_move_number} "
                f"({top_hole.opening or 'unknown opening'}) — reached "
                f"{top_hole.n_games}× with {top_hole.n_distinct_moves} different moves "
                f"and avg {top_hole.avg_cpl:.0f} CPL. Tick a row's checkbox to view "
                f"the board.")
            hole_rows = hole_sel.selection.rows if hole_sel and hole_sel.selection else []
            if hole_rows:
                sel = holes_df.iloc[hole_rows[0]]
                if sel.fen_before:
                    analysis = cached_position_analysis(sqlite_conn, sel.fen_before)
                    analysis = live_engine.get_or_analyse_position(
                        sqlite_conn, sel.fen_before, analysis, session_key=sel.fen_before,
                        on_fresh_result=cached_position_analysis.clear)

                    engine_san = analysis["best_move_san"] if analysis else None
                    flip = st.toggle("Flip board", key="rep_holes_flip")
                    col_bd, col_info = st.columns([1, 1])
                    with col_bd:
                        st.markdown(
                            _board_svg(sel.fen_before, player_san=sel.most_played_san,
                                       engine_san=engine_san, flip=flip),
                            unsafe_allow_html=True)
                    with col_info:
                        same_move = engine_san and engine_san == sel.most_played_san
                        st.markdown(
                            f"**Around move {int(sel.approx_move_number)}** "
                            f"({sel.opening or '—'})\n\n"
                            f"Reached {int(sel.n_games)}× with "
                            f"**{int(sel.n_distinct_moves)} different moves** tried\n\n"
                            f"Your usual move: **{sel.most_played_san}**"
                            + (" ✓ engine agrees" if same_move else " (gold arrow)") + "\n\n"
                            f"Avg CPL: {sel.avg_cpl:.0f}")
                        st.divider()
                        if analysis:
                            st.markdown(f"**Eval:** {chess_display.eval_str(analysis['eval_cp'], analysis['eval_mate'])}")
                            if engine_san and not same_move:
                                st.markdown(f"**Engine best:** {engine_san} (green arrow)")
                            pv = chess_display.pv_str(sel.fen_before, analysis["pv_json"])
                            depth = analysis.get("depth")
                            depth_str = f" (depth {depth})" if depth else ""
                            if pv:
                                st.caption(f"Line: {pv}{depth_str}")
                            elif depth:
                                st.caption(f"depth {depth}")
                            if analysis.get("source") == "live":
                                st.caption("Live engine result (not from batch).")
                            elif analysis.get("source") == "lichess_cloud":
                                st.caption("From Lichess's cloud evaluation database.")
                        else:
                            st.caption("No analysis available for this position.")

            if drill_export_page:
                st.divider()
                if st.button("→ Export these as drill positions",
                             key="holes_drill_export",
                             help="Open Drill Export with Repertoire Holes pre-selected."):
                    st.session_state["_drill_preset"] = {
                        "include_motifs": False,
                        "include_moments": False,
                        "include_holes": True,
                        "motif_filter": None,
                    }
                    st.switch_page(drill_export_page)


@st.fragment
def _render_opening_ply_accuracy_section(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("Where in an opening does your accuracy drop?")
        st.caption("Average centipawn loss by move number within a specific opening. "
                   "A spike at move 8 means your choices at that move are costing you "
                   "more than at other points in the line -- not just a general feel, "
                   "but the exact move number where preparation runs out.")
        # Deliberately independent of the "Openings" section's own
        # min_games slider above (see render()'s comment) -- every
        # opening ever played should be selectable here, not just
        # whichever ones currently pass that other section's filter.
        # Shares section 1's unfiltered cache entry.
        openings_df = cached_openings_table_full(duck_conn, sqlite_conn)
        if openings_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            drill_labels = [f"{r.opening_family} ({r.player_color})"
                            for r in openings_df.itertuples()]
            drill_label = st.selectbox("Select opening", drill_labels,
                                       key="opening_ply_select")
            drill_row = openings_df.iloc[drill_labels.index(drill_label)]
            min_app = st.slider("Min games reaching each move", 1, 10, 3,
                                key="opening_ply_min_app")
            ply_df = cached_opening_ply_accuracy(
                duck_conn, drill_row.opening_family, drill_row.player_color, min_app)
            if ply_df.empty:
                st.info(theme.thin_data_message(0, min_app))
            else:
                st.plotly_chart(
                    charts.bar_chart(ply_df, "move_number", "avg_cpl", theme.NEGATIVE,
                                     height=280, x_title="Move number",
                                     y_title="Average centipawn loss"),
                    theme=None)
                worst = ply_df.nlargest(3, "avg_cpl")
                worst_nums = ", ".join(f"move {int(r.move_number)} "
                                       f"(avg {r.avg_cpl:.0f} CPL, "
                                       f"{r.blunder_rate:.0f}% blunder)"
                                       for r in worst.itertuples())
                st.caption(f"Highest-CPL move numbers: {worst_nums}")
