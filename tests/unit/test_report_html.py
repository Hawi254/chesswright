"""Unit tests for dashboard/report_html.py (HTML report export, roadmap
§27). Pure functions -- no Streamlit runtime, no DB fixture needed.
"""
import report_html


def test_markdown_to_html_converts_heading_bold_and_bullets():
    md = (
        "**Opening:** A solid start.\n\n"
        "**Key moments:**\n\n"
        "- **12. Nxe5** (YOUR move): a blunder.\n"
        "- **15. Qh5** (opponent's move): a mistake.\n"
    )
    html = report_html.markdown_to_html(md)

    assert "<strong>Opening:</strong>" in html
    assert "<strong>Key moments:</strong>" in html
    assert "<ul>" in html
    assert "<li><strong>12. Nxe5</strong> (YOUR move): a blunder.</li>" in html


def _full_context(**overrides):
    ctx = dict(
        title="Game Report — vs Test Opponent (2026-07-01)",
        opponent_name="Test Opponent",
        utc_date="2026-07-01",
        result="win",
        color="white",
        opening="Sicilian Defense",
        time_control="Blitz",
        generated_at="2026-07-11 10:00 UTC",
        body_html=report_html.markdown_to_html(
            "**Opening:** A solid start.\n\n- one\n- two\n"
        ),
    )
    ctx.update(overrides)
    return ctx


def test_render_report_html_produces_standalone_document():
    html = report_html.render_report_html("game_report.html", **_full_context())

    assert "<!doctype html" in html.lower() or "<html" in html.lower()
    assert "<style>" in html


def test_render_report_html_has_no_external_references():
    html = report_html.render_report_html("game_report.html", **_full_context())

    assert 'rel="stylesheet"' not in html
    assert "http://" not in html
    assert "https://" not in html


def test_render_report_html_escapes_hostile_context_vars():
    hostile = "<script>alert(1)</script>"
    html = report_html.render_report_html(
        "game_report.html", **_full_context(opponent_name=hostile)
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_report_html_does_not_double_escape_markdown_body():
    body_html = report_html.markdown_to_html("**bold text**")
    html = report_html.render_report_html(
        "game_report.html", **_full_context(body_html=body_html)
    )

    assert "<strong>bold text</strong>" in html
    assert "&lt;strong&gt;" not in html
