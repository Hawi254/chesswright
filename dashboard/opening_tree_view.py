"""Interactive Opening Repertoire Tree — Pro feature gate.

The actual tree implementation (Explorer, What Changed, Tree Overview)
lives in the private chesswright_pro package
(chesswright_pro/opening_tree.py) — this file only holds the title, the
free-tier upsell, and the gate check, so the public core repo never
ships the feature's actual source, only the fact that it exists.
"""
import streamlit as st

import pro_gate


def render() -> None:
    st.title("Opening Repertoire Tree")

    if not pro_gate.is_pro_active():
        st.info(
            "**Opening Repertoire Tree** is a Chesswright Pro feature.\n\n"
            "Navigate your opening repertoire as an interactive position tree. "
            "See exactly what you've played from each position, with win rates "
            "and accuracy scores at every branch — then push weak positions "
            "straight into your SRS drill queue.\n\n"
            "Upgrade to Pro to unlock this feature."
        )
        return

    try:
        from chesswright_pro import opening_tree
    except ImportError:
        st.error(
            "Pro is licensed but the chesswright_pro package couldn't be "
            "imported. Try reinstalling it."
        )
        return
    opening_tree.render()
