"""
Pytest configuration and fixtures for E2E workflow testing.
"""
import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"
BROWSER_DATA_DIR = Path(__file__).parent.parent / "browser_data"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests against live Xero (requires login)",
    )
    parser.addoption(
        "--html-dir",
        action="store",
        default=None,
        help="Directory containing saved HTML files for offline testing",
    )


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def live_mode(request) -> bool:
    return request.config.getoption("--live")


@pytest.fixture(scope="session")
def html_dir(request) -> Path | None:
    path = request.config.getoption("--html-dir")
    return Path(path) if path else None


@pytest.fixture(scope="session")
async def browser_context(live_mode: bool) -> AsyncGenerator[BrowserContext, None]:
    """Session-scoped persistent browser context with saved Xero session."""
    if not live_mode:
        yield None
        return

    if not BROWSER_DATA_DIR.exists():
        raise RuntimeError(
            f"Browser data directory not found: {BROWSER_DATA_DIR}\n"
            "Please run the app first and log in to Xero to create a session."
        )

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            slow_mo=100,
        )
        yield context
        await context.close()


@pytest.fixture(scope="function")
async def page(browser_context: BrowserContext, live_mode: bool) -> AsyncGenerator[Page, None]:
    """Function-scoped page for each test."""
    if not live_mode or browser_context is None:
        yield None
        return

    page = await browser_context.new_page()
    yield page
    await page.close()


@pytest.fixture
def workflows_dir() -> Path:
    return WORKFLOWS_DIR


@pytest.fixture
def screenshots_dir() -> Path:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOTS_DIR


@pytest.fixture(autouse=True)
def skip_e2e_without_live(request, live_mode: bool):
    """Auto-skip E2E tests that require --live flag."""
    if request.node.get_closest_marker("e2e") and not live_mode:
        pytest.skip("E2E test requires --live flag")
