# Phase 6 Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `dashboard/settings_view.py` from 6 flat, undividered sections into a tabbed Settings page with 4 new Common-tier controls (engine location, timezone offset, confidence threshold, ingestion behavior), a collapsed Advanced tier for the long tail, Engine Profiles presets, an in-page search/jump box, and reset/confirm safeguards — per `docs/superpowers/specs/2026-07-11-phase6-settings-design.md`.

**Architecture:** `st.tabs` replaces the current `st.divider()`-separated scroll, one private `_render_*_tab()` function per tab (matches this file's existing `_render_chesscom_section`/`_render_pro_section`/`_render_support_section` convention — no new files, no new package). New config.py functions follow the file's existing `_set_section_scalar`-backed wrapper pattern (`set_engine_setting`, `set_worker_setting`) rather than introducing a second config-mutation mechanism. Two `dashboard/data/*.py` functions and their view-layer callers pick up `analytics.utc_offset_hours`/`analytics.min_sample_size` as their default via the file's own existing `get_config(config_path=None)` convention, not a new plumbing mechanism.

**Tech Stack:** Python 3, Streamlit 1.58 (`st.tabs(..., default=, key=)` confirmed to support programmatic tab selection), PyYAML, `rapidfuzz` (already a dependency via Global Search), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- `annotation.*` and `achievements.*` get **no** UI control at any tier — this is a data-integrity boundary, not a scope trim. No task in this plan may add one.
- Every new control is either query-time (re-buckets/re-filters on next query, no stale-data risk) or forward-looking (affects future syncs/runs only) — never retroactively silent.
- Batch engine/worker settings (`engine.depth/multipv/threads/hash_mb`, `worker.max_games/max_duration`) stay on the Analysis Jobs page. Nothing in this plan duplicates them into Settings.
- New numeric controls use `min_value`/`max_value` bounds matching `config.yaml`'s own documented safe range, mirroring the existing Live Engine form.
- Help Center, Onboarding Maturation, and Notification Service are out of scope — do not add stub UI for any of them.
- Follow this repo's existing `_set_section_scalar`/`get_config`/`@st.cache_data` conventions exactly (see Task 1's File Structure notes) rather than introducing new ones.

---

## File Structure

