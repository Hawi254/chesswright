"""Shared config loading. CLI args (when not None) always win over config.yaml."""
import os
import re
import shutil
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


def backfill_missing_keys(path=None) -> None:
    """Forward-migrates an already-created user config.yaml to pick up
    keys added to the shipped template since that user's copy was made.

    ensure_user_data() only copies the bundled template into
    USER_DATA_DIR on first launch, deliberately -- overwriting it on
    every launch would clobber a user's real settings. But that means
    every key a later release adds to config.yaml (e.g. the
    analytics.instant_move_* keys added in v0.1.2x) is invisible to an
    existing install forever: load_config() returns a dict missing that
    key, and the first view to read it hits a bare KeyError deep inside
    a cached fragment, nowhere near this file. Call this on EVERY
    launch (unlike ensure_user_data()'s one-time copy) so new keys
    backfill automatically instead of needing a human to notice and
    reinstall.

    Only backfills keys within a section the user's config already has,
    appending each missing key's own default line (with its trailing
    comment, preserved verbatim from the template) to the end of that
    section. A whole new top-level section is rare enough (none have
    been added since v0.1.0) that it's left for a human to notice via
    the changelog rather than guessed at here.
    """
    user_path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    template_path = pathlib.Path(__file__).resolve().parent / "config.yaml"
    if not user_path.exists() or user_path.resolve() == template_path.resolve():
        return

    template_cfg = load_config(template_path)
    user_cfg = load_config(user_path)
    template_text = template_path.read_text()
    text = user_path.read_text()
    changed = False

    for section, template_section in template_cfg.items():
        if not isinstance(template_section, dict):
            continue
        user_section = user_cfg.get(section)
        if not isinstance(user_section, dict):
            continue
        missing_keys = [k for k in template_section if k not in user_section]
        if not missing_keys:
            continue

        section_re = rf'(?m)^{re.escape(section)}:\n((?:[ \t]+.*\n|[ \t]*\n)*)'
        template_section_match = re.search(section_re, template_text)
        user_section_match = re.search(section_re, text)
        if not template_section_match or not user_section_match:
            continue
        template_body = template_section_match.group(1)

        new_lines = []
        for key in missing_keys:
            key_match = re.search(
                rf'(?m)^[ \t]+{re.escape(key)}:\s*\S.*\n(?:[ \t]*#.*\n)*',
                template_body)
            if key_match:
                new_lines.append(key_match.group(0))
        if not new_lines:
            continue

        insertion_point = user_section_match.end(1)
        text = text[:insertion_point] + "".join(new_lines) + text[insertion_point:]
        changed = True

    if changed:
        user_path.write_text(text)


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


