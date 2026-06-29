"""
Phase 6c.4: Tactical Highlights -- reframed from the old "Tactics" tab,
which was bolted on during a gap-analysis pass and presented as three
bare technical tables. This is some of the most "every game tells a
story" material in the whole dashboard (brilliant finds, blown mates,
puzzle-like conversions); it deserves a real intro and real drill-down,
not just a rename. Every row here has a game_id that now actually goes
somewhere, via _common.navigate_on_row_click.
"""
import streamlit as st

import charts
import data
import theme
from _common import get_config, get_connections, navigate_on_row_click
from motif import MOTIF_LABELS


@st.cache_data
def cached_motif_breakdown(_duck_conn):
    return data.get_motif_breakdown(_duck_conn)


@st.cache_data
def cached_puzzle_sequences(_duck_conn, top_n):
    return data.get_puzzle_sequences(_duck_conn, top_n=top_n)


@st.cache_data
def cached_brilliant_candidates(_duck_conn, top_n):
    return data.get_brilliant_candidates(_duck_conn, top_n=top_n)


@st.cache_data
def cached_blown_mates(_duck_conn):
    return data.get_blown_mates(_duck_conn)


@st.cache_data
def cached_best_move_streaks(_duck_conn, top_n, min_unforced):
    return data.get_best_move_streaks(_duck_conn, top_n=top_n, min_unforced=min_unforced)


@st.cache_data
def cached_knight_rim_performance(_sqlite_conn):
    return data.get_knight_rim_performance(_sqlite_conn)


@st.cache_data
def cached_hallucination_blunders(_duck_conn):
    return data.get_hallucination_blunders(_duck_conn)


@st.cache_data
def cached_hallucination_context(_duck_conn, hangs):
    return data.get_hallucination_context(_duck_conn, hangs)