- **Modify `dashboard/settings_view.py`** (currently 371 lines): restructured into `st.tabs`, existing sections extracted into `_render_account_data_tab`/`_render_analysis_engine_tab`/`_render_api_key_tab` (new) alongside the existing `_render_chesscom_section`/`_render_pro_section`/`_render_support_section` (unchanged), plus three new tab functions (`_render_analytics_display_tab`, `_render_ingestion_tab`, `_render_advanced_tab`) and a search box (`_render_search_box`). One clear responsibility per function: render one tab's content.
- **Modify `config.py`**: new thin wrapper functions (`set_analytics_setting`, `set_ingestion_setting`, `set_sync_setting`, `set_sync_chesscom_setting`, `reset_engine_path`) following the existing `set_engine_setting`/`set_worker_setting` pattern, plus a new Engine Profiles section (`save_engine_profile`/`list_engine_profiles`/`apply_engine_profile`/`delete_engine_profile`) storing to a new `~/.chesswright/engine_profiles.yaml`, distinctly named from the existing Pro student-profile functions in the same file.
- **Modify `dashboard/data/patterns.py`**: `get_day_hour_heatmap` gains a `config_path` param and applies `utc_offset_hours`.
- **Modify `dashboard/patterns_view.py`**: the heatmap's subheader/axis label become offset-aware; `get_config` added to its `_common` import.
- **Modify `dashboard/data/matchups.py`, `dashboard/data/points.py`, `dashboard/data/evolution.py`**: `get_nemesis_opponents`/`monthly_points`/`family_win_trend` pick up `analytics.min_sample_size` as their default when the caller doesn't override it. `dashboard/data/openings.py::get_openings_table` does the same via its file's existing `import config` precedent (not `get_config`, to match that file's own established style).
- **Modify `tests/conftest.py`**: incrementally extends the shared `config_yaml` fixture with the new sections/keys each task needs.
- **Modify `tests/unit/test_config.py`, `tests/ui/test_pages.py`**: new/extended coverage per task.
- **Create `tests/unit/test_settings_view.py`**: new file for the pure-logic helpers extracted from `settings_view.py` (engine-binary install, search ranking).

---

### Task 1: Tab scaffold — pure refactor of existing content

**Files:**
- Modify: `dashboard/settings_view.py` (whole `render()` function, lines 22–253)
- Modify: `tests/ui/test_pages.py:52-69` (add `"settings_view"` to the parametrized page list)

**Interfaces:**
- Produces: `_render_account_data_tab()`, `_render_analysis_engine_tab()`, `_render_api_key_tab()` — each takes no arguments, renders into whatever container is currently active (called from inside a `with tab:` block). Later tasks append to these functions and eventually add a `highlight_field=None` parameter (Task 9).
- Consumes: existing `_render_chesscom_section()`, `_render_pro_section()`, `_render_support_section()` — unchanged, just called from a tab instead of after a `st.divider()`.

This task moves code, it does not change behavior. No new tests needed beyond confirming the page still renders — this task's real deliverable is not breaking anything, verified by adding `settings_view` to the existing page-render smoke test (a real, pre-existing gap: `settings_view` was never in this list).

- [ ] **Step 1: Add `settings_view` to the page-render smoke test (currently failing to prove the gap first)**

In `tests/ui/test_pages.py`, add `"settings_view",` to the `test_no_arg_page_renders` parametrize list (around line 69, alongside `"ask_view"`):

```python
    @pytest.mark.parametrize("module_name", [
        "patterns_view",
        "openings_view",
        "game_endings_view",
        "insights_view",
        "training_queue_view",
        "points_view",
        "srs_drill_view",
        "evolution_view",
        "batch_impact_view",
        "analysis_jobs_view",
        "ask_view",
        "settings_view",
    ])
```

- [ ] **Step 2: Run it to confirm it currently passes against the OLD file (baseline)**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS (the old flat-render version already works fine — this establishes the baseline the refactor must not break).

- [ ] **Step 3: Rewrite `render()` with the tab scaffold, extracting existing bodies verbatim**

Replace the entire `render()` function (`dashboard/settings_view.py:22-253`, from `def render():` through the trailing `_render_support_section()` call) with:

```python
def render():
    st.title("Settings")

    tab_account, tab_engine, tab_api, tab_pro, tab_support = st.tabs([
        "Account & Data", "Analysis Engine", "Anthropic API key",
        "Chesswright Pro", "Support",
    ])

    with tab_account:
        _render_account_data_tab()
    with tab_engine:
        _render_analysis_engine_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()


def _render_api_key_tab():
    st.subheader("Anthropic API key")
    st.caption(
        "Optional. Powers the on-demand 'richer narrative' / commentary "
        "buttons throughout the app (game stories, opening and opponent "
        "commentary). Everything else works without one -- this only "
        "unlocks the Claude-API extras. You pay for your own usage "
        "directly through your own Anthropic account; this app never "
        "sends your key anywhere except Anthropic's API.")
    st.caption(
        "**Shared computers:** if this machine has multiple user accounts, "
        "be aware that without an OS keychain (see the warning below if "
        "one appears after saving) the key is stored in a plain text file "
        "that any other user on this system could read. If this is a "
        "shared machine, consider not configuring a key here, or use a "
        "machine you control exclusively.")

    current_key = api_key_store.get_api_key()
    secure_backend = api_key_store.using_secure_backend()

    if current_key:
        masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 12 else "set"
        st.success(f"A key is currently configured ({masked}).")
        if not secure_backend:
            st.warning(
                "No OS-native secure credential store was found on this "
                "system, so your key is stored in a plain text file at "
                "~/.chesswright/api_key.txt instead of your OS keychain. "
                "This is less secure -- anyone with access to your user "
                "account could read that file. This is normal on some "
                "minimal Linux installs; if you'd rather avoid it, install "
                "and run a Secret Service provider (e.g. gnome-keyring) "
                "and re-enter your key here.")
    else:
        st.info("No API key configured yet.")

    with st.form("api_key_form", clear_on_submit=True):
        new_key = st.text_input("Anthropic API key", type="password",
                                 placeholder="sk-ant-...")
        save_clicked = st.form_submit_button("Save key", type="primary")

    if save_clicked:
        if not new_key.strip():
            st.error("Enter a key before saving.")
        else:
            stored_securely = api_key_store.set_api_key(new_key)
            if stored_securely:
                st.success("Key saved to your OS credential store.")
            else:
                st.warning(
                    "Key saved, but no secure OS credential store was "
                    "available -- it's stored in a plain text file "
                    "(~/.chesswright/api_key.txt) instead. See the note "
                    "above for how to switch to secure storage.")
            st.rerun()

    if current_key:
        if st.button("Remove saved key"):
            api_key_store.clear_api_key()
            st.success("Saved key removed.")
            st.rerun()


def _render_analysis_engine_tab():
    st.subheader("Live engine settings")
    st.caption(
        "Controls the on-demand Stockfish analysis in the position browser and "
        "game detail panels. The live engine is always paused when the batch "
        "worker is running — these settings only affect interactive probes.")
    ie_cfg = config.load_config().get("interactive_engine", {})
    _ie_defaults = {
        "ie_time_sec":        float(ie_cfg.get("time_sec", 0.5)),
        "ie_depth":           int(ie_cfg.get("depth", 20)),
        "ie_threads":         int(ie_cfg.get("threads", 1)),
        "ie_hash_mb":         int(ie_cfg.get("hash_mb", 32)),
        "ie_store_threshold": int(ie_cfg.get("store_threshold", 20)),
        "ie_use_cloud_eval":  bool(ie_cfg.get("use_lichess_cloud_eval", True)),
    }
    for k, v in _ie_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    with st.form("live_engine_form"):
        col1, col2 = st.columns(2)
        time_sec = col1.number_input(
            "Time limit (s)",
            min_value=0.1, max_value=10.0,
            step=0.1, format="%.1f",
            key="ie_time_sec",
            help="Hard wall-clock cap per position. Always enforced alongside "
                 "the depth limit — whichever is hit first stops the search.")
        depth = col2.number_input(
            "Depth limit",
            min_value=5, max_value=40,
            step=1,
            key="ie_depth",
            help="Maximum search depth. Paired with the time limit — depth "
                 "alone is not a safe limit.")
        threads = col1.number_input(
            "Threads",
            min_value=1, max_value=8,
            step=1,
            key="ie_threads",
            help="Keep at 1 to avoid competing with the batch engine if both "
                 "happen to run on the same machine.")
        hash_mb = col2.number_input(
            "Hash (MB)",
            min_value=16, max_value=1024,
            step=16,
            key="ie_hash_mb",
            help="Stockfish hash table size for interactive probes. Smaller "
                 "than the batch engine's hash to keep the footprint low.")
        store_threshold = col1.number_input(
            "Store threshold (depth)",
            min_value=0, max_value=50,
            step=1,
            key="ie_store_threshold",
            help="Only save the result to position_cache when the actual "
                 "search depth reached this value. Set higher than the depth "
                 "limit above to disable auto-storing entirely.")
        use_cloud_eval = st.checkbox(
            "Use Lichess cloud evaluations when available",
            key="ie_use_cloud_eval",
            help="Before spinning up the local engine on a position lookup, "
                 "try Lichess's free cloud-eval database first (deep evals "
                 "for popular/opening positions, from other players' prior "
                 "analysis). Only the board position (FEN) is sent — no "
                 "account or game data. Falls back to the local engine on a "
                 "miss.")
        save_btn = st.form_submit_button("Save and restart engine", type="primary")

    if save_btn:
        new_settings = {
            "time_sec": round(float(time_sec), 1),
            "depth": int(depth),
            "threads": int(threads),
            "hash_mb": int(hash_mb),
            "store_threshold": int(store_threshold),
            "use_lichess_cloud_eval": bool(use_cloud_eval),
        }
        try:
            config.save_interactive_engine(new_settings)
            live_engine.get_engine_service.clear()
            st.toast("Live engine settings saved.", icon="✅")
        except Exception as e:
            st.error(f"Could not save settings: {e}")


def _render_account_data_tab():
    st.subheader("Import an existing database")
    st.caption(
        "For returning users: point at a chesswright-compatible database "
        "file already on this computer (e.g. from a previous install, or "
        "built by running the original open backend standalone) instead "
        "of starting fresh through the onboarding wizard. The file is "
        "copied into this app's own data directory -- the original file is "
        "never modified or referenced afterward.")

    pending_path = st.session_state.get("import_pending_path")

    if not pending_path:
        col1, col2 = st.columns([5, 1])
        with col2:
            st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            picked = native_file_picker.pick("database", key="import_native_picker")
        if picked and picked != st.session_state.get("import_native_picker_applied"):
            st.session_state["import_native_picker_applied"] = picked
            st.session_state["import_path_input"] = picked
        with col1:
            src = st.text_input("Path to the database file on this computer",
                                 placeholder="/home/you/some-folder/chess.db",
                                 key="import_path_input")
        if st.button("Import"):
            try:
                dest_dir = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent
                imported_path = db_import.import_database(pathlib.Path(src.strip()), dest_dir)
            except db_import.DatabaseImportError as e:
                st.error(str(e))
            else:
                st.session_state["import_pending_path"] = str(imported_path)
                st.session_state["import_suggested_username"] = \
                    db_import.suggest_player_name(imported_path) or ""
                st.rerun()
    else:
        st.success(f"Imported and migrated: `{pending_path}`.")
        suggested = st.session_state.get("import_suggested_username", "")
        st.caption(
            "Confirm whose account this database belongs to -- the most "
            "frequently-appearing username was pre-filled below, but this "
            "isn't auto-detected with certainty, so please check it before "
            "continuing.")
        username = st.text_input("Lichess username for this database", value=suggested)
        col1, col2 = st.columns(2)
        if col1.button("Use this database", type="primary", disabled=not username.strip()):
            config.set_database_path(pending_path)
            config.set_player_name(username.strip())
            del st.session_state["import_pending_path"]
            st.session_state.pop("import_suggested_username", None)
            st.cache_resource.clear()
            st.success("Switched to the imported database.")
            st.rerun()
        if col2.button("Cancel"):
            pathlib.Path(pending_path).unlink(missing_ok=True)
            del st.session_state["import_pending_path"]
            st.session_state.pop("import_suggested_username", None)
            st.rerun()

    st.divider()
    _render_chesscom_section()
```

Leave `_render_chesscom_section`, `_run_chesscom_sync`, `_render_pro_section`, `_render_support_section` exactly as they are today (unchanged, not shown here since this step doesn't touch them).

- [ ] **Step 4: Run the full test file to confirm the refactor didn't break anything**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS (same test as Step 2, now against the new tabbed version).

- [ ] **Step 5: Manual smoke check**

Run: `.venv/bin/streamlit run dashboard/app.py` (or use the `run` skill), navigate to Settings, confirm all 5 tabs render their expected content with no visual regressions from before the refactor.

- [ ] **Step 6: Commit**

```bash
git add dashboard/settings_view.py tests/ui/test_pages.py
git commit -m "Restructure Settings into tabs (pure refactor, no new features)"
```

---

### Task 2: Engine location control

**Files:**
- Modify: `dashboard/settings_view.py` (imports + `_render_analysis_engine_tab`)
- Create: `tests/unit/test_settings_view.py`

**Interfaces:**
- Produces: `_install_engine_binary(src_path: pathlib.Path, engines_dir: pathlib.Path, validate_fn=None) -> str` and `_install_engine_upload(uploaded_file, engines_dir: pathlib.Path, validate_fn=None) -> str` — pure-ish helpers (only side effect is filesystem writes) that Task 7 does not need but Task 8's reset logic doesn't touch either.
- Consumes: `worker.find_engine_path(explicit_path)`, `worker.validate_engine_path(path) -> str` (raises `RuntimeError`), `config.set_engine_path(path)`, `config.DEFAULT_CONFIG_PATH`, `components.native_file_picker.pick(kind, label=, key=) -> str | None`, `live_engine.get_engine_service.clear()` — all pre-existing, confirmed live in `worker.py`/`onboarding_view.py`/`live_engine.py`.

- [ ] **Step 1: Write the failing tests for the extracted install helpers**

Create `tests/unit/test_settings_view.py`:

```python
"""Unit tests for settings_view.py's pure-logic helpers (extracted from
Streamlit UI glue so they're testable without a real Stockfish binary)."""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "dashboard"))
import settings_view


@pytest.mark.unit
class TestInstallEngineBinary:
    def test_copies_chmods_and_validates(self, tmp_path):
        src = tmp_path / "fake_stockfish"
        src.write_text("#!/bin/sh\necho fake\n")
        engines_dir = tmp_path / "engines"

        name = settings_view._install_engine_binary(
            src, engines_dir, validate_fn=lambda p: "Fake Engine 1.0")

        dest = engines_dir / "fake_stockfish"
        assert dest.exists()
        assert os.access(dest, os.X_OK)
        assert name == "Fake Engine 1.0"

    def test_removes_file_on_validation_failure(self, tmp_path):
        src = tmp_path / "not_an_engine"
        src.write_text("garbage")
        engines_dir = tmp_path / "engines"

        def fail(_path):
            raise RuntimeError("not a UCI engine")

        with pytest.raises(RuntimeError, match="not a UCI engine"):
            settings_view._install_engine_binary(src, engines_dir, validate_fn=fail)

        assert not (engines_dir / "not_an_engine").exists()


@pytest.mark.unit
class TestInstallEngineUpload:
    def test_writes_bytes_chmods_and_validates(self, tmp_path):
        class FakeUpload:
            name = "fake_upload_engine"
            def getvalue(self):
                return b"#!/bin/sh\necho fake\n"

        engines_dir = tmp_path / "engines"
        name = settings_view._install_engine_upload(
            FakeUpload(), engines_dir, validate_fn=lambda p: "Fake Engine 2.0")

        dest = engines_dir / "fake_upload_engine"
        assert dest.exists()
        assert os.access(dest, os.X_OK)
        assert name == "Fake Engine 2.0"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_settings_view.py -v`
Expected: FAIL with `AttributeError: module 'settings_view' has no attribute '_install_engine_binary'`.

- [ ] **Step 3: Add imports and the two install helpers to `settings_view.py`**

Add to the import block at the top of `dashboard/settings_view.py` (after the existing `import pathlib`):

```python
import shutil
import stat

import requests
import streamlit as st

import api_key_store
import config
import db_import
import live_engine
import sync_chesscom
import worker
from _common import resolve_db_path
import components.native_file_picker as native_file_picker
```

Add these two functions (module level, anywhere above `_render_analysis_engine_tab`):

```python
def _install_engine_binary(src_path: pathlib.Path, engines_dir: pathlib.Path,
                            validate_fn=None) -> str:
    """Copies src_path into engines_dir, marks it executable, and validates
    it as a real UCI engine (worker.validate_engine_path by default --
    overridable so tests don't need a real engine binary). Returns the
    engine's self-reported name. Raises RuntimeError (from validate_fn) if
    it isn't a working UCI engine -- the partially-installed file is
    removed before re-raising, so a bad pick never lingers in engines_dir."""
    validate_fn = validate_fn or worker.validate_engine_path
    engines_dir.mkdir(parents=True, exist_ok=True)
    dest = engines_dir / src_path.name
    shutil.copy2(src_path, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        return validate_fn(str(dest))
    except RuntimeError:
        dest.unlink(missing_ok=True)
        raise


def _install_engine_upload(uploaded_file, engines_dir: pathlib.Path,
                            validate_fn=None) -> str:
    """Same as _install_engine_binary, for an st.file_uploader result
    instead of a filesystem path (write_bytes instead of copy2)."""
    validate_fn = validate_fn or worker.validate_engine_path
    engines_dir.mkdir(parents=True, exist_ok=True)
    dest = engines_dir / pathlib.Path(uploaded_file.name).name
    dest.write_bytes(uploaded_file.getvalue())
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        return validate_fn(str(dest))
    except RuntimeError:
        dest.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_settings_view.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Add the Engine location UI to `_render_analysis_engine_tab`, before the existing "Live engine settings" subheader**

Insert at the top of `_render_analysis_engine_tab()` (before `st.subheader("Live engine settings")`):

```python
def _render_analysis_engine_tab():
    st.subheader("Engine location")
    st.caption(
        "The Stockfish (or other UCI-compatible) engine binary used by "
        "both the batch analysis worker and the on-demand probes below. "
        "Auto-detected on first run -- use this if you've since installed "
        "Stockfish somewhere new, or want to switch engines.")

    cfg = config.load_config()
    current_path = cfg["engine"].get("path")
    detected_path = current_path or worker.find_engine_path(None)

    if detected_path:
        st.success(f"Using: `{detected_path}`" +
                   ("" if current_path else " (auto-detected)"))
    else:
        st.error(
            "No chess engine found. Install Stockfish from "
            "[stockfishchess.org/download](https://stockfishchess.org/download/) "
            "or browse for one below.")

    if st.button("Re-detect"):
        found = worker.find_engine_path(None)
        if found:
            config.set_engine_path(found)
            live_engine.get_engine_service.clear()
            st.success(f"Found and saved: `{found}`.")
            st.rerun()
        else:
            st.error("Still couldn't find one automatically.")

    st.warning(
        "Only pick a binary you obtained directly from "
        "[stockfishchess.org/download](https://stockfishchess.org/download/) "
        "or the official release page of another UCI engine. This app "
        "will execute the file you select -- do not pick a file from an "
        "untrusted source.")

    engines_dir = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent / "engines"

    picked_path = native_file_picker.pick(
        "engine", label="Browse for its executable file (native dialog)…",
        key="settings_engine_native_picker")
    if picked_path and picked_path != st.session_state.get(
            "settings_engine_native_picker_applied"):
        st.session_state["settings_engine_native_picker_applied"] = picked_path
        with st.spinner("Checking it speaks UCI..."):
            try:
                engine_name = _install_engine_binary(pathlib.Path(picked_path), engines_dir)
            except RuntimeError as e:
                st.error(str(e))
            else:
                config.set_engine_path(str(engines_dir / pathlib.Path(picked_path).name))
                live_engine.get_engine_service.clear()
                st.success(f"Confirmed and saved: {engine_name}.")
                st.rerun()

    uploaded_engine = st.file_uploader(
        "Or upload its executable file:", key="settings_engine_uploader")
    if uploaded_engine is not None:
        with st.spinner("Checking it speaks UCI..."):
            try:
                engine_name = _install_engine_upload(uploaded_engine, engines_dir)
            except RuntimeError as e:
                st.error(str(e))
            else:
                config.set_engine_path(str(engines_dir / pathlib.Path(uploaded_engine.name).name))
                live_engine.get_engine_service.clear()
                st.success(f"Confirmed and saved: {engine_name}.")
                st.rerun()

    st.divider()
    st.subheader("Live engine settings")
    st.caption(
        "Controls the on-demand Stockfish analysis in the position browser and "
        "game detail panels. The live engine is always paused when the batch "
        "worker is running — these settings only affect interactive probes.")
    ie_cfg = config.load_config().get("interactive_engine", {})
    _ie_defaults = {
        "ie_time_sec":        float(ie_cfg.get("time_sec", 0.5)),
        "ie_depth":           int(ie_cfg.get("depth", 20)),
        "ie_threads":         int(ie_cfg.get("threads", 1)),
        "ie_hash_mb":         int(ie_cfg.get("hash_mb", 32)),
        "ie_store_threshold": int(ie_cfg.get("store_threshold", 20)),
        "ie_use_cloud_eval":  bool(ie_cfg.get("use_lichess_cloud_eval", True)),
    }
    for k, v in _ie_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    with st.form("live_engine_form"):
        col1, col2 = st.columns(2)
        time_sec = col1.number_input(
            "Time limit (s)",
            min_value=0.1, max_value=10.0,
            step=0.1, format="%.1f",
            key="ie_time_sec",
            help="Hard wall-clock cap per position. Always enforced alongside "
                 "the depth limit — whichever is hit first stops the search.")
        depth = col2.number_input(
            "Depth limit",
            min_value=5, max_value=40,
            step=1,
            key="ie_depth",
            help="Maximum search depth. Paired with the time limit — depth "
                 "alone is not a safe limit.")
        threads = col1.number_input(
            "Threads",
            min_value=1, max_value=8,
            step=1,
            key="ie_threads",
            help="Keep at 1 to avoid competing with the batch engine if both "
                 "happen to run on the same machine.")
        hash_mb = col2.number_input(
            "Hash (MB)",
            min_value=16, max_value=1024,
            step=16,
            key="ie_hash_mb",
            help="Stockfish hash table size for interactive probes. Smaller "
                 "than the batch engine's hash to keep the footprint low.")
        store_threshold = col1.number_input(
            "Store threshold (depth)",
            min_value=0, max_value=50,
            step=1,
            key="ie_store_threshold",
            help="Only save the result to position_cache when the actual "
                 "search depth reached this value. Set higher than the depth "
                 "limit above to disable auto-storing entirely.")
        use_cloud_eval = st.checkbox(
            "Use Lichess cloud evaluations when available",
            key="ie_use_cloud_eval",
            help="Before spinning up the local engine on a position lookup, "
                 "try Lichess's free cloud-eval database first (deep evals "
                 "for popular/opening positions, from other players' prior "
                 "analysis). Only the board position (FEN) is sent — no "
                 "account or game data. Falls back to the local engine on a "
                 "miss.")
        save_btn = st.form_submit_button("Save and restart engine", type="primary")

    if save_btn:
        new_settings = {
            "time_sec": round(float(time_sec), 1),
            "depth": int(depth),
            "threads": int(threads),
            "hash_mb": int(hash_mb),
            "store_threshold": int(store_threshold),
            "use_lichess_cloud_eval": bool(use_cloud_eval),
        }
        try:
            config.save_interactive_engine(new_settings)
            live_engine.get_engine_service.clear()
            st.toast("Live engine settings saved.", icon="✅")
        except Exception as e:
            st.error(f"Could not save settings: {e}")
```

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Manual smoke check**

Launch the app, go to Settings → Analysis Engine, confirm the current engine path (or auto-detect message) shows correctly, and "Re-detect" works without error.

- [ ] **Step 8: Commit**

```bash
git add dashboard/settings_view.py tests/unit/test_settings_view.py
git commit -m "Add engine location control to Settings (closes a real gap: live_engine.py already told users to configure it here)"
```

---

### Task 3: Timezone offset control + dashboard heatmap bugfix

**Files:**
- Modify: `config.py` (new `set_analytics_setting`)
- Modify: `tests/conftest.py:74-90` (`config_yaml` fixture: add `analytics:` section)
- Modify: `tests/unit/test_config.py` (new test class)
- Modify: `dashboard/data/patterns.py:140-167` (`get_day_hour_heatmap`)
- Modify: `dashboard/patterns_view.py` (import + display labels)
- Modify: `tests/integration/test_data_layer.py:683-711` (new offset test)
- Modify: `dashboard/settings_view.py` (new `_render_analytics_display_tab`, wired into `render()`)

**Interfaces:**
- Produces: `config.set_analytics_setting(key, value, path=None)` — mirrors `set_engine_setting`. `data.patterns.get_day_hour_heatmap(duck_conn, config_path=None)` — same return shape as before `(win_pivot, rating_pivot)`, columns now labeled by local hour instead of raw UTC hour.
- Consumes: `config._set_section_scalar` (existing), `_common.get_config` (existing, already imported in `patterns.py`).

- [ ] **Step 1: Write the failing config.py test**

Add to `tests/unit/test_config.py` (new class, anywhere after `TestSetDatabasePath`):

```python
@pytest.mark.unit
class TestSetAnalyticsSetting:
    def test_sets_utc_offset_hours(self, config_yaml):
        config.set_analytics_setting("utc_offset_hours", -5, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["analytics"]["utc_offset_hours"] == -5

    def test_does_not_touch_other_analytics_keys(self, config_yaml):
        config.set_analytics_setting("utc_offset_hours", 3, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["analytics"]["min_sample_size"] == 5
```

Extend the `config_yaml` fixture in `tests/conftest.py` (currently lines 74-90) to add an `analytics:` section:

```python
@pytest.fixture
def config_yaml(tmp_path):
    """A minimal config.yaml written to a temp directory for mutation tests."""
    cfg_text = (
        'player:\n'
        '  name: "CHANGE_ME"\n'
        'database:\n'
        '  path: chess.db\n'
        'engine:\n'
        '  path: null\n'
        '  depth: 20\n'
        'interactive_engine:\n'
        '  threads: 1\n'
        '  hash_mb: 32\n'
        '  time_sec: 0.5\n'
        '  depth: 20\n'
        '  store_threshold: 20\n'
        'analytics:\n'
        '  min_sample_size: 5\n'
        '  utc_offset_hours: 0\n'
    )
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text)
    return cfg_path
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestSetAnalyticsSetting" -v`
Expected: FAIL with `AttributeError: module 'config' has no attribute 'set_analytics_setting'`.

- [ ] **Step 3: Add `set_analytics_setting` to `config.py`**

Add directly after the existing `set_worker_setting` function in `config.py`:

```python
def set_analytics_setting(key: str, value, path=None):
    """key in {min_sample_size, utc_offset_hours, ...} -- any bare-scalar
    key under analytics:. Same _set_section_scalar mechanism as
    set_engine_setting/set_worker_setting."""
    _set_section_scalar("analytics", key, value, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestSetAnalyticsSetting" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing test for the patterns.py bugfix**

Add to `tests/integration/test_data_layer.py`, directly after the existing `test_get_day_hour_heatmap_returns_aligned_pivots` (around line 711):

```python
    def test_get_day_hour_heatmap_applies_utc_offset(self, migrated_db, monkeypatch):
        """hour_utc=23 with a +2 offset lands in hour_local=1 (wraps past
        midnight) -- shifts hour only, leaves day_of_week alone, matching
        this app's existing CLI report_by_hour_bucket convention
        (analytics.py) rather than inventing a new cross-adjustment."""
        from data import patterns as patterns_module
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "day_of_week, hour_utc, rating_diff) VALUES ('g1', 'W', 'B', 'win', 3, 23, 0)")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        monkeypatch.setattr(
            patterns_module, "get_config",
            lambda config_path=None: {"analytics": {"utc_offset_hours": 2}})
        try:
            win_pivot, _ = patterns_module.get_day_hour_heatmap(duck)
            assert 1 in win_pivot.columns
            assert 23 not in win_pivot.columns
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
```

- [ ] **Step 6: Run to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_data_layer.py -k "test_get_day_hour_heatmap_applies_utc_offset" -v`
Expected: FAIL — `get_day_hour_heatmap()` doesn't accept being monkeypatched this way yet because it doesn't call `get_config` at all (raises `TypeError` or just returns unshifted columns, so the assertion `23 not in win_pivot.columns` fails).

- [ ] **Step 7: Fix `get_day_hour_heatmap` in `dashboard/data/patterns.py`**

Replace lines 140-167 (the whole `get_day_hour_heatmap` function):

```python
def get_day_hour_heatmap(duck_conn, config_path=None):
    """day_of_week x hour_local win rate, full dataset (board-derived).
    hour_local = (hour_utc + analytics.utc_offset_hours) % 24 -- shifts the
    HOUR axis only into the player's own local time; day_of_week is left
    alone, matching this app's older CLI report_by_hour_bucket convention
    (analytics.py) of never cross-adjusting the day when converting hours.

    Also returns avg_rating_diff pivoted to the same (day_of_week,
    hour_local) shape -- a confidence-gap disclaimer, not a new finding:
    win% varies by hour partly because the opponent pool's average
    strength varies by hour too, not only because of how the player
    performs at that hour. Verified live (2026-07-07) on the real dev DB:
    hours 17-18 UTC combine both the most favorable average rating_diff
    (+33 to +37) and the highest win% (49-50%), while hours 20-23 combine
    a negative rating_diff (-20 to -35) with some of the lowest win%, so a
    bare win% cell can't tell "played worse at this hour" apart from
    "faced tougher opponents at this hour." Returns (win_pct_pivot,
    avg_rating_diff_pivot) -- callers pass the second into charts.heatmap's
    hover_extra, they are never blended into one number."""
    cfg = get_config(config_path)
    utc_offset_hours = cfg["analytics"]["utc_offset_hours"]
    df = duck_conn.execute("""
        SELECT day_of_week, hour_utc,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               AVG(rating_diff) AS avg_rating_diff
        FROM db.games
        WHERE day_of_week IS NOT NULL AND hour_utc IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY day_of_week, hour_utc
    """).fetchdf()
    df["hour_local"] = (df["hour_utc"] + utc_offset_hours) % 24
    win_pivot = df.pivot(index="day_of_week", columns="hour_local", values="win_pct")
    rating_pivot = df.pivot(index="day_of_week", columns="hour_local", values="avg_rating_diff")
    return win_pivot, rating_pivot
```

- [ ] **Step 8: Run both tests to verify they pass**

Run: `.venv/bin/pytest tests/integration/test_data_layer.py -k "test_get_day_hour_heatmap" -v`
Expected: PASS (both the pre-existing aligned-pivots test and the new offset test — the aligned-pivots test still passes because the repo's real `config.yaml` has `utc_offset_hours: 0`, so `hour_local == hour_utc` unchanged).

- [ ] **Step 9: Update the display labels in `dashboard/patterns_view.py`**

Add `get_config` to the existing `_common` import (line 18):

```python
from _common import get_connections, get_config, persist_filter, render_where_next, restore_filter_default
```

Replace the heatmap rendering block (around lines 497-516):

```python
    with st.container(border=True):
        offset = get_config()["analytics"]["utc_offset_hours"]
        st.subheader(f"Win rate heatmap: day of week × hour of day (UTC{offset:+d})")
        st.caption("Hover a cell to see your average rating difference at that day/hour too -- "
                   "win rate varies partly because who you face varies by time of day, not "
                   "only how you play then.")
        heatmap_df, rating_df = cached_day_hour_heatmap(duck_conn)
        day_labels = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        heatmap_df = heatmap_df.rename(index=day_labels)
        rating_df = rating_df.rename(index=day_labels).map(
            lambda v: "--" if pd.isna(v) else f"{v:+.0f}")
        st.plotly_chart(
            charts.heatmap(heatmap_df, theme.DIVERGING_COLORSCALE, value_suffix="%",
                           x_title=f"Hour of day (UTC{offset:+d})", y_title="Day of week",
                           colorbar_title="Win %",
                           hover_extra=(rating_df, "Avg rating diff")),
            theme=None)
```

- [ ] **Step 10: Add the Settings control**

Add a new function to `dashboard/settings_view.py` and wire it into `render()`'s tabs (`render()` gains one more tab, `_render_analytics_display_tab`):

```python
def _render_analytics_display_tab():
    st.subheader("Local timezone")
    st.caption(
        "Your local UTC offset, used to show 'time of day' findings "
        "(like the day-of-week × hour win-rate map on Patterns & "
        "Tendencies) in your own local time instead of raw UTC.")
    cfg = config.load_config()
    offset = st.number_input(
        "UTC offset (hours)", min_value=-12, max_value=14, step=1,
        value=int(cfg["analytics"]["utc_offset_hours"]),
        help="E.g. -5 for US Eastern Standard Time, +1 for Central "
             "European Time.")
    if st.button("Save timezone"):
        config.set_analytics_setting("utc_offset_hours", int(offset))
        st.cache_data.clear()
        st.toast("Timezone saved.", icon="✅")
        st.rerun()
```

Update `render()`:

```python
def render():
    st.title("Settings")

    tab_account, tab_engine, tab_analytics, tab_api, tab_pro, tab_support = st.tabs([
        "Account & Data", "Analysis Engine", "Analytics & Display",
        "Anthropic API key", "Chesswright Pro", "Support",
    ])

    with tab_account:
        _render_account_data_tab()
    with tab_engine:
        _render_analysis_engine_tab()
    with tab_analytics:
        _render_analytics_display_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()
```

- [ ] **Step 11: Run the full affected test set**

Run: `.venv/bin/pytest tests/unit/test_config.py tests/integration/test_data_layer.py tests/ui/test_pages.py -v`
Expected: all PASS.

- [ ] **Step 12: Manual smoke check**

Launch the app, set a non-zero offset in Settings → Analytics & Display, save, then check Patterns & Tendencies' day/hour heatmap subheader and x-axis both show the new `UTC±N` label and that cell values shifted by N hours (wrapping correctly at 0/24).

- [ ] **Step 13: Commit**

```bash
git add config.py tests/conftest.py tests/unit/test_config.py tests/integration/test_data_layer.py dashboard/data/patterns.py dashboard/patterns_view.py dashboard/settings_view.py
git commit -m "Add timezone offset control; fix dashboard day/hour heatmap to actually apply it"
```

---

### Task 4: Confidence / sample-size threshold control

**Files:**
- Modify: `dashboard/data/matchups.py:103` (`get_nemesis_opponents`)
- Modify: `dashboard/data/points.py:204` (`monthly_points`)
- Modify: `dashboard/data/evolution.py:220` (`family_win_trend`)
- Modify: `dashboard/data/patterns.py:943` (`get_event_name_breakdown`)
- Modify: `dashboard/data/openings.py:366` (`get_openings_table`)
- Modify: `tests/unit/test_evolution.py`, new tests in `tests/integration/test_data_layer.py`
- Modify: `dashboard/settings_view.py` (`_render_analytics_display_tab`)

**Interfaces:**
- Produces: each of the 5 functions above changes its `min_games`/`min_games_per_quarter` default from a hardcoded literal to `None`, resolving to `analytics.min_sample_size` when the caller doesn't pass one explicitly. Existing explicit-override call sites (`matchups_view.py`'s slider, `cached_queries.py`'s `min_games=1`) are untouched and continue to override.
- **Deliberately excluded, and why (do not touch these in this task):** `openings.get_most_repeated_positions` (its own docstring already documents the cache it reads from has its own baked-in `min_games=5` floor — a config-driven default here wouldn't do anything real above or below that floor); `openings.get_opening_moves_from_fen`'s `min_games` (a per-FEN interactive-lookup gate, not an aggregate confidence gate); `evolution.compute_dominant_move_flips`'s `min_games_each_era` (a distinct, deliberately-named per-era parameter); `insights.py`'s 6 module-level `*_THRESHOLDS` constants (computed once at import time from named, signal-specific constants — not a runtime default, and each is a distinct metric, not the generic "is this bucket big enough" gate this task targets).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_evolution.py`, inside the existing `TestFamilyWinTrend` class (which already has `test_drops_thin_quarters`/`test_unknown_family_returns_empty` and already uses the file's own `_rows(entries)` helper — `entries: (year, quarter, family, n_games, n_wins)`). The file imports `family_win_trend` by name via `from data.evolution import (...)` at the top, so monkeypatching needs a separate module-object import (`from data import evolution as evolution_module`) purely to reach the `get_config` name bound inside that module — the bare `family_win_trend` call stays exactly as every other test in this class already calls it, since Python functions resolve globals from their own module regardless of how the caller imported them:

```python
    def test_uses_config_min_sample_size_when_not_passed(self, monkeypatch):
        from data import evolution as evolution_module
        monkeypatch.setattr(
            evolution_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 2}})
        df = _rows([(2018, 1, "X", 3, 2)])  # 3 games >= min_sample_size=2
        out = family_win_trend(df, "X")
        assert len(out) == 1
        assert out.iloc[0].label == "2018 Q1"

    def test_explicit_override_still_wins(self, monkeypatch):
        from data import evolution as evolution_module
        monkeypatch.setattr(
            evolution_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 100}})
        df = _rows([(2018, 1, "X", 3, 2)])
        out = family_win_trend(df, "X", min_games_per_quarter=2)  # explicit 2 overrides config's 100
        assert len(out) == 1
        assert out.iloc[0].label == "2018 Q1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_evolution.py -k "test_uses_config_min_sample_size_when_not_passed or test_explicit_override_still_wins" -v`
