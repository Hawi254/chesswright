"""SRS card management and SM-2 scheduling for in-app drill mode.

Cards are chess positions from the player's game history. Ratings follow
the Anki convention: 0=Again, 1=Hard, 2=Good, 3=Easy. The scheduling
algorithm is a simplified SM-2: ease_factor and interval_days are updated
per card after every review and stored in srs_cards.

The efficacy section at the bottom (BRIEF §6p) is the first reader
srs_reviews has ever had -- until then it was write-only (one INSERT in
apply_rating, one DELETE in delete_card). Two kinds of read:
- drill-side progress (recall rate over time, learning curve): tiny
  tables, recomputed fresh every render because a drill session in the
  SAME app session changes them -- never put these behind st.cache_data.
- real-game transfer: joins the drill timeline against subsequent
  real-game motif misses. The game-side series are full-table aggregates
  (~1.4s total on the real DB) and only change when new analysis lands,
  so THOSE are the cacheable half; compute_motif_transfer is pure pandas
  on top so the split stays testable.
"""
import datetime
from typing import NamedTuple

import pandas as pd

# A motif's before/after comparison is only shown once this many analyzed
# player moves exist AFTER drilling started -- a rate over a few dozen
# moves is noise dressed up as progress.
TRANSFER_MIN_MOVES_AFTER = 200


class SrsCard(NamedTuple):
    id: int
    fen: str
    source: str
    best_move_san: str
    context: str
    ease_factor: float
    interval_days: int
    repetitions: int
    next_due: str
    added_at: str
    last_reviewed_at: str | None
    actual_move_san: str | None = None


def get_due_cards(sqlite_conn, limit: int = 50) -> list[SrsCard]:
    """Cards due today or earlier, soonest-overdue first."""
    today = datetime.date.today().isoformat()
    rows = sqlite_conn.execute("""
        SELECT id, fen, source, best_move_san, context, ease_factor,
               interval_days, repetitions, next_due, added_at, last_reviewed_at,
               actual_move_san
        FROM srs_cards
        WHERE next_due <= ?
        ORDER BY next_due ASC, id ASC
        LIMIT ?
    """, [today, limit]).fetchall()
    return [SrsCard(*row) for row in rows]


def get_card_counts(sqlite_conn) -> dict:
    """Returns {total, due, new} counts for the queue summary."""
    today = datetime.date.today().isoformat()
    total = sqlite_conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0]
    due   = sqlite_conn.execute(
        "SELECT COUNT(*) FROM srs_cards WHERE next_due <= ?", [today]
    ).fetchone()[0]
    new   = sqlite_conn.execute(
        "SELECT COUNT(*) FROM srs_cards WHERE repetitions = 0"
    ).fetchone()[0]
    return {"total": total, "due": due, "new": new}


def add_cards(sqlite_conn, cards: list[dict]) -> int:
    """Bulk-insert positions into the SRS deck.

    Each dict needs: fen, source, best_move_san. Optional: context (str).
    Skips positions already in the deck (UNIQUE on fen). Returns newly
    added count.
    """
    today = datetime.date.today().isoformat()
    inserted = 0
    for card in cards:
        cur = sqlite_conn.execute("""
            INSERT OR IGNORE INTO srs_cards
                (fen, source, best_move_san, context, actual_move_san,
                 ease_factor, interval_days, repetitions, next_due, added_at)
            VALUES (?, ?, ?, ?, ?, 2.5, 0, 0, ?, ?)
        """, [card["fen"], card["source"], card["best_move_san"],
              card.get("context", ""), card.get("actual_move_san"),
              today, today])
        inserted += cur.rowcount
    sqlite_conn.commit()
    return inserted


