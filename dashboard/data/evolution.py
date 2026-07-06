"""Repertoire Evolution page queries -- the core (free-tier) half of the
repertoire-evolution feature (the Pro half is the Opening Tree's
time-sliced diff, BRIEF 6s).

Answers the time dimension the all-time Openings page can't: which
opening families entered and left the repertoire, when, and how each
one's results moved. Everything here reads the games table only (never
the 2.3M-row moves table), except the per-family ACPL trend, which is
one targeted duck scan per (family, color) selection.

Split of labor, per the audit rule (never key a cache on args the
expensive part ignores): get_family_period_counts is ONE unkeyed scan
returning per-(quarter, color, time-control, family) counts; every
control on the page (color, time-control filter, family/ECO grouping,
chart top-N) is pure pandas on top of that frame.
"""
import pandas as pd

# Quarterly buckets: with this user base's volume (hundreds to thousands
# of games/year) quarters are the finest grain where shares aren't noise.
QUARTERS_WINDOW = 4        # "early"/"late" comparison windows: ~1 year each
MAJOR_SHARE_PCT = 5.0      # >= this share of a window: family is a real repertoire member
MINOR_SHARE_PCT = 2.0      # < this share: family is absent-in-practice
TREND_RATIO = 1.5          # late/early share ratio for rising (inverse for fading)
MIN_FAMILY_GAMES = 20      # ledger floor: fewer total games than this is anecdote

# Standard ECO section names -- the honest answer to lichess's catch-all
# family naming ("Zukertort Opening" / "Queen's Pawn Game" are move-order
# buckets, not repertoire choices). Grouping by section trades precision
# for stability.
ECO_SECTION_NAMES = {
    "A": "A — Flank openings",
    "B": "B — Semi-open games",
    "C": "C — Open games & French",
    "D": "D — Closed & semi-closed",
    "E": "E — Indian defences",
}

STATUS_ORDER = ["adopted", "dropped", "rising", "fading", "stable"]


def get_family_period_counts(duck_conn) -> pd.DataFrame:
    """One grouped scan over games: per (year, quarter, color, time
    control, opening family) game/win/draw counts, plus the ECO section
    letter for the coarser grouping toggle. ~30ms on the real 32k-game
    table -- cheap enough that a single unkeyed @st.cache_data wrapper
    serves every control combination on the page."""
    return duck_conn.execute("""
        SELECT
            year,
            ((month - 1) // 3) + 1                                   AS quarter,
            player_color,
            time_control_category,
            opening_family,
            SUBSTR(eco, 1, 1)                                        AS eco_section,
            COUNT(*)                                                 AS n_games,
            SUM(CASE WHEN outcome_for_player = 'win'  THEN 1 ELSE 0 END) AS n_wins,
            SUM(CASE WHEN outcome_for_player = 'draw' THEN 1 ELSE 0 END) AS n_draws
        FROM db.games
        WHERE opening_family IS NOT NULL
          AND outcome_for_player IS NOT NULL
          AND year IS NOT NULL AND month IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6
        ORDER BY year, quarter
    """).fetchdf()


def filter_counts(counts: pd.DataFrame, color: str, time_control: str | None = None,
                  grouping: str = "family") -> pd.DataFrame:
    """Slice the bulk counts frame down to one color (+ optional time
    control) and collapse to the chosen grouping. Returns long-form:
    year, quarter, period (sortable int), label ('2019 Q1' -- string
    deliberately NOT numeric-parseable, see the twice-confirmed plotly
    coercion rule), family, n_games, n_wins, n_draws."""
    df = counts[counts["player_color"] == color]
    if time_control:
        df = df[df["time_control_category"] == time_control]
    if df.empty:
        return pd.DataFrame(columns=["year", "quarter", "period", "label",
                                     "family", "n_games", "n_wins", "n_draws"])
    if grouping == "eco":
        df = df.assign(family=df["eco_section"].map(
            lambda s: ECO_SECTION_NAMES.get(s, f"{s} — other")))
    else:
        df = df.assign(family=df["opening_family"])
    out = (df.groupby(["year", "quarter", "family"], as_index=False)
             [["n_games", "n_wins", "n_draws"]].sum())
    out["period"] = out["year"].astype(int) * 4 + (out["quarter"].astype(int) - 1)
    out["label"] = out["year"].astype(int).astype(str) + " Q" + out["quarter"].astype(int).astype(str)
    return out


def _period_label(period: int) -> str:
    return f"{period // 4} Q{period % 4 + 1}"