Expected: FAIL — `family_win_trend` doesn't import `get_config` yet, so `monkeypatch.setattr(evolution_module, "get_config", ...)` raises `AttributeError: <module 'data.evolution'> does not have the attribute 'get_config'`.

- [ ] **Step 3: Update `dashboard/data/evolution.py`**

Add to the top imports:

```python
from _common import get_config
```

Replace the `family_win_trend` signature and its threshold line:

```python
def family_win_trend(filtered: pd.DataFrame, family: str,
                     min_games_per_quarter: int | None = None,
                     config_path=None) -> pd.DataFrame:
    """Win% per quarter for one family, from the already-loaded counts
    frame (no DB hit). Quarters with fewer than min_games_per_quarter
    games are dropped rather than plotted as fake-precise points.
    min_games_per_quarter defaults to analytics.min_sample_size when not
    passed explicitly -- the shared confidence-threshold config, per
    docs/superpowers/specs/2026-07-11-phase6-settings-design.md."""
    if min_games_per_quarter is None:
        min_games_per_quarter = get_config(config_path)["analytics"]["min_sample_size"]
    fam = filtered[filtered["family"] == family]
    if fam.empty:
        return pd.DataFrame(columns=["label", "n_games", "win_pct", "period"])
    out = fam.groupby("period", as_index=False)[["n_games", "n_wins"]].sum()
    quarter_thresholds = default_thresholds(min_games_per_quarter)
    out = out[out["n_games"].map(
        lambda n: confidence_tier(n, quarter_thresholds) != "insufficient")]
    out["win_pct"] = 100.0 * out["n_wins"] / out["n_games"]
    out["label"] = out["period"].map(_period_label)
    return out.sort_values("period").reset_index(drop=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_evolution.py -k "TestFamilyWinTrend" -v`