def apply_rating(sqlite_conn, card_id: int, rating: int) -> int:
    """Apply an SM-2 rating (0-3) to a card. Returns new interval in days.

    0 Again: reset interval to 1, ease -0.20 (min 1.3)
    1 Hard:  interval * 1.2, ease -0.15
    2 Good:  standard SM-2 progression (1 → 4 → interval * ease)
    3 Easy:  accelerated (4 → interval * ease * 1.3), ease +0.15
    """
    row = sqlite_conn.execute("""
        SELECT ease_factor, interval_days, repetitions FROM srs_cards WHERE id = ?
    """, [card_id]).fetchone()
    if not row:
        return 1
    ease, interval, reps = row

    if rating == 0:
        new_interval = 1
        new_reps     = 0
        new_ease     = max(1.3, ease - 0.2)
    elif rating == 1:
        new_interval = max(1, round(interval * 1.2)) if interval > 0 else 1
        new_reps     = reps + 1
        new_ease     = max(1.3, ease - 0.15)
    elif rating == 2:
        if reps == 0:
            new_interval = 1
        elif reps == 1:
            new_interval = 4
        else:
            new_interval = max(1, round(interval * ease))
        new_reps = reps + 1
        new_ease = ease
    else:
        if reps == 0:
            new_interval = 4
        else:
            new_interval = max(4, round(interval * ease * 1.3))
        new_reps = reps + 1
        new_ease = min(3.0, ease + 0.15)

    now = datetime.datetime.now().isoformat()
    due = (datetime.date.today() + datetime.timedelta(days=new_interval)).isoformat()
    sqlite_conn.execute("""
        UPDATE srs_cards
        SET ease_factor = ?, interval_days = ?, repetitions = ?,
            next_due = ?, last_reviewed_at = ?
        WHERE id = ?
    """, [new_ease, new_interval, new_reps, due, now, card_id])
    sqlite_conn.execute("""
        INSERT INTO srs_reviews (card_id, reviewed_at, rating, interval_days_after)
        VALUES (?, ?, ?, ?)
    """, [card_id, now, rating, new_interval])
    sqlite_conn.commit()
    return new_interval


def delete_card(sqlite_conn, card_id: int) -> None:
    sqlite_conn.execute("DELETE FROM srs_reviews WHERE card_id = ?", [card_id])
    sqlite_conn.execute("DELETE FROM srs_cards WHERE id = ?", [card_id])
    sqlite_conn.commit()


# ---------- efficacy: drill-side progress ----------

def get_review_history(sqlite_conn) -> pd.DataFrame:
    """Every review with its card's source and this review's per-card
    order (1 = first time the card was ever seen). Reviews of cards that
    were later deleted are gone too (delete_card removes them) -- history
    covers the deck as it exists, which is the honest denominator."""
    rows = sqlite_conn.execute("""
        SELECT r.card_id, c.source, r.rating,
               substr(r.reviewed_at, 1, 10) AS review_date,
               ROW_NUMBER() OVER (PARTITION BY r.card_id
                                  ORDER BY r.reviewed_at, r.id) AS review_index
        FROM srs_reviews r
        JOIN srs_cards c ON c.id = r.card_id
        ORDER BY r.reviewed_at
    """).fetchall()
    return pd.DataFrame(rows, columns=["card_id", "source", "rating",
                                        "review_date", "review_index"])


def weekly_recall(history: pd.DataFrame) -> pd.DataFrame:
    """Per ISO week: review volume and recall rate (Good-or-Easy share --
    rating >= 2 means the position was actually remembered; Again/Hard
    means it wasn't, which is exactly what SM-2 punishes)."""
    if history.empty:
        return pd.DataFrame(columns=["week", "n_reviews", "recall_pct"])
    df = history.copy()
    df["week"] = (pd.to_datetime(df.review_date)
                  .dt.to_period("W").dt.start_time)
    out = (df.groupby("week")
           .agg(n_reviews=("rating", "size"),
                recall_pct=("rating", lambda s: 100.0 * (s >= 2).mean()))
           .reset_index()
           .sort_values("week", ignore_index=True))
    return out


# Labels deliberately non-numeric ("1st" not "1."): plotly coerces
# numeric-LOOKING string labels onto a linear axis and silently drops any
# axis member that doesn't parse -- confirmed live, "5+" vanished from the
# rendered chart while "1."-"4." became the numbers 1-4. Same coercion
# family as the 'YYYY.MM' period bug on the points page (BRIEF §6o).
_NTH_LABELS = ["1st", "2nd", "3rd", "4th", "5th+"]


def learning_curve(history: pd.DataFrame) -> pd.DataFrame:
    """Recall rate by how many times the card had been seen: 1st sight
    through 5th+. A working SRS shows this rising -- if the 4th viewing
    recalls no better than the 1st, the drilling isn't sticking."""
    if history.empty:
        return pd.DataFrame(columns=["nth_review", "n_reviews", "recall_pct"])
    df = history.copy()
    df["nth_review"] = df.review_index.map(
        lambda i: _NTH_LABELS[i - 1] if i <= 4 else _NTH_LABELS[-1])
    out = (df.groupby("nth_review")
           .agg(n_reviews=("rating", "size"),
                recall_pct=("rating", lambda s: 100.0 * (s >= 2).mean()))
           .reindex(_NTH_LABELS)
           .dropna(how="all")
           .reset_index(names="nth_review"))
    out["n_reviews"] = out.n_reviews.astype(int)
    return out


