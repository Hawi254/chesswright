# Chesswright — Distributable Chess Analysis Tool

**Working name: "Chesswright."** Not finalized — easy to rename later (one
find-replace pass, no code yet exists). Alternates considered: "Ply &
Pattern," "Moveprint." Confirm with the user before this sticks.

A separate, installable desktop app that lets **any** lichess player run
the same kind of Stockfish-powered game analysis the original
`chess-analyzer` project built for one specific person (username `L3-37`).
Local install, local Stockfish, local SQLite database, never synced or
shared anywhere. New repository, new identity — this is not a phase of
the original project.

**Read `BRIEF.md` in full before doing anything else.** It has the full
research, the decisions and their reasoning, the architecture, and the
phased rollout plan (copy/adapt → pilot group → public release). This
file only holds facts that must hold true every session.

## Relationship to the original project — hard boundary

- The original project lives at
  `/home/jasper/Desktop/chess_project/chess-analyzer/`. **Never read,
  write, run, or import anything from that directory as a live
  dependency.** It is mid a multi-week Stockfish analysis run against a
  real personal database; any coupling (shared venv, shared import path,
  accidental write) risks destabilizing it.
- The starting backend code here (`ingest.py`, `worker.py`, `annotate.py`,
  `analytics.py`, `db.py`, `config.py`, `chess_utils.py`, the
  `dashboard/` package) is a **copy**, taken once, then evolved
  independently. See `BRIEF.md` §5 for why copy-now-converge-later was
  chosen over importing a shared package from day one.
- The original project's own `CLAUDE.md`/`PROJECT_BRIEF.md` are research
  material for this project, not files this project edits.

## Stack (planned — nothing built yet)

Same backend stack as the original: Python 3, SQLite, `python-chess`,
Stockfish (UCI, external process — never linked in), PyYAML, DuckDB,
pandas, Streamlit, Plotly, `anthropic`. New, specific to this project:
`pywebview` (native window wrapper), `PyInstaller` (packaging),
`keyring` (local OS-native secret storage for the user's own Claude API
key — see `BRIEF.md` §3, this is a deliberate deviation from the
original project's "env var only" rule, and the reason is documented
there, not re-litigated here).

## Hard rules — do not violate without flagging it as a question first

- **Never bundle a Stockfish binary inside the installer.** The app
  auto-detects a system-installed Stockfish (mirrors the original
  project's `engine.path: null` convenience) and, if none is found,
  walks the user through installing it themselves via Stockfish's own
  official distribution channels. See `BRIEF.md` §1 for the full GPLv3
  reasoning — this is the one research finding most likely to be wrong
  if skimmed, read it before changing this rule.
- **Our own code's license is separate from Stockfish's GPLv3** (planned:
  MIT) — defensible only because we never distribute, modify, or
  statically link Stockfish. If that ever changes (e.g. vendoring a
  downloaded copy for onboarding convenience), this needs real legal
  review first, not an assumption carried over from this file.
- **API keys are never hardcoded, never committed, never logged.**
  Stored via `keyring` (OS credential store) with a documented,
  explicitly-flagged-as-less-secure plain-local-file fallback only when
  no OS secret service is available. Every Claude-API feature must
  degrade gracefully (not crash) when no key is configured.
- **The first-run experience must state the real time cost honestly**,
  computed from a short live calibration on the user's own machine, not
  a fixed claim — see `BRIEF.md` §2 for the onboarding design. Don't
  silently default to analyzing a user's whole account history on first
  run.
- **Don't touch the original project's directory, database, or running
  pipeline.** Full stop — see the boundary section above.
- Config-driven by lichess username (this is already true of the copied
  backend — confirmed in the original's `config.yaml` — preserve it,
  don't reintroduce a hardcoded player).

## File layout (planned)

See `BRIEF.md` §4 for the full repository layout, packaging structure,
and phased build order. Nothing has been written yet — this is a design
document, not a status report.

## Starting a new session

- New sessions share no context with each other or with claude.ai — read
  `BRIEF.md` fully rather than inferring history you don't have.
- This project has not started building yet as of 2026-06-23. The
  current state is: research done, plan drafted, **awaiting the user's
  checkpoint approval before any code is written.**