Expected: PASS (4 tests: the 2 pre-existing plus the 2 new ones added to the same class).

- [ ] **Step 5: Repeat the same pattern for `matchups.get_nemesis_opponents`**

Add a test to `tests/integration/test_data_layer.py`'s existing `TestMatchupsData` class (line 209):

```python
    def test_get_nemesis_opponents_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import matchups as matchups_module
        monkeypatch.setattr(
            matchups_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "opponent_name, rating_diff) VALUES ('g1', 'W', 'B', 'loss', 'Bob', 0)")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = matchups_module.get_nemesis_opponents(duck)
            assert "Bob" in df.opponent_name.values  # 1 game qualifies at min_sample_size=1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
```

Run: `.venv/bin/pytest tests/integration/test_data_layer.py -k "test_get_nemesis_opponents_uses_config" -v`
Expected: FAIL first (signature/behavior not yet changed), then update `dashboard/data/matchups.py`:

```python
def get_nemesis_opponents(duck_conn, min_games: int | None = None, config_path=None):
    """Mirrors analysis/nemesis_opponents.py -- ranked by score% (win +
    0.5*draw, standard tournament scoring) so repeated draws aren't
    misread as losses. Real finding: 17.1% score against a specific
    41-game opponent, one of the largest single-opponent samples in the
    dataset -- never previously surfaced in the dashboard.

    Also returns expected_score_pct/surprise_pct: a confidence-gap fix on
    top of raw score_pct, which conflates "genuinely tough matchup" with
    "this opponent is just rated well above you, no surprise there."
    expected_score_pct is the average Elo-predicted score (standard
    logistic curve, 400-point scale) given each game's OWN rating_diff,
    averaged per game -- not derived from the opponent's average
    rating_diff, which is a different (and wrong) quantity by Jensen's
    inequality once game-to-game rating gaps vary. surprise_pct =
    score_pct - expected_score_pct: how far below what the rating gap
    alone predicts, so a large negative number is a genuine surprise, not
    just "this opponent happens to be much stronger."

    min_games defaults to analytics.min_sample_size when not passed
    explicitly. It remains the hard SQL gate below; it doubles as
    confidence.py's "low" tier threshold via default_thresholds(), so the
    returned frame also carries a confidence_tier column (every row is
    at least "low" by construction) for future badge use without
    changing which opponents are returned."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    thresholds = default_thresholds(min_games)
    # all_lichess gates the Opponent Prep deep link: prep's fetch pipeline
    # (sync.py) is lichess-only, so a chess.com opponent's name pre-filled
    # into it would scout the wrong (or a nonexistent) player. Names are
    # grouped across sources, so require every game vs. this opponent to
    # be a lichess game before treating the name as a lichess username.
    df = duck_conn.execute("""
        SELECT opponent_name,
               COUNT(*) AS n,
               SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) AS draws,
               SUM(CASE WHEN outcome_for_player='loss' THEN 1 ELSE 0 END) AS losses,
               MIN(CASE WHEN site LIKE 'https://lichess.org/%' THEN 1 ELSE 0 END) AS all_lichess,
               COUNT(rating_diff) AS n_rated,
               AVG(CASE WHEN rating_diff IS NOT NULL
                        THEN 1.0 / (1.0 + POWER(10.0, -rating_diff / 400.0)) END) AS expected_score_frac
        FROM db.games
        WHERE opponent_name IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY opponent_name
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()
    df["score_pct"] = 100.0 * (df.wins + 0.5 * df.draws) / df.n
    df["expected_score_pct"] = 100.0 * df["expected_score_frac"]
    df["surprise_pct"] = df["score_pct"] - df["expected_score_pct"]
    df["confidence_tier"] = df.n.map(lambda n: confidence_tier(n, thresholds))
    return df.drop(columns=["expected_score_frac"])
```