def render(self_page, detail_page):
    sqlite_conn, duck_conn = get_connections()
    st.title("Tactical Highlights")
    st.write("A curated reel of the moments most worth remembering: sequences where a "
             "blunder got punished cleanly, real sacrifices that worked, and forced mates "
             "that slipped away. Click any row to open that game's full story.")

    with st.container(border=True):
        st.subheader("Missed tactical motifs")
        st.caption("Which types of tactic keep catching you out? For each mistake or blunder "
                   "where the engine's best move was available, python-chess identifies the "
                   "pattern behind it: a fork, pin, skewer, discovered attack, back-rank mate, "
                   "or a plain hanging piece. Motifs are filled in the next time an analysis "
                   "batch runs -- the chart below is blank until at least one batch has finished.")
        motif_df = cached_motif_breakdown(duck_conn)
        if motif_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            motif_df = motif_df.copy()
            motif_df["motif"] = motif_df["motif"].map(
                lambda m: MOTIF_LABELS.get(m, m))
            col1, col2 = st.columns([2, 1])
            with col1:
                st.plotly_chart(
                    charts.bar_chart(motif_df, "motif", "n_missed", theme.NEGATIVE,
                                     height=260),
                    theme=None)
            with col2:
                display = motif_df[["motif", "n_missed", "n_games", "avg_cpl",
                                    "blunder_pct"]].copy()
                display["avg_cpl"] = display["avg_cpl"].apply(
                    lambda v: "--" if v is None else f"{v:.0f}")
                display["blunder_pct"] = display["blunder_pct"].apply(
                    lambda v: "--" if v is None else f"{v:.0f}%")
                st.dataframe(display, hide_index=True, column_config={
                    "motif":       "Motif",
                    "n_missed":    "Times missed",
                    "n_games":     "Games",
                    "avg_cpl":     "Avg CPL",
                    "blunder_pct": "Blunder %",
                })

    with st.container(border=True):
        st.subheader("Puzzle-candidate sequences")
        st.caption("A trigger ply is a mistake/blunder by either side; the sequence length "
                   "counts how many of the OTHER side's following moves (the one who didn't "
                   "just blunder) were played accurately in a row -- i.e. the conversion. "
                   "Works in both directions: an opponent blunder you converted, or your own "
                   "blunder the opponent converted.")
        puzzle_top_n = st.slider("Show top N sequences", 5, 50, 15, key="puzzle_top_n")
        puzzle_df = cached_puzzle_sequences(duck_conn, puzzle_top_n)
        if not puzzle_df.empty:
            puzzle_df = puzzle_df.copy()
            puzzle_df["who_converted"] = puzzle_df.is_player_move.map(
                {0: "you converted", 1: "opponent converted"})
        navigate_on_row_click(
            puzzle_df.drop(columns=["is_player_move"], errors="ignore"),
            "puzzle_sequences", detail_page, self_page, "Tactical Highlights",
            column_config={
                "game_id": "Game",
                "ply": "At ply",
                "san": "Trigger move",
                "classification": "Quality",
                "puzzle_sequence_length": "Sequence length",
                "who_converted": "Outcome",
            })

    with st.container(border=True):
        st.subheader("Brilliant-move candidates")
        st.caption("A real sacrifice, objectively best/excellent, recaptured by the opponent "
                   "on the same square -- the exact-square check was added after catching a "
                   "false-positive bug (an unrelated capture elsewhere on the board was "
                   "originally being flagged).")
        brilliant_top_n = st.slider("Show top N", 5, 50, 15, key="brilliant_top_n")
        brilliant_df = cached_brilliant_candidates(duck_conn, brilliant_top_n)
        navigate_on_row_click(brilliant_df, "brilliant_candidates", detail_page, self_page,
                              "Tactical Highlights", column_config={
                                  "game_id": "Game",
                                  "ply": "At ply",
                                  "san": "Move",
                                  "material_delta": "Material won",
                              })

    with st.container(border=True):
        st.subheader("Best-move streaks")
        st.caption("3+ consecutive turns matching the engine's literal top move. A streak only "
                   "counts if its first move was itself a real choice -- 'unforced', meaning the "
                   "engine's best and second-best moves were close in value (under 5 centipawns "
                   "apart, the same rank1-vs-rank2 gap the sharpness metric uses, read inverted: "
                   "small gap here means several moves were genuinely good, so finding the best "
                   "one meant something), not just the only sensible move on the board. Later "
                   "moves in the streak can be forced or unforced -- raise the slider below to "
                   "surface streaks where more of the moves were real choices, not just the first.")
        _depth = get_config()["engine"]["depth"]
        st.caption(f"⚠️ This is a sharpness-adjacent signal. At the configured engine depth ({_depth}), "
                   "close-position judgment is less reliable than clear blunder detection -- "
                   "expect this to read noisier than the blunder-rate panels.")
        streak_top_n = st.slider("Show top N streaks", 5, 50, 15, key="streak_top_n")
        streak_min_unforced = st.slider("Minimum unforced moves in the streak", 1, 10, 1,
                                         key="streak_min_unforced")
        streak_df = cached_best_move_streaks(duck_conn, streak_top_n, streak_min_unforced)
        navigate_on_row_click(
            streak_df.drop(columns=["is_player_move"], errors="ignore"),
            "best_move_streaks", detail_page, self_page, "Tactical Highlights",
            column_config={
                "game_id": "Game",
                "ply": "At ply",
                "san": "First move",
                "best_move_streak_length": "Streak length",
                "best_move_streak_unforced_count": "Unforced moves",
            })

    with st.container(border=True):
        st.subheader("Blown forced mates")
        st.caption("A forced mate was available but you played something else. Most still won "
                   "eventually (just a less efficient mate) -- the rows with result='loss' are "
                   "the truly dramatic ones: mate was on the board and the game was lost anyway.")
        blown_df = cached_blown_mates(duck_conn)
        st.metric("Truly blown (mate available, game still lost)",
                  int((blown_df.outcome_for_player == "loss").sum()))
        navigate_on_row_click(blown_df, "blown_mates", detail_page, self_page,
                              "Tactical Highlights", column_config={
                                  "game_id": "Game",
                                  "ply": "At ply",
                                  "san": "Played",
                                  "best_move_san": "Best move",
                                  "eval_mate": "Mate in",
                                  "outcome_for_player": "Result",
                              })

    with st.container(border=True):
        st.subheader("\"A knight on the rim is dim\" -- tested directly")
        _, knight_phase_df = cached_knight_rim_performance(sqlite_conn)
        _rim_endgame_n = int(knight_phase_df.loc[
            (knight_phase_df.location == "rim") & (knight_phase_df.phase == "endgame"),
            "n_moves"].sum()) if not knight_phase_df.empty else 0
        _thin_note = (f" The rim-in-endgame cell covers only {_rim_endgame_n} moves -- "
                      "treat that bar as suggestive.") if _rim_endgame_n < 150 else ""
        st.caption("Rim = a knight move landing on the a/h file or the 1st/8th rank."
                   + _thin_note)
        st.plotly_chart(
            charts.grouped_bar_chart(knight_phase_df, "phase", "location", "blunder_rate",
                                     colors={"rim": theme.NEGATIVE, "interior": theme.POSITIVE}),
            theme=None)

    with st.container(border=True):
        st.subheader("Hallucination / mouse-slip blunders")
        st.caption("A stricter signal than any 'blunder' classification: the player's move is "
                   "flagged a blunder AND the opponent's very next move recaptures on the exact "
                   "same square for real material -- i.e. a piece was actually hung, not just a "
                   "positional dip.")
        hangs = cached_hallucination_blunders(duck_conn)
        n_total = len(hangs)
        n_quick = int(hangs.resigned_quickly.sum()) if n_total else 0
        played_on = hangs[~hangs.resigned_quickly] if n_total else hangs

        col1, col2, col3 = st.columns(3)
        col1.metric("Hanging-piece blunders found", n_total)
        col2.metric("Resigned within 3 moves", f"{100.0 * n_quick / n_total:.0f}%" if n_total else "--")
        n_played_on = len(played_on)
        win_or_draw_pct = (100.0 * played_on.outcome_for_player.isin(["win", "draw"]).sum() / n_played_on
                           if n_played_on else 0.0)
        col3.metric("Won/drew anyway after playing on", f"{win_or_draw_pct:.0f}%")

        ts_df, tp_df = cached_hallucination_context(duck_conn, hangs)
        if len(ts_df):
            considered = ts_df[ts_df.bucket.str.startswith("considered")].iloc[0]
            plenty = tp_df[tp_df.bucket.str.startswith("plenty")].iloc[0]
            st.caption(f"These read as genuine hallucinations, not careless mouse-slips: "
                       f"{considered.hang_pct:.0f}% happened on a \"considered\" (3-10s) move, vs. "
                       f"{considered.baseline_pct:.0f}% of all blunders -- slightly MORE deliberation, "
                       f"not less. And {plenty.hang_pct:.0f}% happened with 60-100% of the clock still "
                       f"remaining -- not concentrated under time pressure either.")

        hallucination_top_n = st.slider("Show top N examples", 5, 50, 15, key="hallucination_top_n")
        _hang_col_config = {
            "game_id": "Game",
            "blunder_ply": "At ply",
            "blunder_san": "Move played",
            "num_plies": "Game length",
            "outcome_for_player": "Result",
            "game_end_type": "Ended by",
            "plies_remaining": "Plies remaining",
        }
        st.write("**Quickest hang-and-resign examples**")
        # No hanging-piece blunders found yet means `hangs` has no
        # `resigned_quickly` column at all (get_hallucination_blunders()
        # only adds it when there's at least one row) -- common early on
        # with few analyzed games, not just a theoretical empty case.
        quick_examples = (hangs[hangs.resigned_quickly].sort_values("plies_remaining").head(
            hallucination_top_n) if n_total else hangs)
        navigate_on_row_click(
            quick_examples.drop(columns=["resigned_quickly"], errors="ignore"),
            "hallucination_quick_resign", detail_page, self_page, "Tactical Highlights",
            column_config=_hang_col_config)

        st.write("**Recoveries: hung a piece, didn't lose anyway**")
        recoveries = played_on[played_on.outcome_for_player.isin(["win", "draw"])].sort_values(
            "plies_remaining", ascending=False).head(hallucination_top_n)
        navigate_on_row_click(
            recoveries.drop(columns=["resigned_quickly"], errors="ignore"),
            "hallucination_recoveries", detail_page, self_page, "Tactical Highlights",
            column_config=_hang_col_config)
