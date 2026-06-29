"""Python wrapper for the interactive chessboard Streamlit component."""
import os
import streamlit.components.v1 as components

_FRONTEND_BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "build")
_component_func = components.declare_component("chessboard", path=_FRONTEND_BUILD)


def render(fen: str, orientation: str = "white", arrows: list = None,
           interactive: bool = False, lastmove_from: str = None,
           lastmove_to: str = None, key: str = None) -> dict | None:
    """Render an interactive chess board.

    Returns {uci, fen, san} when the user makes a move, None otherwise.
    arrows: list of {from, to, color} dicts.
    """
    return _component_func(
        fen=fen,
        orientation=orientation,
        arrows=arrows or [],
        interactive=interactive,
        lastmove_from=lastmove_from,
        lastmove_to=lastmove_to,
        key=key,
        default=None,
    )
