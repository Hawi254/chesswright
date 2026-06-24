"""Shared config loading. CLI args (when not None) always win over config.yaml."""
import os
import re
import pathlib
import yaml

# A source checkout (the dev workflow Phases A/B were built and tested
# against) keeps config.yaml next to this file -- fine, since __file__
# resolves correctly there. A PyInstaller-frozen build is different:
# __file__-relative paths point into a read-only (or, for --onefile,
# temporary and wiped-between-runs) bundle directory, never somewhere
# safe to keep a growing personal database. desktop_app.py (the packaged
# entry point) sets this env var to redirect config resolution at a
# real per-user data directory instead -- unset in the dev workflow, so
# nothing about Phases A/B's already-tested behavior changes.
_ENV_CONFIG_PATH = os.environ.get("CHESSWRIGHT_CONFIG_PATH")
DEFAULT_CONFIG_PATH = pathlib.Path(_ENV_CONFIG_PATH) if _ENV_CONFIG_PATH \
    else pathlib.Path(__file__).parent / "config.yaml"


def load_config(path=None) -> dict:
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


def pick(cli_value, config_value):
    """CLI value wins if explicitly given (argparse default=None means 'not given')."""
    return cli_value if cli_value is not None else config_value


def set_player_name(username, path=None):
    """Persists the onboarding wizard's chosen lichess username into
    config.yaml -- a targeted text substitution of just the `player.name`
    line, not a full re-serialize via yaml.safe_dump(), which would strip
    every one of this file's explanatory comments (the whole point of
    this file's format, per its own header). Assumes the line looks like
    `  name: "..."` directly under a `player:` section, which is true of
    every config.yaml this project ships -- if a user has hand-edited it
    into some other shape, this raises rather than silently doing nothing."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    text = path.read_text()
    new_text, n = re.subn(
        r'(?m)^(\s*)name:\s*"[^"]*"(\s*#.*)?$',
        lambda m: f'{m.group(1)}name: "{username}"{m.group(2) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find a player.name line to update in {path} -- "
            "expected a line like `name: \"...\"`.")
    path.write_text(new_text)


def set_database_path(db_path, path=None):
    """Same targeted-substitution approach as set_player_name(), used
    once by desktop_app.py when it copies the bundled config.yaml
    template into the per-user data directory on first launch -- rewrites
    the relative `database.path: chess.db` default to an absolute path
    inside that same directory, so the database doesn't end up wherever
    the process happened to have its cwd.

    Scoped to the `database:` section specifically, not a bare `path:`
    match -- config.yaml has a SECOND `path:` key (`engine.path`), and a
    naive regex would silently rewrite whichever one happens to appear
    first in the file rather than the one this function is actually
    meant to change."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    text = path.read_text()
    new_text, n = re.subn(
        r'(?ms)^(database:\n(?:[ \t].*\n)*?)(\s*)path:\s*\S+(\s*#.*)?$',
        lambda m: f'{m.group(1)}{m.group(2)}path: {db_path}{m.group(3) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find a database.path line to update in {path}.")
    path.write_text(new_text)


def set_engine_path(engine_path, path=None):
    """Same targeted-substitution approach as set_database_path(), scoped
    to the `engine:` section's `path:` key specifically -- the same reason
    set_database_path() already documents (config.yaml has a SECOND `path:`
    key, and a naive regex would rewrite whichever one appears first).

    Quoted (unlike set_database_path()'s bare value): a Windows engine path
    routinely contains spaces (`C:\\Program Files\\...`), which the database
    path didn't need to handle but this one realistically does."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    text = path.read_text()
    new_text, n = re.subn(
        r'(?ms)^(engine:\n(?:[ \t].*\n)*?)(\s*)path:\s*\S+(\s*#.*)?$',
        lambda m: f'{m.group(1)}{m.group(2)}path: "{engine_path}"{m.group(3) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find an engine.path line to update in {path}.")
    path.write_text(new_text)