def recall_by_source(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["source", "n_reviews", "recall_pct"])
    return (history.groupby("source")
            .agg(n_reviews=("rating", "size"),
                 recall_pct=("rating", lambda s: 100.0 * (s >= 2).mean()))
            .reset_index()
            .sort_values("n_reviews", ascending=False, ignore_index=True))


# ---------- efficacy: real-game transfer ----------

def get_drilled_motifs(sqlite_conn) -> pd.DataFrame:
    """Motifs the player has actually drilled: cards whose position maps
    back to a motif-tagged player move (Missed Tactics cards store
    moves.fen_before verbatim as their fen, so the join is exact -- no
    parsing of the human-readable context string). One row per motif with
    review volume and the date drilling started."""
    rows = sqlite_conn.execute("""
        WITH card_motif AS (
            SELECT c.id AS card_id,
                   (SELECT m.motif FROM moves m
                    WHERE m.fen_before = c.fen
                      AND m.motif IS NOT NULL
                      AND m.is_player_move = 1
                    LIMIT 1) AS motif
            FROM srs_cards c
        )
        SELECT cm.motif,
               COUNT(DISTINCT cm.card_id)        AS n_cards,
               COUNT(r.id)                        AS n_reviews,
               MIN(substr(r.reviewed_at, 1, 10))  AS first_review
        FROM card_motif cm
        JOIN srs_reviews r ON r.card_id = cm.card_id
        WHERE cm.motif IS NOT NULL
        GROUP BY cm.motif
    """).fetchall()
    return pd.DataFrame(rows, columns=["motif", "n_cards", "n_reviews",
                                        "first_review"])


def get_analyzed_move_series(duck_conn) -> pd.DataFrame:
    """Analyzed player moves per calendar day -- the denominator for any
    per-1000-moves rate. Dates normalized from the PGN's 'YYYY.MM.DD' to
    ISO so they compare correctly against reviewed_at dates."""
    return duck_conn.execute("""
        SELECT REPLACE(g.utc_date, '.', '-') AS d, COUNT(*) AS n_moves
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move = 1 AND m.cpl IS NOT NULL
          AND g.utc_date IS NOT NULL
        GROUP BY d ORDER BY d
    """).fetchdf()


def get_motif_miss_series(duck_conn) -> pd.DataFrame:
    """Motif-tagged player misses per motif per calendar day."""
    return duck_conn.execute("""
        SELECT m.motif, REPLACE(g.utc_date, '.', '-') AS d, COUNT(*) AS n_misses
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.motif IS NOT NULL AND m.is_player_move = 1
          AND g.utc_date IS NOT NULL
        GROUP BY m.motif, d
    """).fetchdf()


def compute_motif_transfer(drilled: pd.DataFrame,
                           move_series: pd.DataFrame,
                           miss_series: pd.DataFrame,
                           min_moves_after: int = TRANSFER_MIN_MOVES_AFTER,
                           ) -> pd.DataFrame:
    """Per drilled motif: real-game misses per 1,000 analyzed player moves
    before vs. after drilling started (first review date, inclusive on the
    after side -- the day you started drilling counts as drilled).

    measurable is False until min_moves_after analyzed moves exist after
    the cutoff; rows still appear so the UI can say "keep playing" rather
    than silently hiding the motif. Pure pandas, no I/O."""
    cols = ["motif", "n_cards", "n_reviews", "first_review",
            "misses_before", "moves_before", "rate_before",
            "misses_after", "moves_after", "rate_after", "measurable"]
    if drilled.empty or move_series.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for row in drilled.itertuples(index=False):
        cutoff = row.first_review
        before = move_series[move_series.d < cutoff]
        after = move_series[move_series.d >= cutoff]
        moves_before = int(before.n_moves.sum())
        moves_after = int(after.n_moves.sum())
        mm = miss_series[miss_series.motif == row.motif] if not miss_series.empty \
            else miss_series
        misses_before = int(mm[mm.d < cutoff].n_misses.sum()) if len(mm) else 0
        misses_after = int(mm[mm.d >= cutoff].n_misses.sum()) if len(mm) else 0
        out.append({
            "motif": row.motif, "n_cards": row.n_cards,
            "n_reviews": row.n_reviews, "first_review": cutoff,
            "misses_before": misses_before, "moves_before": moves_before,
            "rate_before": (1000.0 * misses_before / moves_before
                            if moves_before else None),
            "misses_after": misses_after, "moves_after": moves_after,
            "rate_after": (1000.0 * misses_after / moves_after
                           if moves_after else None),
            "measurable": (moves_before > 0
                           and moves_after >= min_moves_after),
        })
    return pd.DataFrame(out, columns=cols)