def period_shares(filtered: pd.DataFrame, top_n: int = 4) -> tuple[pd.DataFrame, list[str]]:
    """Chart-shaped share-of-games frame: every quarter from first to
    last (gaps zero-filled, so inactive quarters render as honest empty
    slots instead of being silently collapsed by a category axis), the
    top_n families by total games as themselves, the rest folded into
    'Other'. Returns (long df of label/family/n_games/share, top list)
    so the view can assign identity colors in fixed rank order."""
    if filtered.empty:
        return pd.DataFrame(columns=["label", "family", "n_games", "share"]), []
    top = list(filtered.groupby("family")["n_games"].sum()
                       .sort_values(ascending=False).head(top_n).index)
    df = filtered.assign(
        family=filtered["family"].where(filtered["family"].isin(top), "Other"))
    df = df.groupby(["period", "family"], as_index=False)["n_games"].sum()

    all_periods = range(int(df["period"].min()), int(df["period"].max()) + 1)
    families = top + (["Other"] if (df["family"] == "Other").any() else [])
    grid = pd.MultiIndex.from_product([all_periods, families],
                                      names=["period", "family"]).to_frame(index=False)
    df = grid.merge(df, on=["period", "family"], how="left").fillna({"n_games": 0})
    totals = df.groupby("period")["n_games"].transform("sum")
    df["share"] = (100.0 * df["n_games"] / totals.where(totals > 0)).fillna(0.0)
    df["label"] = df["period"].map(_period_label)
    return df, top


