# Chesswright Test Suite

## Quick start

```bash
# All tests except performance benchmarks (~18s)
.venv/bin/python -m pytest tests/ --ignore=tests/performance -q

# Unit tests only — pure functions, no DB (~1s)
.venv/bin/python -m pytest tests/unit/ -q

# Integration tests — SQLite fixtures, pipeline, joblock (~15s)
.venv/bin/python -m pytest tests/integration/ -q

# UI tests — Streamlit AppTest (requires configured chess.db)
.venv/bin/python -m pytest tests/ui/ -q

# Performance benchmarks — pytest-benchmark on 1000-game synthetic DB
.venv/bin/python -m pytest tests/performance/ -m perf -q

# Full suite including benchmarks
.venv/bin/python -m pytest tests/ -q
```

## Test layers

| Layer | Location | What it covers |
|-------|----------|----------------|
| **unit** | `tests/unit/` | Pure functions: chess_utils, motif classifier, eval formatting, config mutations, ingest parsers, annotate math, security S1/S2/S4/S5 |
| **integration** | `tests/integration/` | DB migration (all 22, idempotency, schema), ingest→annotate pipeline, joblock acquire/release/TOCTOU, data layer queries, db_import validation |
| **ui** | `tests/ui/` | AppTest page renders (Overview, Openings, Matchups, Endings, Tactical, Insights), API key button state, narrative determinism |
| **performance** | `tests/performance/` | pytest-benchmark: query latency on 1000-game DB, Insights combined query vs old 4-scan, migration speed, annotate 100-game batch |

## Markers

- `unit` — no filesystem or network
- `integration` — SQLite temp files
- `ui` — Streamlit AppTest (reads real chess.db)
- `perf` — benchmark tests, excluded from default run

## Known xfails

None — all tests pass cleanly against a real DB. The `patterns_view`
`StreamlitDuplicateElementId` bug previously noted in BRIEF.md §6b
only manifested against an empty DB; it does not reproduce with real data.

## Benchmark results (developer machine baseline)

All queries on 1000-game / 30,000-move synthetic DB:

| Test | Mean | Limit |
|------|------|-------|
| Migration (all 22) | ~10ms | 500ms |
| `get_most_repeated_positions` | ~13ms | 500ms |
| `get_motif_breakdown` | ~17ms | 200ms |
| `get_progress_by_month` | ~20ms | 500ms |
| Insights combined query | ~28ms | 2,000ms |
| `get_openings_table` | ~26ms | 500ms |
| Annotate 100 games (mock evals) | ~5ms | 10,000ms |

All passing with 10–100× headroom.