Run again: Expected PASS.

- [ ] **Step 6: Repeat for `points.monthly_points`**

Add a test to `tests/integration/test_data_layer.py`'s existing `TestPointsData` class (line 806):

```python
    def test_monthly_points_uses_config_min_sample_size(self, monkeypatch):
        from data import points as points_module
        monkeypatch.setattr(
            points_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        classified = pd.DataFrame({
            "game_id": ["g1"], "period": ["2026.01"], "points": [1.0], "leaked": [0.0],
        })
        out = points_module.monthly_points(classified)
        assert len(out) == 1  # 1 game qualifies at min_sample_size=1
```

Update `dashboard/data/points.py`:

```python
def monthly_points(classified, min_games: int | None = None, config_path=None):
    """Per month: actual score vs. score with leaks recovered, both as
    raw point sums and per-game percentages (the chart plots the
    percentages -- monthly game volume varies by two orders of magnitude
    in real data, so raw sums mostly graph volume, not quality). month is
    a real datetime: the 'YYYY.MM' period strings LOOK numeric to plotly,
    which coerces them onto a fractional-year continuous axis (confirmed
    on the rendered chart, axis read 2018..2026). Months under min_games
    are dropped -- same single-game-noise guard as get_progress_by_month.
    min_games defaults to analytics.min_sample_size when not passed
    explicitly."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    df = classified[classified.period.notna() & (classified.period != "")]
    if df.empty:
        return pd.DataFrame(columns=["period", "month", "n_games", "actual",
                                     "potential", "actual_pct", "potential_pct"])
    out = (df.groupby("period")
           .agg(n_games=("game_id", "size"), actual=("points", "sum"),
                leaked=("leaked", "sum"))
           .reset_index()
           .sort_values("period", ignore_index=True))
    out["potential"] = out.actual + out.leaked
    month_thresholds = default_thresholds(min_games)
    out = out[out.n_games.map(
        lambda n: confidence_tier(n, month_thresholds) != "insufficient")]
    out = out.drop(columns="leaked").reset_index(drop=True)
    out["actual_pct"] = 100.0 * out.actual / out.n_games
    out["potential_pct"] = 100.0 * out.potential / out.n_games
    out["month"] = pd.to_datetime(out.period, format="%Y.%m")
    return out
```

Run: `.venv/bin/pytest tests/integration/test_data_layer.py -k "test_monthly_points_uses_config_min_sample_size" -v` — Expected PASS.

- [ ] **Step 7: Repeat for `patterns.get_event_name_breakdown` (already has a `config_path` param, just currently unused)**

Add a test to `tests/integration/test_data_layer.py`'s existing `TestPatternsData` class (line 633, the same class Task 3's heatmap tests live in):

```python
    def test_get_event_name_breakdown_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import patterns as patterns_module
        monkeypatch.setattr(
            patterns_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, event) "
            "VALUES ('g1', 'W', 'B', 'win', 'Weekly Rapid Arena')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = patterns_module.get_event_name_breakdown(duck)
            assert "Weekly Rapid Arena" in df.event.values  # 1 game qualifies at min_sample_size=1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
```

Update `dashboard/data/patterns.py`:

```python
def get_event_name_breakdown(duck_conn, min_games: int | None = None, config_path=None) -> pd.DataFrame:
    """Win/draw/loss% and ACPL for each individually-NAMED tournament/arena
    (e.g. "Hourly SuperBlitz Arena", "Weekly Rapid Arena") -- the specific-
    events half of the Event Type Breakdown. Reuses
    get_event_type_performance's same classification (via _event_perf_rows)
    then restricts to the "Tournament / Arena" category and groups by the
    raw `event` name instead of the 2-way category, so the generic "Rated
    <category> game" casual buckets (already covered by the 2-category
    summary) never appear here. min_games defaults to
    analytics.min_sample_size when not passed explicitly, gating one-off
    or rarely-played events from cluttering the table -- this is a
    per-EVENT-NAME rollup, not per-tournament-instance (see module comment
    above for why the latter isn't feasible from the data Lichess gives us).

    Returns event, n_games, win_pct, draw_pct, loss_pct, acpl, n_analyzed --
    sorted by n_games descending."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    cols = ["event", "n_games", "win_pct", "draw_pct", "loss_pct", "acpl", "n_analyzed"]
    df = _event_perf_rows(duck_conn)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df[df.category == "Tournament / Arena"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = _aggregate_event_rows(df, "event")
    out = pd.DataFrame(rows, columns=cols)
    out = out[out.n_games >= min_games]
    return out.sort_values("n_games", ascending=False).reset_index(drop=True)
```

