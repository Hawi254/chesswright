"""SRS Drill Mode — Pro feature gate.

The actual drill implementation (in-app spaced-repetition sessions over
positions from the player's game history) lives in the private
chesswright_pro package (chesswright_pro/srs_drills.py) — this file only
holds the title, the free-tier upsell, and the gate check, so the public
core repo never ships the feature's actual source, only the fact that it
exists.
"""
import streamlit as st

import pro_gate


def render() -> None:
    st.title("SRS Drills")
    st.caption("Spaced-repetition drills: positions from your own games, re-shown "
               "at growing intervals as you get them right — the same system "
               "flashcard apps use to make things stick.")

    if not pro_gate.is_pro_active():
        st.info(
            "**SRS Drill Mode** is a Chesswright Pro feature. "
            "Practice your mistake positions on an adaptive spaced-repetition "
            "schedule — so the positions you keep blundering come back sooner, "
            "and the ones you've mastered fade into the background.\n\n"
            "Upgrade to Pro to unlock in-app drilling."
        )
        return

    try:
        from chesswright_pro import srs_drills
    except ImportError:
        st.error(
            "Pro is licensed but the chesswright_pro package couldn't be "
            "imported. Try reinstalling it."
        )
        return
    srs_drills.render()
