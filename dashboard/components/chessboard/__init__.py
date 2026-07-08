"""Python wrapper for the interactive chessboard Streamlit component."""
import os
import streamlit.components.v1 as components

_FRONTEND_BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "build")
_component_func = components.declare_component("chessboard", path=_FRONTEND_BUILD)


def render(fen: str, orientation: str = "white", arrows: list = None,
           highlighted_squares: list = None,
           interactive: bool = False, lastmove_from: str = None,
           lastmove_to: str = None, enable_keyboard_nav: bool = False,
           key: str = None) -> dict | None:
    """Render an interactive chess board.

    Returns None, or a dict tagged by "type":
      {"type": "move", "uci", "fen", "san", "nonce"} -- the user completed a
        move (click/drag, or a promotion pick).
      {"type": "nav", "direction": "prev"|"next", "nonce"} -- the user
        pressed Left/Right arrow. Only ever returned when
        enable_keyboard_nav=True; callers that don't pass it will never see
        this shape. Callers MUST check "type" before reading move-specific
        keys ("fen" is absent on a nav result).

    "nonce" is a per-mount, monotonically increasing int stamped on every
    emitted value. A Streamlit custom component keeps re-returning its last
    emitted value on every subsequent script rerun until it sends a new one
    -- callers that need to act on a value exactly once (not on every
    rerun that happens to see it) should compare "nonce" against the last
    one they processed (e.g. in session_state) rather than giving the board
    a position-dependent `key` to force a remount, which is what used to
    cause a visible flash (the iframe fully unmounting and remounting) on
    every move/nav. Use a stable `key` (per game/position-tree, not per
    ply/step) and dedupe on "nonce" instead.

    arrows: list of {from, to, color} dicts.
    highlighted_squares: list of {"square": ..., "color": ...} dicts, e.g.
        {"square": "e4", "color": "#B0584F"}. Colors are pre-resolved by
        the caller (a style-enum -> theme-color mapping happens in
        chesswright_pro/board_chat.py, never in this component) -- same
        convention `arrows` already uses (callers pass a resolved `color`
        string, never a style keyword the component would need to
        interpret).
    enable_keyboard_nav: also grabs keyboard focus on mount and listens for
        Left/Right arrow keys -- only turn on where the caller actually has
        a fixed move sequence to step through (see game_detail_view.py).
    """
    return _component_func(
        fen=fen,
        orientation=orientation,
        arrows=arrows or [],
        highlighted_squares=highlighted_squares or [],
        interactive=interactive,
        lastmove_from=lastmove_from,
        lastmove_to=lastmove_to,
        enable_keyboard_nav=enable_keyboard_nav,
        key=key,
        default=None,
    )
