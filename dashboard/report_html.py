"""HTML report rendering — Jinja2-templated, self-contained HTML export for
Chesswright reports (single-game report today; tournament-prep report is a
planned sibling, see docs/implementation_roadmap.md §27).

Converts a cached Claude-generated Markdown report body to HTML, then
renders it into one of the templates in dashboard/templates/reports/ to
produce a complete, standalone HTML string -- inline CSS, no external
stylesheet/font/script reference, since the output is a real file a user
may open from Downloads or forward to someone on a different machine.

autoescape=True is deliberate: report templates also receive plain
free-text context (opponent names, etc.) that is real, untrusted-ish game
data and must be escaped. The one exception (the already-markdown-derived
HTML fragment) is opted out of escaping explicitly in the template with
`| safe`, not by disabling autoescape globally.
"""
import pathlib

import jinja2
import markdown

_TEMPLATES_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "reports"
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def markdown_to_html(md_text: str) -> str:
    """Convert a Claude-generated report's Markdown body to HTML fragment."""
    return markdown.markdown(md_text)


def render_report_html(template_name: str, **context) -> str:
    """Render one of the templates in dashboard/templates/reports/ to a
    complete, standalone HTML string -- inline CSS, no external
    stylesheet/font/script reference, since the output is a real file a
    user may open from Downloads or forward to someone on a different
    machine."""
    return _env.get_template(template_name).render(**context)
