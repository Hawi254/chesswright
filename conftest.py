import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-streamlit-ui",
        action="store_true",
        default=False,
        help="Run Streamlit AppTest page-render tests (skipped by default).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-streamlit-ui"):
        return
    skip_streamlit_ui = pytest.mark.skip(
        reason="Streamlit UI test -- pass --run-streamlit-ui to run"
    )
    for item in items:
        if "ui" in item.keywords:
            item.add_marker(skip_streamlit_ui)