Since this wrapper is cached (`patterns_view.py`'s `cached_event_name_breakdown`), the timezone-style `st.cache_data.clear()` in Step 10 below already covers it (same Settings save action clears the whole cache).

- [ ] **Step 8: Repeat for `openings.get_openings_table` (uses this file's own `import config` precedent, not `get_config`)**

Add a test to `tests/integration/test_data_layer.py`:

```python
    def test_get_openings_table_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import openings as openings_module
        monkeypatch.setattr(
            openings_module.config, "load_config",
            lambda *a, **kw: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "opening_family, player_color) VALUES "
            "('g1', 'W', 'B', 'win', 'Sicilian', 'white')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = openings_module.get_openings_table(duck, migrated_db)
            assert "Sicilian" in df.opening_family.values  # 1 game qualifies at min_sample_size=1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
```

Update `dashboard/data/openings.py`:

```python
def get_openings_table(duck_conn, sqlite_conn, min_games: int | None = None):
    """Single bulk GROUP BY for the ACPL side, not one acpl_and_blunder_rate
    call per (opening, color) row -- measured cost of the per-row version:
    74 rows x ~0.5s/full-table-scan = ~39s. moves has no index on cpl/
    opening_family, so every targeted query scans all ~2M rows; one grouped
    pass over the same rows costs ~0.5s total instead of 74x that.

    min_games defaults to analytics.min_sample_size when not passed
    explicitly (this file's own config.load_config() precedent, matching
    this file's existing interactive_engine lookup elsewhere, rather than
    the get_config() convention used in the rest of dashboard/data/). It
    doubles as confidence.py's "low" tier threshold via
    default_thresholds(). Not attached to the returned frame as a column:
    openings_view.py renders it via st.dataframe with no column allowlist,
    so a new column would leak into the UI -- left as a future badge hook,
    not wired in here."""
    if min_games is None:
        min_games = config.load_config()["analytics"]["min_sample_size"]
    _thresholds = default_thresholds(min_games)  # noqa: F841 (future badge hook)
    counts = duck_conn.execute("""
        SELECT opening_family, player_color, COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               100.0 * SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) / COUNT(*) AS draw_pct
        FROM db.games
        WHERE opening_family IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY opening_family, player_color
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()

    acpl_rows = sqlite_conn.execute("""
        SELECT g.opening_family, g.player_color, COUNT(DISTINCT m.game_id) AS n_analyzed, AVG(m.cpl) AS acpl
        FROM moves m JOIN games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND g.opening_family IS NOT NULL
        GROUP BY g.opening_family, g.player_color
    """).fetchall()
    acpl_lookup = {(family, color): (n_analyzed, acpl) for family, color, n_analyzed, acpl in acpl_rows}

    acpls, n_analyzed_list = [], []
    for row in counts.itertuples():
        n_analyzed, acpl = acpl_lookup.get((row.opening_family, row.player_color), (0, None))
        acpls.append(acpl)
        n_analyzed_list.append(n_analyzed)
    counts["acpl"] = acpls
    counts["n_analyzed"] = n_analyzed_list
    return counts.sort_values("n", ascending=False).reset_index(drop=True)
```

(This reproduces the function's existing body verbatim below the changed `min_games` line — the only change in this task is where `min_games`'s value comes from, not the SQL/pandas logic itself.)

- [ ] **Step 9: Run all the new and pre-existing affected tests together**

Run: `.venv/bin/pytest tests/unit/test_evolution.py::TestFamilyWinTrend tests/integration/test_data_layer.py -k "min_sample_size or still_wins" -v`
Expected: all PASS (4 tests in `TestFamilyWinTrend` — 2 pre-existing regression checks plus the 2 new ones — plus the 4 new integration tests from Steps 5-8).

- [ ] **Step 10: Add the Settings control**

Append to `_render_analytics_display_tab()` in `dashboard/settings_view.py` (after the timezone control from Task 3):

```python
    st.divider()
    st.subheader("Confidence threshold")
    st.caption(
        "The minimum sample size (games/positions) a stat needs before "
        "it's shown as trustworthy instead of flagged '(small sample)' "
        "across Insights, Openings, Matchups, and other pages. One shared "
        "threshold, not a per-page setting.")
    min_sample_size = st.number_input(
        "Minimum sample size", min_value=1, max_value=100, step=1,
        value=int(cfg["analytics"]["min_sample_size"]),
        help="Groups below this many analyzed games are shown but marked "
             "as a small sample, rather than hidden.")
    if st.button("Save confidence threshold"):
        config.set_analytics_setting("min_sample_size", int(min_sample_size))
        st.cache_data.clear()
        st.toast("Confidence threshold saved.", icon="✅")
        st.rerun()
```

- [ ] **Step 11: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add dashboard/data/evolution.py dashboard/data/matchups.py dashboard/data/points.py dashboard/data/patterns.py dashboard/data/openings.py tests/unit/test_evolution.py tests/integration/test_data_layer.py dashboard/settings_view.py
git commit -m "Realize the roadmap's 'one confidence threshold, configurable once' call across 5 call sites"
```

---

### Task 5: Ingestion behavior dropdowns

**Files:**
- Modify: `config.py` (new `set_ingestion_setting`)
- Modify: `tests/conftest.py` (`config_yaml` fixture: add `ingestion:` section)
- Modify: `tests/unit/test_config.py` (new test class)
- Modify: `dashboard/settings_view.py` (new `_render_ingestion_tab`, wired into `render()`)

**Interfaces:**
- Produces: `config.set_ingestion_setting(key, value, path=None)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:

```python
@pytest.mark.unit
class TestSetIngestionSetting:
    def test_sets_variant_policy(self, config_yaml):
        config.set_ingestion_setting("variant_policy", "include", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["ingestion"]["variant_policy"] == "include"

    def test_sets_queue_strategy(self, config_yaml):
        config.set_ingestion_setting("queue_strategy", "chronological", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["ingestion"]["queue_strategy"] == "chronological"
```

Extend the `config_yaml` fixture in `tests/conftest.py` with an `ingestion:` section (add after the `analytics:` block Task 3 added):

```python
        'ingestion:\n'
        '  variant_policy: skip\n'
        '  queue_strategy: interleaved_by_year\n'
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestSetIngestionSetting" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add `set_ingestion_setting` to `config.py`**

```python
def set_ingestion_setting(key: str, value, path=None):
    """key in {variant_policy, queue_strategy, berserk_max_clock_fraction,
    backlog_quota, backlog_quota_window} -- any bare-scalar key under
    ingestion:. variant_policy/queue_strategy are quoted strings in
    config.yaml but _set_section_scalar's str(value) already renders a
    bare word correctly for these two (no spaces/special YAML chars), so
    no separate quoting branch is needed the way set_engine_path() needs
    one for filesystem paths."""
    _set_section_scalar("ingestion", key, value, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestSetIngestionSetting" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Add the Ingestion tab**

Add to `dashboard/settings_view.py`:

```python
def _render_ingestion_tab():
    st.subheader("New game ingestion")
    st.caption(
        "Controls how future syncs (lichess/chess.com) and the analysis "
        "worker treat newly-fetched games. Doesn't affect games already "
        "in your database.")
    cfg = config.load_config()

    variant_options = ["skip", "include"]
    variant_policy = st.selectbox(
        "Non-standard variants (Chess960, Atomic, ...)",
        options=variant_options,
        index=variant_options.index(cfg["ingestion"]["variant_policy"]),
        help="'skip' (default) ignores non-Standard-chess games entirely -- "
             "safe, since the batch engine assumes normal rules. Only "
             "choose 'include' if you plan to analyze those games with a "
             "variant-aware engine separately.")

    queue_options = ["interleaved_by_year", "chronological", "reverse_chronological"]
    queue_strategy = st.selectbox(
        "Analysis queue order",
        options=queue_options,
        index=queue_options.index(cfg["ingestion"]["queue_strategy"]),
        help="Controls which unanalyzed games the worker picks next. "
             "'interleaved_by_year' (default) samples across your whole "
             "history early instead of only your oldest or newest games.")

    if st.button("Save ingestion settings"):
        config.set_ingestion_setting("variant_policy", variant_policy)
        config.set_ingestion_setting("queue_strategy", queue_strategy)
        st.toast("Ingestion settings saved.", icon="✅")
        st.rerun()
```

Update `render()` in full to add the tab (inserting `tab_ingestion` between `tab_analytics` and `tab_api`):

```python
def render():
    st.title("Settings")

    tab_account, tab_engine, tab_analytics, tab_ingestion, tab_api, tab_pro, tab_support = st.tabs([
        "Account & Data", "Analysis Engine", "Analytics & Display", "Ingestion",
        "Anthropic API key", "Chesswright Pro", "Support",
    ])

    with tab_account:
        _render_account_data_tab()
    with tab_engine:
        _render_analysis_engine_tab()
    with tab_analytics:
        _render_analytics_display_tab()
    with tab_ingestion:
        _render_ingestion_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()
```

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add config.py tests/conftest.py tests/unit/test_config.py dashboard/settings_view.py
git commit -m "Add Ingestion behavior controls (variant policy, queue strategy) to Settings"
```

---

### Task 6: Advanced tier

**Files:**
- Modify: `config.py` (new `set_sync_setting`, `set_sync_chesscom_setting`; docstring update on `set_engine_setting`)
- Modify: `tests/conftest.py` (`config_yaml` fixture: add remaining keys)
- Modify: `tests/unit/test_config.py` (new test classes)
- Modify: `dashboard/settings_view.py` (new `_render_advanced_tab`, wired into `render()`)

**Interfaces:**
- Produces: `config.set_sync_setting(key, value, path=None)`, `config.set_sync_chesscom_setting(key, value, path=None)`.
- Consumes: existing `set_engine_setting`, `set_worker_setting`, `set_ingestion_setting` (Task 5) — reused for the fields already covered by those wrappers.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:

```python
@pytest.mark.unit
class TestSetSyncSettings:
    def test_sets_sync_timeout(self, config_yaml):
        config.set_sync_setting("request_timeout_seconds", 60, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["sync"]["request_timeout_seconds"] == 60

    def test_sets_sync_chesscom_timeout(self, config_yaml):
        config.set_sync_chesscom_setting("request_timeout_seconds", 45, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["sync_chesscom"]["request_timeout_seconds"] == 45
```

Extend the `config_yaml` fixture in `tests/conftest.py` with the remaining Advanced-tier sections/keys:

```python
        'worker:\n'
        '  consecutive_failure_limit: 3\n'
        '  commit_every_n_moves: 1\n'
        'ingestion:\n'
        '  variant_policy: skip\n'
        '  queue_strategy: interleaved_by_year\n'
        '  berserk_max_clock_fraction: 0.75\n'
        '  backlog_quota: 0.5\n'
        '  backlog_quota_window: 20\n'
        'sync:\n'
        '  request_timeout_seconds: 30\n'
        'sync_chesscom:\n'
        '  request_timeout_seconds: 30\n'
```

(This replaces the narrower `ingestion:` block Task 5 added — same two keys plus the three new ones, in the same section.) Also add `pv_max_len: 15` and `reuse_evals: true` under the existing `engine:` block:

```python
        'engine:\n'
        '  path: null\n'
        '  depth: 20\n'
        '  pv_max_len: 15\n'
        '  reuse_evals: true\n'
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestSetSyncSettings" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add the two new config.py wrappers, and widen `set_engine_setting`'s docstring**

```python
def set_sync_setting(key: str, value, path=None):
    """key: request_timeout_seconds -- the only scalar under sync: today."""
    _set_section_scalar("sync", key, value, path)


def set_sync_chesscom_setting(key: str, value, path=None):
    """key: request_timeout_seconds -- the only scalar under
    sync_chesscom: today."""
    _set_section_scalar("sync_chesscom", key, value, path)
```

Update `set_engine_setting`'s docstring (function body unchanged, `_set_section_scalar` already handles any key/value):

```python
def set_engine_setting(key: str, value, path=None):
    """key in {depth, multipv, threads, hash_mb, pv_max_len, reuse_evals}
    -- NOT path (see set_engine_path(), which needs quoting for Windows
    paths with spaces; these are all bare numbers/booleans)."""
    _set_section_scalar("engine", key, value, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_config.py -v`
Expected: all PASS (confirms Steps 1-4 plus no regression on the fixture extension for existing tests).

- [ ] **Step 5: Add the Advanced tab**

```python
def _render_advanced_tab():
    with st.expander("Advanced settings", expanded=False):
        st.caption(
            "Lower-level tuning knobs -- most of which config.yaml itself "
            "documents as safe defaults not worth changing. Shown here so "
            "they're not YAML-only, without pretending they're as commonly "
            "needed as the settings on the other tabs.")
        cfg = config.load_config()

        st.markdown("**Batch engine**")
        pv_max_len = st.number_input(
            "Stored line length (plies)", min_value=1, max_value=60, step=1,
            value=int(cfg["engine"]["pv_max_len"]), key="adv_pv_max_len",
            help="Plies of each line's continuation to store (storage vs. detail).")
        reuse_evals = st.checkbox(
            "Reuse a prior batch result for an exact-FEN repeat position",
            value=bool(cfg["engine"]["reuse_evals"]), key="adv_reuse_evals",
            help="Instead of re-running Stockfish. Unchecking restores the "
                 "old always-re-analyze behavior.")

        st.markdown("**Batch worker**")
        consecutive_failure_limit = st.number_input(
            "Stop after this many consecutive game failures", min_value=1,
            max_value=100, step=1,
            value=int(cfg["worker"]["consecutive_failure_limit"]),
            key="adv_consecutive_failure_limit",
            help="Stops the batch rather than silently failing the whole queue.")
        commit_every_n_moves = st.number_input(
            "Commit every N moves", min_value=1, max_value=100, step=1,
            value=int(cfg["worker"]["commit_every_n_moves"]),
            key="adv_commit_every_n_moves",
            help="1 (default) is safest -- a crash loses at most the "
                 "in-flight position. Not recommended to change.")

        st.markdown("**Ingestion queue fairness**")
        berserk_max_clock_fraction = st.number_input(
            "Berserk clock fraction", min_value=0.0, max_value=1.0, step=0.05,
            format="%.2f", value=float(cfg["ingestion"]["berserk_max_clock_fraction"]),
            key="adv_berserk_max_clock_fraction",
            help="A color is flagged berserk when its first clock reading "
                 "is at or below this fraction of the base time.")
        backlog_quota = st.number_input(
            "Backlog quota", min_value=0.0, max_value=1.0, step=0.05,
            format="%.2f", value=float(cfg["ingestion"]["backlog_quota"]),
            key="adv_backlog_quota",
            help="Minimum share of recently-analyzed games that must come "
                 "from the historical backlog, even while new synced games "
                 "are pending. 0 = recent games always win; 1 = backlog only.")
        backlog_quota_window = st.number_input(
            "Backlog quota window (games)", min_value=1, max_value=1000, step=1,
            value=int(cfg["ingestion"]["backlog_quota_window"]),
            key="adv_backlog_quota_window",
            help="How many of the most recently analyzed games the backlog "
                 "quota above looks at.")

        st.markdown("**Sync timeouts**")
        sync_timeout = st.number_input(
            "Lichess sync request timeout (s)", min_value=1, max_value=300, step=1,
            value=int(cfg["sync"]["request_timeout_seconds"]), key="adv_sync_timeout")
        sync_chesscom_timeout = st.number_input(
            "Chess.com sync request timeout (s)", min_value=1, max_value=300, step=1,
            value=int(cfg["sync_chesscom"]["request_timeout_seconds"]),
            key="adv_sync_chesscom_timeout")

        if st.button("Save advanced settings"):
            config.set_engine_setting("pv_max_len", int(pv_max_len))
            config.set_engine_setting("reuse_evals", bool(reuse_evals))
            config.set_worker_setting("consecutive_failure_limit", int(consecutive_failure_limit))
            config.set_worker_setting("commit_every_n_moves", int(commit_every_n_moves))
            config.set_ingestion_setting("berserk_max_clock_fraction", round(float(berserk_max_clock_fraction), 2))
            config.set_ingestion_setting("backlog_quota", round(float(backlog_quota), 2))
            config.set_ingestion_setting("backlog_quota_window", int(backlog_quota_window))
            config.set_sync_setting("request_timeout_seconds", int(sync_timeout))
            config.set_sync_chesscom_setting("request_timeout_seconds", int(sync_chesscom_timeout))
            st.toast("Advanced settings saved.", icon="✅")
            st.rerun()
```

Update `render()` in full to add `tab_advanced` (positioned between `tab_ingestion` and `tab_api`):

```python
def render():
    st.title("Settings")

    (tab_account, tab_engine, tab_analytics, tab_ingestion, tab_advanced,
     tab_api, tab_pro, tab_support) = st.tabs([
        "Account & Data", "Analysis Engine", "Analytics & Display", "Ingestion",
        "Advanced", "Anthropic API key", "Chesswright Pro", "Support",
    ])

    with tab_account:
        _render_account_data_tab()
    with tab_engine:
        _render_analysis_engine_tab()
    with tab_analytics:
        _render_analytics_display_tab()
    with tab_ingestion:
        _render_ingestion_tab()
    with tab_advanced:
        _render_advanced_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()
```

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add config.py tests/conftest.py tests/unit/test_config.py dashboard/settings_view.py
git commit -m "Add Advanced settings tier (engine/worker/ingestion-fairness/sync tuning)"
```

---

### Task 7: Engine Profiles (presets)

**Files:**
- Modify: `config.py` (new Engine Profiles section)
- Modify: `tests/conftest.py` (`config_yaml` fixture: add `multipv`/`threads`/`hash_mb` under `engine:`, `use_lichess_cloud_eval` under `interactive_engine:`)
- Modify: `tests/unit/test_config.py` (new test class)
- Modify: `dashboard/settings_view.py` (append to `_render_analysis_engine_tab`)

**Interfaces:**
- Produces: `config.save_engine_profile(name, path=None)`, `config.list_engine_profiles() -> list[str]`, `config.apply_engine_profile(name, path=None)`, `config.delete_engine_profile(name)`. Storage: `config.ENGINE_PROFILES_PATH` (`~/.chesswright/engine_profiles.yaml`), distinct from the existing `config.PROFILES_DIR` (Pro student profiles).
- Consumes: existing `config.set_engine_setting`, `config.save_interactive_engine`, `config.load_config`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:

```python
@pytest.mark.unit
class TestEngineProfiles:
    def test_save_and_list(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.save_engine_profile("Laptop", path=config_yaml)
        assert config.list_engine_profiles() == ["Laptop"]

    def test_apply_writes_back_engine_and_interactive_settings(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.set_engine_setting("depth", 30, path=config_yaml)
        config.save_engine_profile("Deep", path=config_yaml)
        config.set_engine_setting("depth", 14, path=config_yaml)
        config.apply_engine_profile("Deep", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["depth"] == 30

    def test_delete_removes_profile(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.save_engine_profile("Temp", path=config_yaml)
        config.delete_engine_profile("Temp")
        assert config.list_engine_profiles() == []

    def test_list_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        assert config.list_engine_profiles() == []
```

Extend the `config_yaml` fixture in `tests/conftest.py`'s `engine:`/`interactive_engine:` blocks:

```python
        'engine:\n'
        '  path: null\n'
        '  depth: 20\n'
        '  multipv: 3\n'
        '  threads: 4\n'
        '  hash_mb: 256\n'
        '  pv_max_len: 15\n'
        '  reuse_evals: true\n'
        'interactive_engine:\n'
        '  threads: 1\n'
        '  hash_mb: 32\n'
        '  time_sec: 0.5\n'
        '  depth: 20\n'
        '  store_threshold: 20\n'
        '  use_lichess_cloud_eval: true\n'
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestEngineProfiles" -v`
Expected: FAIL with `AttributeError: module 'config' has no attribute 'ENGINE_PROFILES_PATH'`.

- [ ] **Step 3: Add the Engine Profiles section to `config.py`**

Add after the existing `set_engine_path` function (end of the file):

```python
# ---------------------------------------------------------------------------
# Engine Profiles -- named snapshots of engine.*/interactive_engine.* only
# (batch depth/multipv/threads/hash_mb + all interactive_engine fields).
# Distinct from the Pro profile machinery above (PROFILES_DIR/list_profiles/
# initialize_profile/remove_profile), which snapshots a whole separate
# student database + config -- these are just speed/depth presets like
# "Laptop" vs "Deep Analysis", stored in one small YAML file, not a
# directory per profile.
# ---------------------------------------------------------------------------

ENGINE_PROFILES_PATH = CHESSWRIGHT_DIR / "engine_profiles.yaml"

_ENGINE_PROFILE_FIELDS = {
    "engine": ["depth", "multipv", "threads", "hash_mb"],
    "interactive_engine": ["time_sec", "depth", "threads", "hash_mb",
                            "store_threshold", "use_lichess_cloud_eval"],
}


def _load_engine_profiles() -> dict:
    if not ENGINE_PROFILES_PATH.exists():
        return {}
    with open(ENGINE_PROFILES_PATH) as f:
        return yaml.safe_load(f) or {}


def save_engine_profile(name: str, path=None) -> None:
    """Snapshots the CURRENT engine.*/interactive_engine.* values (from
    the live config, or *path* if given) under *name*. Overwrites any
    existing profile of the same name."""
    cfg = load_config(path)
    snapshot = {}
    for section, keys in _ENGINE_PROFILE_FIELDS.items():
        for key in keys:
            snapshot[f"{section}.{key}"] = cfg[section][key]
    profiles = _load_engine_profiles()
    profiles[name] = snapshot
    CHESSWRIGHT_DIR.mkdir(exist_ok=True)
    ENGINE_PROFILES_PATH.write_text(yaml.dump(profiles, default_flow_style=False))


def list_engine_profiles() -> list[str]:
    return sorted(_load_engine_profiles().keys())


def apply_engine_profile(name: str, path=None) -> None:
    """Writes a saved profile's engine.*/interactive_engine.* values back
    into config.yaml (or *path*) in one action. Raises KeyError if *name*
    doesn't exist."""
    snapshot = _load_engine_profiles()[name]
    engine_settings = {}
    interactive_settings = {}
    for dotted_key, value in snapshot.items():
        section, key = dotted_key.split(".", 1)
        if section == "engine":
            engine_settings[key] = value
        else:
            interactive_settings[key] = value
    for key, value in engine_settings.items():
        set_engine_setting(key, value, path=path)
    save_interactive_engine(interactive_settings, path=path)


def delete_engine_profile(name: str) -> None:
    profiles = _load_engine_profiles()
    profiles.pop(name, None)
    ENGINE_PROFILES_PATH.write_text(yaml.dump(profiles, default_flow_style=False))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestEngineProfiles" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Add the Engine Profiles UI**

Append to `_render_analysis_engine_tab()` in `dashboard/settings_view.py`, after the existing Live Engine form's `if save_btn:` block:

```python
    st.divider()
    st.subheader("Engine Profiles")
    st.caption(
        "Save your current engine speed/depth settings under a name you "
        "choose, and switch between them later -- e.g. 'Laptop' vs. "
        "'Desktop' vs. 'Deep Analysis'. Not the same as Chesswright Pro's "
        "student profiles further down this page, which are separate "
        "databases for different players.")

    profile_names = config.list_engine_profiles()
    col1, col2 = st.columns(2)
    with col1:
        new_profile_name = st.text_input("Save current settings as…",
                                          key="new_engine_profile_name")
        if st.button("Save profile") and new_profile_name.strip():
            config.save_engine_profile(new_profile_name.strip())
            st.success(f"Saved profile '{new_profile_name.strip()}'.")
            st.rerun()
    with col2:
        if profile_names:
            selected_profile = st.selectbox("Saved profiles", profile_names,
                                             key="selected_engine_profile")
            apply_col, delete_col = st.columns(2)
            if apply_col.button("Apply", key="apply_engine_profile"):
                config.apply_engine_profile(selected_profile)
                live_engine.get_engine_service.clear()
                st.success(f"Applied '{selected_profile}'.")
                st.rerun()
            confirm_delete = delete_col.checkbox(
                "Confirm delete", key="confirm_delete_engine_profile")
            if delete_col.button("Delete", key="delete_engine_profile",
                                  disabled=not confirm_delete):
                config.delete_engine_profile(selected_profile)
                st.success(f"Deleted '{selected_profile}'.")
                st.rerun()
        else:
            st.caption("No saved profiles yet.")
```

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Manual smoke check**

Launch the app, go to Settings → Analysis Engine, save a profile, change a value, click Apply, confirm the value reverts; confirm Delete is disabled until "Confirm delete" is checked.

- [ ] **Step 8: Commit**

```bash
git add config.py tests/conftest.py tests/unit/test_config.py dashboard/settings_view.py
git commit -m "Add Engine Profiles presets (roadmap's Laptop/Desktop/Deep Analysis/Tournament Mode concept)"
```

---

### Task 8: Reset-to-defaults safeguard

**Files:**
- Modify: `config.py` (new `reset_engine_path`)
- Modify: `tests/unit/test_config.py` (new test)
- Modify: `dashboard/settings_view.py` (`_render_analysis_engine_tab`, `_render_analytics_display_tab`, `_render_ingestion_tab`)

**Interfaces:**
- Produces: `config.reset_engine_path(path=None)` — clears `engine.path` back to the bare YAML `null` literal (distinct from `set_engine_path`, which always quotes a real path string and would otherwise write the literal string `"None"`).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:

```python
@pytest.mark.unit
class TestResetEnginePath:
    def test_clears_back_to_null(self, config_yaml):
        config.set_engine_path("/usr/bin/stockfish", path=config_yaml)
        config.reset_engine_path(path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["path"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestResetEnginePath" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add `reset_engine_path` to `config.py`**

```python
def reset_engine_path(path=None) -> None:
    """Clears engine.path back to null (auto-detect) -- the Settings
    page's 'Reset to defaults' action for the Engine location control.
    Distinct from set_engine_path() (which always quotes a real path
    string) since null must render as the bare YAML null literal, not
    the string "None"."""
    _set_section_scalar("engine", "path", None, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_config.py -k "TestResetEnginePath" -v`
Expected: PASS.

- [ ] **Step 5: Add the three Reset-to-defaults buttons**

In `_render_analysis_engine_tab()`, add at the end of the function (after the Engine Profiles block from Task 7):

```python
    st.divider()
    if st.button("Reset engine settings to defaults", key="reset_engine_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.reset_engine_path()
        config.save_interactive_engine(template_cfg["interactive_engine"])
        live_engine.get_engine_service.clear()
        st.success("Engine settings reset to defaults.")
        st.rerun()
```

In `_render_analytics_display_tab()`, add at the end:

```python
    st.divider()
    if st.button("Reset analytics & display settings to defaults", key="reset_analytics_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.set_analytics_setting("utc_offset_hours", template_cfg["analytics"]["utc_offset_hours"])
        config.set_analytics_setting("min_sample_size", template_cfg["analytics"]["min_sample_size"])
        st.cache_data.clear()
        st.success("Analytics & Display settings reset to defaults.")
        st.rerun()
```

In `_render_ingestion_tab()`, add at the end:

```python
    st.divider()
    if st.button("Reset ingestion settings to defaults", key="reset_ingestion_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.set_ingestion_setting("variant_policy", template_cfg["ingestion"]["variant_policy"])
        config.set_ingestion_setting("queue_strategy", template_cfg["ingestion"]["queue_strategy"])
        st.success("Ingestion settings reset to defaults.")
        st.rerun()
```

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Manual smoke check**

Change each of the three tabs' values away from their defaults, click each Reset button, confirm values revert to what's in the repo's own `config.yaml`.

- [ ] **Step 8: Commit**

```bash
git add config.py tests/unit/test_config.py dashboard/settings_view.py
git commit -m "Add Reset-to-defaults to each Common-tier tab"
```

---

### Task 9: Settings search / jump

**Files:**
- Modify: `dashboard/settings_view.py` (new `_SETTINGS_INDEX`, `_render_search_box`, `render()`, and a `highlight_field=None` parameter on `_render_account_data_tab`/`_render_analysis_engine_tab`/`_render_analytics_display_tab`/`_render_ingestion_tab`)
- Create: additions to `tests/unit/test_settings_view.py`

**Interfaces:**
- Produces: `_rank_settings_matches(query: str, limit: int = 5) -> list[tuple[str, str]]` — pure function, `(tab_label, field_label)` pairs, ranked by `rapidfuzz`. Kept separate from the Streamlit button-rendering loop so it's unit-testable without `AppTest`.

- [ ] **Step 1: Write the failing test for the pure ranking function**

Add to `tests/unit/test_settings_view.py`:

```python
@pytest.mark.unit
class TestRankSettingsMatches:
    def test_finds_timezone_by_partial_word(self):
        matches = settings_view._rank_settings_matches("timezone")
        labels = [label for _tab, label in matches]
        assert "Local timezone" in labels

    def test_finds_engine_location_by_keyword(self):
        matches = settings_view._rank_settings_matches("stockfish")
        labels = [label for _tab, label in matches]
        assert "Engine location" in labels

    def test_no_match_returns_empty(self):
        matches = settings_view._rank_settings_matches("zzzznonsense")
        assert matches == []

    def test_respects_limit(self):
        matches = settings_view._rank_settings_matches("settings", limit=2)
        assert len(matches) <= 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_settings_view.py -k "TestRankSettingsMatches" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add the index and ranking function to `dashboard/settings_view.py`**

```python
_SETTINGS_INDEX = [
    ("Account & Data", "Anthropic API key", "api key claude narrative commentary"),
    ("Account & Data", "Import an existing database", "database import migrate"),
    ("Account & Data", "Chess.com account", "chesscom sync"),
    ("Analysis Engine", "Engine location", "stockfish engine path detect browse"),
    ("Analysis Engine", "Live engine settings", "interactive engine depth threads hash time"),
    ("Analysis Engine", "Engine Profiles", "preset laptop desktop deep analysis tournament"),
    ("Analytics & Display", "Local timezone", "utc offset hour time of day"),
    ("Analytics & Display", "Confidence threshold", "sample size min games confidence"),
    ("Ingestion", "Non-standard variants", "chess960 atomic variant policy"),
    ("Ingestion", "Analysis queue order", "queue strategy interleaved chronological"),
    ("Advanced", "Advanced settings", "pv_max_len reuse_evals worker sync timeout"),
    ("Anthropic API key", "Anthropic API key", "api key claude"),
    ("Chesswright Pro", "Chesswright Pro", "license coach mode student profile"),
    ("Support", "Support this project", "sponsor donate"),
]


def _rank_settings_matches(query: str, limit: int = 5) -> list[tuple[str, str]]:
    """Ranks _SETTINGS_INDEX entries against *query* by label+keywords,
    returning (tab_label, field_label) pairs, best match first. Pure
    function (no Streamlit calls) so it's unit-testable without AppTest."""
    from rapidfuzz import process, fuzz
    candidates = [f"{label} {keywords}" for _tab, label, keywords in _SETTINGS_INDEX]
    ranked = process.extract(query, candidates, scorer=fuzz.WRatio,
                              limit=limit, score_cutoff=40)
    return [(_SETTINGS_INDEX[idx][0], _SETTINGS_INDEX[idx][1]) for _text, _score, idx in ranked]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_settings_view.py -k "TestRankSettingsMatches" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire the search box and tab-jump into `render()`**

```python
def _render_search_box():
    query = st.text_input("🔍 Search settings", key="settings_search_query",
                           placeholder="e.g. timezone, engine, confidence…")
    if not query.strip():
        return
    matches = _rank_settings_matches(query)
    if not matches:
        st.caption("No matching settings found.")
        return
    st.caption("Jump to:")
    for i, (tab, label) in enumerate(matches):
        if st.button(f"{label}  (in {tab})", key=f"settings_search_jump_{i}"):
            st.session_state["settings_active_tab"] = tab
            st.session_state["settings_jump_field"] = label
            st.rerun()


def render():
    st.title("Settings")
    _render_search_box()

    jump_tab = st.session_state.get("settings_active_tab")
    jump_field = st.session_state.get("settings_jump_field")
    tab_labels = [
        "Account & Data", "Analysis Engine", "Analytics & Display", "Ingestion",
        "Advanced", "Anthropic API key", "Chesswright Pro", "Support",
    ]
    if jump_tab:
        st.session_state["settings_tabs_active"] = jump_tab

    (tab_account, tab_engine, tab_analytics, tab_ingestion, tab_advanced,
     tab_api, tab_pro, tab_support) = st.tabs(tab_labels, key="settings_tabs_active")

    with tab_account:
        _render_account_data_tab(jump_field if jump_tab == "Account & Data" else None)
    with tab_engine:
        _render_analysis_engine_tab(jump_field if jump_tab == "Analysis Engine" else None)
    with tab_analytics:
        _render_analytics_display_tab(jump_field if jump_tab == "Analytics & Display" else None)
    with tab_ingestion:
        _render_ingestion_tab(jump_field if jump_tab == "Ingestion" else None)
    with tab_advanced:
        _render_advanced_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()

    st.session_state.pop("settings_active_tab", None)
    st.session_state.pop("settings_jump_field", None)
```

Add a `highlight_field=None` parameter to each of the four functions this touches. This changes exactly the `def` line plus inserts exactly one two-line `if` block as the very first lines inside each function — every other line of each function (already fully written out in Tasks 1/2/3/5) stays byte-for-byte the same. The four exact edits:

In `_render_account_data_tab()` (Task 1): change `def _render_account_data_tab():` to `def _render_account_data_tab(highlight_field=None):`, and insert as the new first two lines of the function body, immediately before `st.subheader("Import an existing database")`:

```python
    if highlight_field:
        st.info(f"🔍 Jumped here for: **{highlight_field}**")
```

In `_render_analysis_engine_tab()` (Task 1, extended by Tasks 2/7/8): change `def _render_analysis_engine_tab():` to `def _render_analysis_engine_tab(highlight_field=None):`, and insert the same two-line block immediately before `st.subheader("Engine location")`.

In `_render_analytics_display_tab()` (Task 3, extended by Tasks 4/8): change `def _render_analytics_display_tab():` to `def _render_analytics_display_tab(highlight_field=None):`, and insert the same two-line block immediately before `st.subheader("Local timezone")`.

In `_render_ingestion_tab()` (Task 5, extended by Task 8): change `def _render_ingestion_tab():` to `def _render_ingestion_tab(highlight_field=None):`, and insert the same two-line block immediately before `st.subheader("New game ingestion")`.

`_render_advanced_tab()`, `_render_api_key_tab()`, `_render_pro_section()`, `_render_support_section()` are not touched by this task — they have no Common-tier fields to jump to, so `render()` (Step 5 above) calls them with no `highlight_field` argument.

- [ ] **Step 6: Run the page-render smoke test**

Run: `.venv/bin/pytest tests/ui/test_pages.py -k "settings_view" -v`
Expected: PASS.

- [ ] **Step 7: Manual smoke check**

Launch the app, go to Settings, type "timezone" in the search box, click the resulting "Local timezone (in Analytics & Display)" button, confirm the page jumps to that tab and shows the "🔍 Jumped here for" callout.

- [ ] **Step 8: Commit**

```bash
git add dashboard/settings_view.py tests/unit/test_settings_view.py
git commit -m "Add Settings search/jump box"
```

---

### Task 10: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: same pre-existing-failure count as the checklist's own baseline (3 unrelated, pre-existing failures — confirm no new failures were introduced by any task in this plan).

- [ ] **Step 2: Run the `verify-live-dashboard` skill against the real dev DB**

Invoke the `verify-live-dashboard` skill to launch a scratch copy of the dashboard against the real dev `chess.db` and screenshot the Settings page's 8 tabs, confirming: all tabs render with real data, the timezone control changes the Patterns & Tendencies heatmap's hour labels, the confidence threshold control changes which rows appear as "small sample" on at least one page (e.g. Matchups' Nemesis Opponents), an Engine Profile round-trips (save → change → apply → confirm reverted), and the search box's jump-to-tab works.

- [ ] **Step 3: Fix anything the live pass surfaces**

If the live pass finds a real bug, fix it with its own small test-first cycle (write the regression test, watch it fail, fix, watch it pass) before moving to Step 4 — do not commit an unverified "fix."

- [ ] **Step 4: Final commit (only if Step 3 produced changes)**

```bash
git add -A
git commit -m "Fix issues found during live verification of the Phase 6 Settings work"
```
