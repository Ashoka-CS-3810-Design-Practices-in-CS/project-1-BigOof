"""Browser tests for the page's JavaScript, run against a live Flask server.

Requires a Playwright browser: ``uv run playwright install chromium``. Without one
these tests are skipped locally, but fail in CI (where ``CI`` is set) so they can't
silently stop running.
"""

import os
import re
import threading
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from werkzeug.serving import make_server

from big_o.app import app, metro_graph


def _browser_installed() -> bool:
    with sync_playwright() as playwright:
        return Path(playwright.chromium.executable_path).exists()


@pytest.fixture(scope="session", autouse=True)
def require_browser():
    if not _browser_installed():
        message = "Playwright Chromium not installed: run `uv run playwright install chromium`"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)


@pytest.fixture(scope="session")
def live_server():
    """Serve the real app (and real metro.db) on a free port for the whole session."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # Reduced motion makes the page skip its entrance animations, so tests don't
    # wait on them; the kinetic-title test opts back in explicitly.
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "reduced_motion": "reduce",
    }


@pytest.fixture
def station_id():
    names = {station.name: station.code for station in metro_graph.stations.values()}
    return names.__getitem__


@pytest.fixture
def app_page(page: Page, live_server) -> Page:
    """The planner page, loaded and ready (stations and network fetched)."""
    # Don't hit OpenStreetMap's tile servers from tests; the map works without tiles.
    page.route(re.compile(r"https://[a-z]\.tile\.openstreetmap\.org/.*"), lambda route: route.abort())
    page.goto(live_server)
    expect(page.locator("#api-status")).to_have_text(re.compile(r"network loaded$"))
    return page