def classify_evolution(filtered: pd.DataFrame) -> pd.DataFrame:
    """The adoption/abandonment ledger -- pure pandas, unit-tested.

    Compares each family's share of the player's games in the EARLY
    window (first QUARTERS_WINDOW quarters they actually played, shrunk
    to half the history when it's short) against the LATE window (last
    QUARTERS_WINDOW), and classifies:

      adopted -- absent early (< MINOR), real now (>= MAJOR)
      dropped -- real early (>= MAJOR), absent now (< MINOR)
      rising  -- present both windows, late >= TREND_RATIO x early
      fading  -- present both windows, late <= early / TREND_RATIO
      stable  -- everything else that clears the floors

    Families with fewer than MIN_FAMILY_GAMES total games, or that never
    reach MINOR_SHARE_PCT in either window, are excluded as anecdote.
    adopted_label/dropped_label date the change: first/last quarter where
    the family's per-quarter share reached MAJOR_SHARE_PCT (falling back
    to first/last appearance). win_early/win_late are the family's win
    percentages inside the two windows (NaN when it wasn't played there),
    which is what lets the ledger answer "did the change pay?" without a
    separate pairing heuristic.
    """
    cols = ["family", "status", "n_games_total", "share_early", "share_late",
            "win_early", "win_late", "n_early", "n_late",
            "first_label", "last_label", "adopted_label", "dropped_label"]
    if filtered.empty:
        return pd.DataFrame(columns=cols)

    periods = sorted(filtered["period"].unique())
    window = min(QUARTERS_WINDOW, max(1, len(periods) // 2))
    early = set(periods[:window])
    late = set(periods[-window:])

    per_q_totals = filtered.groupby("period")["n_games"].sum()
    early_total = per_q_totals[per_q_totals.index.isin(early)].sum()
    late_total = per_q_totals[per_q_totals.index.isin(late)].sum()
    if early_total == 0 or late_total == 0:
        return pd.DataFrame(columns=cols)

    rows = []
    for family, fam in filtered.groupby("family"):
        total = int(fam["n_games"].sum())
        e = fam[fam["period"].isin(early)]
        l = fam[fam["period"].isin(late)]
        n_early, n_late = int(e["n_games"].sum()), int(l["n_games"].sum())
        share_early = 100.0 * n_early / early_total
        share_late = 100.0 * n_late / late_total
        if total < MIN_FAMILY_GAMES:
            continue
        if max(share_early, share_late) < MINOR_SHARE_PCT:
            continue

        if share_early < MINOR_SHARE_PCT and share_late >= MAJOR_SHARE_PCT:
            status = "adopted"
        elif share_early >= MAJOR_SHARE_PCT and share_late < MINOR_SHARE_PCT:
            status = "dropped"
        elif (share_early >= MINOR_SHARE_PCT and share_late >= MAJOR_SHARE_PCT
              and share_late >= TREND_RATIO * share_early):
            status = "rising"
        elif (share_early >= MAJOR_SHARE_PCT and share_late >= MINOR_SHARE_PCT
              and share_late <= share_early / TREND_RATIO):
            status = "fading"
        else:
            status = "stable"

        # Date the change via per-quarter share against that quarter's total.
        fam_q = fam.groupby("period")["n_games"].sum()
        q_share = 100.0 * fam_q / per_q_totals[fam_q.index]
        major_qs = q_share[q_share >= MAJOR_SHARE_PCT].index
        first_seen, last_seen = int(fam_q.index.min()), int(fam_q.index.max())
        adopted_p = int(major_qs.min()) if len(major_qs) else first_seen
        dropped_p = int(major_qs.max()) if len(major_qs) else last_seen

        rows.append({
            "family": family, "status": status, "n_games_total": total,
            "share_early": share_early, "share_late": share_late,
            "win_early": 100.0 * e["n_wins"].sum() / n_early if n_early else float("nan"),
            "win_late": 100.0 * l["n_wins"].sum() / n_late if n_late else float("nan"),
            "n_early": n_early, "n_late": n_late,
            "first_label": _period_label(first_seen),
            "last_label": _period_label(last_seen),
            "adopted_label": _period_label(adopted_p),
            "dropped_label": _period_label(dropped_p),
        })

    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    out["_rank"] = out["status"].map({s: i for i, s in enumerate(STATUS_ORDER)})
    out = (out.sort_values(["_rank", "n_games_total"], ascending=[True, False])
              .drop(columns="_rank").reset_index(drop=True))
    return out


def family_win_trend(filtered: pd.DataFrame, family: str,
                     min_games_per_quarter: int = 5) -> pd.DataFrame:
    """Win% per quarter for one family, from the already-loaded counts
    frame (no DB hit). Quarters with fewer than min_games_per_quarter
    games are dropped rather than plotted as fake-precise points."""
    fam = filtered[filtered["family"] == family]
    if fam.empty:
        return pd.DataFrame(columns=["label", "n_games", "win_pct", "period"])
    out = fam.groupby("period", as_index=False)[["n_games", "n_wins"]].sum()
    out = out[out["n_games"] >= min_games_per_quarter]
    out["win_pct"] = 100.0 * out["n_wins"] / out["n_games"]
    out["label"] = out["period"].map(_period_label)
    return out.sort_values("period").reset_index(drop=True)


def get_family_acpl_by_period(duck_conn, opening_family: str, player_color: str,
                              time_control: str | None = None,
                              min_moves_per_quarter: int = 30) -> pd.DataFrame:
    """Avg centipawn loss per quarter for one (family, color) -- the only
    moves-table read on the page, so it runs per selection (one ~0.5-0.9s
    duck scan; the view caches it keyed on exactly these args, which the
    scan genuinely depends on). Only meaningful for the family grouping:
    the deep-dive selector never offers ECO sections. Analyzed player
    moves only; quarters with < min_moves_per_quarter analyzed moves are
    dropped as noise.

    Also returns n_total_games/coverage_pct per quarter (of all games in
    this family/color/time-control, not just this scan's analyzed ones) --
    same skew-honesty reasoning as overview.get_acpl_trajectory: analysis
    coverage is not spread evenly across calendar time (ingest.py bumps
    freshly-synced games to the front of the analysis queue), so a quarter
    with a handful of analyzed games out of a much larger total reads, on
    the bare ACPL line, as an equally-confident point as a heavily-analyzed
    one. Verified live (2026-07-07) on White's "English Opening" (flagged
    as "Rising" by classify_evolution): only 3 of 31 quarters ever clear
    the min_moves_per_quarter floor at all -- 2018 Q4 (1 of 22 games
    analyzed, 4.5% coverage), 2025 Q2 (24 of 30 games, 80.0%), 2026 Q2
    (6 of 39 games, 15.4%) -- every other quarter is 0% analyzed. Without
    disclosure, that 3-point
    line spanning 2018-2026 reads as an accuracy trend when it's really
    "whichever quarter the backlog quota happened to reach." The view uses
    coverage_pct to disclaim this rather than hide it, same posture as
    every other coverage gap in this package."""
    tc_clause = "AND g.time_control_category = ?" if time_control else ""
    params = [opening_family, player_color] + ([time_control] if time_control else [])
    df = duck_conn.execute(f"""
        WITH totals AS (
            SELECT g.year, ((g.month - 1) // 3) + 1 AS quarter,
                   COUNT(*) AS n_total_games
            FROM db.games g
            WHERE g.opening_family = ? AND g.player_color = ? {tc_clause}
              AND g.year IS NOT NULL AND g.month IS NOT NULL
            GROUP BY 1, 2
        )
        SELECT
            g.year,
            ((g.month - 1) // 3) + 1        AS quarter,
            COUNT(*)                        AS n_moves,
            COUNT(DISTINCT m.game_id)       AS n_games,
            AVG(m.cpl)                      AS acpl,
            t.n_total_games
        FROM db.moves m
        JOIN db.games g ON g.id = m.game_id
        JOIN totals t ON t.year = g.year AND t.quarter = ((g.month - 1) // 3) + 1
        WHERE g.opening_family = ?
          AND g.player_color   = ?
          {tc_clause}
          AND m.is_player_move = 1
          AND m.cpl IS NOT NULL
        GROUP BY 1, 2, t.n_total_games
        ORDER BY 1, 2
    """, params + params).fetchdf()
    cols = ["label", "n_moves", "n_games", "acpl", "n_total_games", "coverage_pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["coverage_pct"] = 100.0 * df["n_games"] / df["n_total_games"]
    df = df[df["n_moves"] >= min_moves_per_quarter].copy()
    df["label"] = (df["year"].astype(int).astype(str)
                   + " Q" + df["quarter"].astype(int).astype(str))
    return df[cols].reset_index(drop=True)
