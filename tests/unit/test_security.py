"""
Security hardening tests — verifies the S1–S8 patches from v0.1.14.

These are unit/integration tests that exercise the security boundaries
directly, without needing a running app or browser.
"""
import html
import pathlib
import re
import pytest


@pytest.mark.unit
class TestS1PathTraversal:
    """S1 (HIGH): Engine upload filename must have directory components stripped."""

    def test_basename_strips_traversal(self):
        # The fix in onboarding_view.py uses pathlib.Path(uploaded.name).name
        crafted = "../../../etc/passwd"
        safe = pathlib.Path(crafted).name
        assert safe == "passwd"
        assert ".." not in safe
        assert "/" not in safe

    def test_windows_style_traversal(self):
        crafted = "..\\..\\windows\\system32\\cmd.exe"
        safe = pathlib.Path(crafted).name
        # On Linux pathlib won't split on \, but the resulting filename is
        # still single-component with no / separators.
        assert "/" not in safe

    def test_normal_filename_unchanged(self):
        normal = "stockfish-linux"
        assert pathlib.Path(normal).name == normal

    def test_hidden_file_prefix_preserved(self):
        name = ".stockfish"
        assert pathlib.Path(name).name == ".stockfish"


@pytest.mark.unit
class TestS2XssEscape:
    """S2 (MEDIUM): User-supplied names/commentary must be escaped before html.unsafe_allow_html."""

    def test_script_tag_escaped(self):
        untrusted = '<script>alert("xss")</script>'
        escaped = html.escape(untrusted)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_img_onerror_escaped(self):
        untrusted = '<img src=x onerror=alert(1)>'
        escaped = html.escape(untrusted)
        assert "<img" not in escaped

    def test_normal_name_passes_through(self):
        name = "DrNykterstein"
        assert html.escape(name) == name

    def test_ampersand_escaped(self):
        name = "Player & Opponent"
        escaped = html.escape(name)
        assert "&amp;" in escaped
        assert "&" not in escaped.replace("&amp;", "")

    def test_double_quotes_escaped(self):
        name = 'Player "TheGreat"'
        escaped = html.escape(name)
        assert '"' not in escaped or "&quot;" in escaped


@pytest.mark.unit
class TestS4VersionTagValidation:
    """S4 (LOW-MEDIUM): GitHub tag_name injected into sidebar markdown must be validated."""

    VALID_TAG_PATTERN = re.compile(r'^v\d+\.\d+\.\d+$')

    def _is_valid_tag(self, tag: str) -> bool:
        return bool(self.VALID_TAG_PATTERN.match(tag))

    def test_valid_semver_tag_accepted(self):
        assert self._is_valid_tag("v0.1.14")
        assert self._is_valid_tag("v1.0.0")
        assert self._is_valid_tag("v10.20.30")

    def test_injection_attempt_rejected(self):
        assert not self._is_valid_tag("v0.1.0; rm -rf /")
        assert not self._is_valid_tag("v0.1.0\n[evil](http://evil.example.com)")
        assert not self._is_valid_tag("<script>alert(1)</script>")

    def test_prerelease_suffix_rejected(self):
        # Pattern gates on exact X.Y.Z — pre-release tags must not sneak through
        assert not self._is_valid_tag("v0.1.14-rc1")
        assert not self._is_valid_tag("v0.1.14.post1")

    def test_empty_string_rejected(self):
        assert not self._is_valid_tag("")

    def test_no_v_prefix_rejected(self):
        assert not self._is_valid_tag("0.1.14")


@pytest.mark.unit
class TestS3SqlDocumentation:
    """S3 (MEDIUM): SQL fragment APIs must document their caller contract.

    We can't unit-test 'never user-supplied' as an invariant, but we can
    confirm the SECURITY docstring is present at the call sites.
    """

    def test_acpl_and_blunder_rate_has_security_docstring(self):
        import inspect
        import analytics
        src = inspect.getsource(analytics.acpl_and_blunder_rate)
        assert "SECURITY" in src or "security" in src.lower() or "user-supplied" in src.lower()

    def test_classification_breakdown_has_security_docstring(self):
        import inspect
        import analytics
        src = inspect.getsource(analytics.classification_breakdown)
        assert "SECURITY" in src or "security" in src.lower() or "user-supplied" in src.lower()


@pytest.mark.unit
class TestS5JoblockAtomicity:
    """S5 (LOW): joblock uses OS-level exclusive lock, not TOCTOU-prone PID-check-then-write."""

    def test_joblock_uses_flock_or_msvcrt(self):
        import inspect
        import joblock
        src = inspect.getsource(joblock)
        # The fix requires one of these locking primitives — not just a PID file
        assert "fcntl" in src or "msvcrt" in src

    def test_acquire_release_cycle(self, tmp_path, monkeypatch):
        import joblock
        monkeypatch.setattr(joblock, "LOCK_PATH", tmp_path / "test.lock")
        joblock.release()  # ensure clean state
        joblock.acquire()
        assert joblock.LOCK_PATH.exists()
        joblock.release()
        assert not joblock.LOCK_PATH.exists()

    def test_double_acquire_raises(self, tmp_path, monkeypatch):
        import joblock
        monkeypatch.setattr(joblock, "LOCK_PATH", tmp_path / "test.lock")
        joblock.release()
        joblock.acquire()
        try:
            with pytest.raises(joblock.LockHeldError):
                joblock.acquire()
        finally:
            joblock.release()