def set_chesscom_username(username, path=None):
    """Same targeted-substitution approach as set_player_name(), for the
    optional player.chesscom_username field (the additive-only chess.com
    integration -- see settings_view.py's "Chess.com account" section).
    username=None (or "") writes the YAML `null` literal, clearing the
    connection rather than leaving a stale/empty string -- already-synced
    chess.com games in the database are untouched either way, this only
    controls whether "Sync now" has anything to sync with.

    chesscom_username is a unique key name across the whole file (unlike
    path:/name:, no other section repeats it), so this doesn't need
    set_database_path()'s section-scoping -- same posture set_player_name()
    already takes for the equally-unique `name:` key."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    text = path.read_text()
    rendered = "null" if not username else f'"{username}"'
    new_text, n = re.subn(
        r'(?m)^(\s*)chesscom_username:\s*(?:"[^"]*"|null)(\s*#.*)?$',
        lambda m: f'{m.group(1)}chesscom_username: {rendered}{m.group(2) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find a player.chesscom_username line to update in {path} -- "
            "expected a line like `chesscom_username: null` or `chesscom_username: \"...\"`.")
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
        r'(?m)^(database:\n(?:[ \t].*\n)*?)(\s*)path:\s*\S+(\s*#.*)?$',
        lambda m: f'{m.group(1)}{m.group(2)}path: {db_path}{m.group(3) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find a database.path line to update in {path}.")
    path.write_text(new_text)


def _set_section_scalar(section: str, key: str, value, path=None):
    """Same comment-preserving substitution approach as set_player_name/
    set_database_path/set_engine_path, generalized to any bare (unquoted)
    scalar under a given top-level section -- used by the Analysis Jobs
    view (depth/multipv/threads/hash_mb/max_games/max_duration) so each
    setting doesn't need its own copy-pasted regex function.

    Scoped to `section:`'s OWN `key:` line, not a bare `key:` match
    anywhere in the file -- config.yaml repeats some key names across
    sections (`path:` under both `database:` and `engine:`, the exact
    case set_database_path()/set_engine_path() already had to guard
    against), so an unscoped regex would silently rewrite whichever
    same-named key happens to appear first.

    value=None writes the YAML `null` literal (e.g. clearing
    worker.max_duration back to "no cap"), not the literal string "None".

    (?m) only, deliberately NOT (?ms): with DOTALL, `.` inside
    `[ \t].*\n` matches newlines too, so the non-greedy line-walk through
    a long, comment-heavy section (engine: has far more lines than
    database:'s, which is why set_database_path()'s near-identical
    pattern never surfaced this) can swallow many lines per iteration and
    then backtrack character-by-character across the rest of the file --
    confirmed live: this hung for over a minute against the real
    engine.depth/worker.max_games before being fixed to plain (?m), where
    `.` correctly stops at each line's own `\n`."""
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    text = path.read_text()
    rendered = "null" if value is None else str(value)
    pattern = rf'(?m)^({section}:\n(?:[ \t].*\n)*?)(\s*){key}:\s*\S+(\s*#.*)?$'
    new_text, n = re.subn(
        pattern,
        lambda m: f'{m.group(1)}{m.group(2)}{key}: {rendered}{m.group(3) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(f"Could not find a {section}.{key} line to update in {path}.")
    path.write_text(new_text)


def set_engine_setting(key: str, value, path=None):
    """key in {depth, multipv, threads, hash_mb, pv_max_len, reuse_evals}
    -- NOT path (see set_engine_path(), which needs quoting for Windows
    paths with spaces; these are all bare numbers/booleans)."""
    _set_section_scalar("engine", key, value, path)


def set_worker_setting(key: str, value, path=None):
    """key in {max_games, max_duration} -- value=None is meaningful for
    both ("no cap" for either, matching config.yaml's own documented
    default), not an error case to special-case away."""
    _set_section_scalar("worker", key, value, path)


def set_analytics_setting(key: str, value, path=None):
    """key in {min_sample_size, utc_offset_hours, ...} -- any bare-scalar
    key under analytics:. Same _set_section_scalar mechanism as
    set_engine_setting/set_worker_setting."""
    _set_section_scalar("analytics", key, value, path)


def set_ingestion_setting(key: str, value, path=None):
    """key in {variant_policy, queue_strategy, berserk_max_clock_fraction,
    backlog_quota, backlog_quota_window} -- any bare-scalar key under
    ingestion:. variant_policy/queue_strategy are bare, unquoted words in
    config.yaml and _set_section_scalar's str(value) already renders a
    bare word correctly for these two (no spaces/special YAML chars), so
    no separate quoting branch is needed the way set_engine_path() needs
    one for filesystem paths."""
    _set_section_scalar("ingestion", key, value, path)


def set_sync_setting(key: str, value, path=None):
    """key: request_timeout_seconds -- the only scalar under sync: today."""
    _set_section_scalar("sync", key, value, path)


def set_sync_chesscom_setting(key: str, value, path=None):
    """key: request_timeout_seconds -- the only scalar under
    sync_chesscom: today."""
    _set_section_scalar("sync_chesscom", key, value, path)


def save_interactive_engine(settings: dict, path=None):
    """Replace the interactive_engine: block with the supplied settings dict.

    Uses a line-scan rather than a full yaml.safe_dump() so every other
    section's comments (and the rest of interactive_engine:'s own header
    comment) are preserved -- the same strategy as the rest of this file.
    Only the interactive_engine: block is rewritten; all other sections are
    passed through character-for-character.

    settings keys: time_sec (float), depth (int), threads (int),
    hash_mb (int), store_threshold (int).
    """
    cfg_path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    lines = cfg_path.read_text().splitlines(keepends=True)

    start_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r'^interactive_engine:', line):
            start_idx = i
        elif start_idx is not None and i > start_idx and re.match(r'^[a-z]', line):
            end_idx = i
            break

    new_block = yaml.dump({"interactive_engine": settings}, default_flow_style=False)

    if start_idx is None:
        # Section absent -- pre-v0.1.10 config that was copied before the
        # interactive_engine: key existed.  Append it cleanly.
        cfg_path.write_text("".join(lines).rstrip("\n") + "\n\n" + new_block)
        return
    if end_idx is None:
        end_idx = len(lines)

    # Preserve one blank line before the next section (new_block already ends
    # with \n, so appending "\n" produces exactly one blank line).
    new_lines = lines[:start_idx] + [new_block + "\n"] + lines[end_idx:]
    cfg_path.write_text("".join(new_lines))


