"""
Bring-your-own Anthropic API key storage (BRIEF.md S3). The original
personal project read ANTHROPIC_API_KEY from an environment variable
only -- right for one technical user running everything from a
terminal, wrong for an installer of a packaged desktop app who isn't
assumed to know what an environment variable is.

Storage precedence, checked in this order:
1. The OS-native credential store, via `keyring` (macOS Keychain,
   Windows Credential Manager, Linux Secret Service/libsecret). The
   default and recommended path.
2. A local plaintext fallback file (~/.chesswright/api_key.txt),
   used ONLY when keyring has no working backend (e.g. a minimal/
   headless Linux install with no Secret Service running) --
   confirmed by actually trying a keyring round-trip, not guessed at
   from the platform name. Every caller that reads from this fallback
   must surface that it's the less-secure path; see
   using_secure_backend().
3. The ANTHROPIC_API_KEY environment variable, lowest priority --
   kept for technical users/CI/testing, not the primary path for a
   packaged install.

Never logged, never written anywhere else.
"""
import os
import pathlib

import keyring
import keyring.errors

SERVICE_NAME = "chesswright"
KEY_NAME = "anthropic_api_key"

FALLBACK_DIR = pathlib.Path.home() / ".chesswright"
FALLBACK_PATH = FALLBACK_DIR / "api_key.txt"

# Cached result of the keyring round-trip probe, module-level so it's computed
# once per process (i.e. once per app restart) rather than on every Streamlit
# rerun -- a live probe touches the OS credential store (e.g. KWallet), which
# can reprompt for a wallet password each time it's called.
_backend_works_cache = None


def _keyring_backend_works():
    """Round-trip a throwaway value rather than trusting keyring.get_keyring()'s
    class name -- the real failure mode (no Secret Service daemon running) only
    shows up when you actually try to use it, confirmed by testing this exact
    case, not assumed from the platform alone."""
    global _backend_works_cache
    if _backend_works_cache is not None:
        return _backend_works_cache

    probe = "chesswright-backend-probe"
    try:
        keyring.set_password(SERVICE_NAME, probe, "ok")
        keyring.delete_password(SERVICE_NAME, probe)
        _backend_works_cache = True
    except keyring.errors.KeyringError:
        _backend_works_cache = False
    return _backend_works_cache


def using_secure_backend():
    """True if a working OS credential store is available. The Settings
    page should show an explicit warning when this is False and a key is
    stored via the plaintext fallback instead."""
    return _keyring_backend_works()


def get_api_key():
    """Returns the stored key, or None if none is configured anywhere."""
    try:
        value = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if value:
            return value
    except keyring.errors.KeyringError:
        pass

    if FALLBACK_PATH.exists():
        value = FALLBACK_PATH.read_text().strip()
        if value:
            return value

    return os.environ.get("ANTHROPIC_API_KEY") or None


def set_api_key(value):
    """Stores the key via keyring if a working backend exists, otherwise
    writes the plaintext fallback file. Returns True if stored securely
    (keyring), False if the less-secure fallback was used -- the caller
    (the Settings page) is responsible for telling the user which
    happened, not this function."""
    value = value.strip()
    if _keyring_backend_works():
        keyring.set_password(SERVICE_NAME, KEY_NAME, value)
        # Clear any stale plaintext fallback so the key only lives in one
        # place once a secure backend is confirmed working.
        if FALLBACK_PATH.exists():
            FALLBACK_PATH.unlink()
        return True

    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_PATH.write_text(value)
    FALLBACK_PATH.chmod(0o600)
    return False


def clear_api_key():
    try:
        keyring.delete_password(SERVICE_NAME, KEY_NAME)
    except keyring.errors.KeyringError:
        pass
    if FALLBACK_PATH.exists():
        FALLBACK_PATH.unlink()
