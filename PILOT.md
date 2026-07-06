# Chesswright pilot — thank you for testing

You're one of a small group trying Chesswright before it's released more
widely. The whole point of this stage is to find out whether a real person,
on their own computer, with only the written instructions and no help from
me in the moment, can install it and get their first analysis running. So
please **don't ask me for help mid-install** — if you get stuck, that's the
single most valuable thing to write down. Struggle a little, then report it.

## What to do

1. Follow the [README](README.md) top to bottom: check the **System
   requirements** first (notably: Intel Macs aren't supported yet), install
   Stockfish, download the build for your OS, run it, and complete the
   first-run setup wizard through to your **starter analysis batch**
   finishing.
2. Poke around the dashboard afterward for as long as you feel like.

That's it. You don't need to analyze your whole history — the starter batch
the wizard suggests is enough.

## What to report

Whatever you hit, but especially these — they're what decides whether the app
is ready:

- **Did you get all the way through install → first analysis with nothing
  fully blocking you?** "Blocking" means you genuinely couldn't install,
  launch, or finish that first batch, with no fix short of editing a config
  file. Confusing wording, an ugly step, something slow-but-working — all
  still worth telling me, just not "blocking."
- **Which OS and roughly what machine** (e.g. "Windows 11 laptop, 2021").
- **Was the time estimate honest?** At the last setup step the app shows an
  estimate ("~N minutes") measured on *your* hardware, then runs. When it
  finishes it tells you the estimate vs. what it actually took, and saves both
  to a file called `first_run_timing.json` next to your database (the setup
  wizard tells you where your data lives). **Please send me those two
  numbers**, or just that file — it's a few lines of plain text with no
  personal data in it.
- **Roughly how many games** does the lichess account you tested with have?
  (A tiny account can't really exercise the onboarding, so this matters.)
- **Anything that surprised you, annoyed you, or looked wrong.**

## How to report

- A [pilot feedback issue](../../issues/new?template=pilot_feedback.yml) is
  ideal — it's a short form with exactly the fields above.
- Something clearly broken? A [bug report](../../issues/new?template=bug_report.yml).
- Or just message me directly with the same details.

Please **don't paste your Claude API key** if one ever shows up in an error or
screenshot. Everything else is fair game — the messier the feedback, the more
useful it is.
