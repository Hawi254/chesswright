"""
Settings page -- the bring-your-own Anthropic API key entry point
(BRIEF.md S3). This is the new project's equivalent of the original
project's "set ANTHROPIC_API_KEY and restart" rule, adapted for an
installer who isn't assumed to be comfortable with environment
variables or a terminal at all.
"""
import streamlit as st

import api_key_store


def render():
    st.title("Settings")

    st.subheader("Anthropic API key")
    st.caption(
        "Optional. Powers the on-demand 'richer narrative' / commentary "
        "buttons throughout the app (game stories, opening and opponent "
        "commentary). Everything else works without one -- this only "
        "unlocks the Claude-API extras. You pay for your own usage "
        "directly through your own Anthropic account; this app never "
        "sends your key anywhere except Anthropic's API.")

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
        col1, col2 = st.columns(2)
        save_clicked = col1.form_submit_button("Save key")
        clear_clicked = col2.form_submit_button("Remove saved key")

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

    if clear_clicked:
        api_key_store.clear_api_key()
        st.success("Saved key removed.")
        st.rerun()
