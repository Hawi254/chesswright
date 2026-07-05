"""Thin Pro-license gate used throughout the dashboard.

Pro features check is_pro_active() before rendering. If the chesswright_pro
package is not installed, or is installed but no key has been activated,
returns False and callers show an upsell nudge instead of the feature.
"""


def is_pro_active() -> bool:
    """Return True if Chesswright Pro is installed and a valid license key is active."""
    try:
        from chesswright_pro import license as _lic  # type: ignore[import]
        return bool(_lic.get_license_key())
    except (ImportError, Exception):
        return False
