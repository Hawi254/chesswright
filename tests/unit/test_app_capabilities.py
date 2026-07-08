"""Regression guard for dashboard/app_capabilities.py's PAGE_CAPABILITIES
registry: it exists to ground AI Coach's (both tiers') page/capability
claims in the real app, so it must never silently drift from the real
`st.Page(...)` list in dashboard/app.py. This test parses the real
url_path values out of app.py via a simple regex (every st.Page(...) call
in that file is written with an explicit `url_path="..."` kwarg, on the
same statement) and asserts the registry matches exactly, both ways.
"""
import pathlib
import re

import pytest

import app_capabilities

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
APP_PY = REPO_ROOT / "dashboard" / "app.py"

_URL_PATH_RE = re.compile(r'st\.Page\(.*?url_path=["\'](?P<url_path>[\w-]+)["\']', re.DOTALL)


def _real_url_paths() -> set[str]:
    """Every url_path="..." that appears inside an st.Page(...) call in
    app.py, found by matching from each `st.Page(` up through its first
    url_path= kwarg (non-greedy across newlines, since several of these
    calls span multiple lines)."""
    source = APP_PY.read_text()
    return set(_URL_PATH_RE.findall(source))


@pytest.mark.unit
class TestPageCapabilitiesRegistry:
    def test_every_registry_entry_is_a_real_page(self):
        real_paths = _real_url_paths()
        registry_paths = {p["url_path"] for p in app_capabilities.PAGE_CAPABILITIES}
        missing_from_app = registry_paths - real_paths
        assert not missing_from_app, (
            f"PAGE_CAPABILITIES references url_path(s) not found in app.py: "
            f"{missing_from_app}"
        )

    def test_every_real_page_is_in_the_registry(self):
        real_paths = _real_url_paths()
        registry_paths = {p["url_path"] for p in app_capabilities.PAGE_CAPABILITIES}
        missing_from_registry = real_paths - registry_paths
        assert not missing_from_registry, (
            f"app.py has st.Page url_path(s) missing from PAGE_CAPABILITIES: "
            f"{missing_from_registry}"
        )

    def test_sanity_real_paths_found_at_all(self):
        # Guards against the regex silently matching nothing if app.py's
        # st.Page() call style ever changes shape.
        assert len(_real_url_paths()) >= 15

    def test_no_duplicate_url_paths_in_registry(self):
        paths = [p["url_path"] for p in app_capabilities.PAGE_CAPABILITIES]
        assert len(paths) == len(set(paths))

    def test_every_entry_has_required_keys_and_nonempty_values(self):
        for entry in app_capabilities.PAGE_CAPABILITIES:
            assert set(entry.keys()) == {"title", "url_path", "capability"}
            assert entry["title"].strip()
            assert entry["url_path"].strip()
            assert entry["capability"].strip()


@pytest.mark.unit
class TestFormatCapabilitiesBlock:
    def test_one_line_per_page(self):
        block = app_capabilities.format_capabilities_block()
        lines = block.splitlines()
        assert len(lines) == len(app_capabilities.PAGE_CAPABILITIES)

    def test_line_format(self):
        block = app_capabilities.format_capabilities_block()
        first_line = block.splitlines()[0]
        first_entry = app_capabilities.PAGE_CAPABILITIES[0]
        assert first_line == f"- {first_entry['title']}: {first_entry['capability']}"

    def test_accepts_custom_list(self):
        custom = [{"title": "X", "url_path": "x", "capability": "does x"}]
        assert app_capabilities.format_capabilities_block(custom) == "- X: does x"
