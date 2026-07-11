"""Unit tests for dashboard/_common.py's roadmap §28 navigation helpers:
render_where_next (bottom-of-page cross-link panel) and the
persist_filter/restore_filter_default pair (filter persistence across
st.navigation page switches -- see _common.py's own docstrings for why
these are needed: keyed widget session_state does NOT survive a
page-away-and-back in this app, confirmed live 2026-07-11).

Uses streamlit.testing.v1.AppTest.from_string with tiny inline scripts --
same harness tests/ui/test_pages.py uses for full page renders, just
scoped down to the three helpers themselves rather than a whole view
module. A real ScriptRunContext is required for st.session_state and
widget calls (st.button/st.columns) to work at all, so plain
monkeypatching of st.session_state as a dict isn't an option here.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

from streamlit.testing.v1 import AppTest


def _run(script: str) -> AppTest:
    at = AppTest.from_string(script)
    at.run(timeout=30)
    assert not at.exception, f"script raised: {at.exception}"
    return at


@pytest.mark.unit
class TestPersistFilter:
    def test_mirrors_current_value_into_persist_key(self):
        at = _run(
            "import streamlit as st\n"
            "from _common import persist_filter\n"
            "st.session_state['mykey'] = 'hello'\n"
            "persist_filter('mykey')\n"
        )
        assert at.session_state["_persist_mykey"] == "hello"


@pytest.mark.unit
class TestRestoreFilterDefault:
    def test_seeds_from_mirror_when_key_absent(self):
        # Simulates the nav-away-and-back case: the widget key was
        # garbage-collected by st.navigation, but the plain mirror entry
        # (never a widget key itself) survived.
        at = _run(
            "import streamlit as st\n"
            "from _common import restore_filter_default\n"
            "st.session_state['_persist_k'] = 'mirrored'\n"
            "restore_filter_default('k', 'fallback')\n"
        )
        assert at.session_state["k"] == "mirrored"

    def test_uses_fallback_when_no_mirror_present(self):
        at = _run(
            "import streamlit as st\n"
            "from _common import restore_filter_default\n"
            "restore_filter_default('k', 'fallback')\n"
        )
        assert at.session_state["k"] == "fallback"

    def test_does_not_clobber_a_key_already_present_this_run(self):
        # e.g. the widget's own rerun already set session_state[key] --
        # must win over a stale mirror value.
        at = _run(
            "import streamlit as st\n"
            "from _common import restore_filter_default\n"
            "st.session_state['k'] = 'current'\n"
            "st.session_state['_persist_k'] = 'mirrored'\n"
            "restore_filter_default('k', 'fallback')\n"
        )
        assert at.session_state["k"] == "current"


@pytest.mark.unit
class TestRenderWhereNext:
    def test_skips_none_targets(self):
        at = _run(
            "import streamlit as st\n"
            "from _common import render_where_next\n"
            "render_where_next([('A', None), ('B', 'target_b')])\n"
        )
        labels = [b.label for b in at.button]
        assert labels == ["B"]

    def test_skips_rendering_entirely_when_all_targets_are_none(self):
        at = _run(
            "import streamlit as st\n"
            "from _common import render_where_next\n"
            "render_where_next([('A', None), ('B', None)])\n"
        )
        assert list(at.button) == []
        assert list(at.subheader) == []
        assert list(at.divider) == []

    def test_renders_one_button_per_live_link_with_correct_labels(self):
        at = _run(
            "import streamlit as st\n"
            "from _common import render_where_next\n"
            "render_where_next([('First', 'p1'), ('Second', 'p2')])\n"
        )
        labels = [b.label for b in at.button]
        assert labels == ["First", "Second"]
        assert [s.value for s in at.subheader] == ["Where next?"]