# ---------------------------------------------------------------------------
# Pro profile management
# Each student/alt-account profile lives at:
#   ~/.chesswright/profiles/{username}/
#     config.yaml   -- copy of the main config with player.name + database.path set
#     games.db      -- isolated SQLite database for that profile
# The active profile is tracked by a plain text file:
#   ~/.chesswright/active_profile  -- contains the username, or absent for own account
# ---------------------------------------------------------------------------

CHESSWRIGHT_DIR = pathlib.Path.home() / ".chesswright"
PROFILES_DIR = CHESSWRIGHT_DIR / "profiles"
_ACTIVE_PROFILE_FILE = CHESSWRIGHT_DIR / "active_profile"


def get_active_profile() -> str | None:
    """Return the username of the currently active Pro profile, or None for own account."""
    if _ACTIVE_PROFILE_FILE.exists():
        username = _ACTIVE_PROFILE_FILE.read_text().strip()
        return username if username else None
    return None


def set_active_profile(username: str) -> None:
    CHESSWRIGHT_DIR.mkdir(exist_ok=True)
    _ACTIVE_PROFILE_FILE.write_text(username)


def clear_active_profile() -> None:
    _ACTIVE_PROFILE_FILE.unlink(missing_ok=True)


def get_profile_dir(username: str) -> pathlib.Path:
    return PROFILES_DIR / username.lower()


def get_profile_db_path(username: str) -> pathlib.Path:
    return get_profile_dir(username) / "games.db"


def get_profile_config_path(username: str) -> pathlib.Path:
    return get_profile_dir(username) / "config.yaml"


def initialize_profile(username: str) -> None:
    """Create a fresh profile directory for a student or alt account.

    Copies the current config.yaml as a template, then rewrites player.name
    and database.path for this profile. Safe to call if the profile already
    exists -- directory creation is idempotent and the config is only written
    on the very first call (so a user's live config changes aren't clobbered
    by a second call to this function).
    """
    profile_dir = get_profile_dir(username)
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_config = get_profile_config_path(username)
    if not profile_config.exists():
        shutil.copy(DEFAULT_CONFIG_PATH, profile_config)
        set_player_name(username, path=profile_config)
        set_database_path(str(get_profile_db_path(username)), path=profile_config)


def list_profiles() -> list[str]:
    """Return usernames of all initialized profiles, sorted alphabetically."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        d.name for d in PROFILES_DIR.iterdir()
        if d.is_dir() and (d / "config.yaml").exists()
    )


def remove_profile(username: str) -> None:
    """Delete a profile directory and all its data. Irreversible."""
    import shutil as _shutil
    profile_dir = get_profile_dir(username)
    if profile_dir.exists():
        _shutil.rmtree(profile_dir)
    if get_active_profile() == username.lower():
        clear_active_profile()


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
        r'(?m)^(engine:\n(?:[ \t].*\n)*?)(\s*)path:\s*\S+(\s*#.*)?$',
        lambda m: f'{m.group(1)}{m.group(2)}path: "{engine_path}"{m.group(3) or ""}',
        text, count=1)
    if n == 0:
        raise ValueError(
            f"Could not find an engine.path line to update in {path}.")
    path.write_text(new_text)
