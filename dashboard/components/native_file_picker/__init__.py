"""Python wrapper for the native file-picker Streamlit component.

Renders a "Browse..." button that opens a real native OS file dialog
when running inside the packaged desktop app (pywebview) -- see
frontend/index.html for the mechanism (pywebview's js_api, reachable
from this component's iframe even though it's served by the separate
Streamlit server subprocess, live-verified in BRIEF.md's §6h Tier 2
investigation). Stays hidden with zero footprint when pywebview isn't
present (the plain `streamlit run` dev workflow, or a browser tab) --
callers must keep their existing fallback widget (st.text_input /
st.file_uploader) for that case, this never replaces it.
"""
import os
import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_component_func = components.declare_component("native_file_picker", path=_FRONTEND_DIR)


def pick(kind: str, label: str = "Browse…", key: str = None) -> str | None:
    """Returns the picked path once the user chooses one, else None --
    covering both "not clicked yet" and "no native dialog available
    here" identically, so callers can just fall back to their existing
    widget whenever this returns None.

    kind: "engine" or "database" -- selects which desktop_app.py js_api
    method gets called (pick_engine_file / pick_database_file). Each of
    those hardcodes its own dialog filter server-side in the launcher
    process; nothing about the dialog type is chosen from here.
    """
    if kind not in ("engine", "database"):
        raise ValueError(f"unknown native_file_picker kind: {kind!r}")
    return _component_func(kind=kind, label=label, key=key, default=None)
