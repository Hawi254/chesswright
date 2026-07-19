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


# ---------------------------------------------------------------------------
# tournament_prep.html (roadmap §27 Decision 4)
# ---------------------------------------------------------------------------

def _prep_context(**overrides):
    ctx = dict(
        title="Tournament Prep — Test Opponent",
        opponent_name="Test Opponent",
        generated_at="2026-07-11 10:00:00",
        n_analyzed=12,
        record=dict(n_games=8, n_with_opening=8, win_pct=62.5),
        swindle=dict(n_losses=3, n_missed_swindle=1, swindle_rate_pct=33.3),
        form_white=[
            {"opening": "Italian Game", "n_games": 5, "score_pct": 60.0, "avg_cpl": 22.4},
        ],
        form_black=[
            {"opening": "Sicilian Defense", "n_games": 4, "score_pct": 50.0, "avg_cpl": 30.1},
        ],
        tendencies=[
            {"opening": "Sicilian Defense", "color": "black", "n_games": 4,
             "avg_cpl": 30.1, "blunder_pct": 12.5},
        ],
    )
    ctx.update(overrides)
    return ctx


def test_tournament_prep_produces_standalone_document():
    html = report_html.render_report_html("tournament_prep.html", **_prep_context())

    assert "<!doctype html" in html.lower() or "<html" in html.lower()
    assert "<style>" in html


def test_tournament_prep_has_no_external_references():
    html = report_html.render_report_html("tournament_prep.html", **_prep_context())

    assert 'rel="stylesheet"' not in html
    assert "http://" not in html
    assert "https://" not in html


def test_tournament_prep_escapes_hostile_opponent_name():
    hostile = "<script>alert(1)</script>"
    html = report_html.render_report_html(
        "tournament_prep.html", **_prep_context(opponent_name=hostile)
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_tournament_prep_renders_sections_with_real_data():
    html = report_html.render_report_html("tournament_prep.html", **_prep_context())

    assert "Italian Game" in html
    assert "Sicilian Defense" in html
    assert "62.5%" in html
    assert "33.3%" in html


def test_tournament_prep_thin_data_path_has_no_crash_or_literal_none():
    ctx = _prep_context(
        n_analyzed=0,
        record=dict(n_games=0, n_with_opening=0, win_pct=None),
        swindle=dict(n_losses=0, n_missed_swindle=0, swindle_rate_pct=None),
        form_white=[],
        form_black=[],
        tendencies=[],
    )
    html = report_html.render_report_html("tournament_prep.html", **ctx)

    assert "<!doctype html" in html.lower() or "<html" in html.lower()
    assert "None" not in html
    assert "nan" not in html.lower()
    assert "not enough" in html.lower()


def test_tournament_prep_handles_none_metric_within_nonempty_rows():
    # A row with a NaN-derived None avg_cpl (e.g. no engine-analysed moves
    # yet for that opening) must render a fallback dash, not "None".
    ctx = _prep_context(
        form_white=[
            {"opening": "Italian Game", "n_games": 3, "score_pct": 50.0, "avg_cpl": None},
        ],
    )
    html = report_html.render_report_html("tournament_prep.html", **ctx)

    assert "None" not in html
    assert "nan" not in html.lower()
