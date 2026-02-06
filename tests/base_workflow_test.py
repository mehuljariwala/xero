"""
Base class for workflow E2E tests.
"""
import asyncio
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, BrowserContext, expect

from tests.utils import WorkflowValidator, print_validation_report


def requires_live(func):
    """Decorator to skip tests that require live Xero access."""
    @pytest.mark.asyncio
    async def wrapper(self, page: Page, live_mode: bool, *args, **kwargs):
        if not live_mode:
            pytest.skip("Requires --live flag for Xero access")
        return await func(self, page, live_mode, *args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class BaseWorkflowTest:
    """Base class for workflow E2E tests with common utilities."""

    WORKFLOW_NAME: str = ""
    WORKFLOW_FILE: str = ""
    REPORT_SEARCH_TERM: str = ""
    XERO_REPORTS_URL = "https://reporting.xero.com/reports"

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        return workflows_dir / self.WORKFLOW_FILE

    async def navigate_to_reports_page(self, page: Page):
        """Navigate to Xero reports page."""
        await page.goto(self.XERO_REPORTS_URL)
        await page.wait_for_load_state("domcontentloaded")

    async def search_for_report(self, page: Page, report_name: str):
        """Search for a report using the search input."""
        search_selectors = [
            "[data-automationid='search-reports--input']",
            "input[placeholder='Find a report']",
        ]

        for selector in search_selectors:
            try:
                search_input = page.locator(selector)
                if await search_input.is_visible(timeout=5000):
                    await search_input.fill(report_name)
                    await page.wait_for_timeout(500)
                    return True
            except Exception:
                continue

        return False

    async def click_report_from_dropdown(self, page: Page, report_name: str):
        """Click on a report from the search dropdown."""
        dropdown_selectors = [
            f"[role='listbox'] button:has-text('{report_name}')",
            f"listbox button:has-text('{report_name}')",
        ]

        for selector in dropdown_selectors:
            try:
                option = page.locator(selector).first
                if await option.is_visible(timeout=3000):
                    await option.click()
                    return True
            except Exception:
                continue

        return False

    async def wait_for_report_page_load(self, page: Page):
        """Wait for the report settings page to fully load."""
        update_button_selectors = [
            "[data-automationid='settings-panel-update-button']",
            "button:has-text('Update')",
        ]

        for selector in update_button_selectors:
            try:
                await page.wait_for_selector(selector, state="visible", timeout=15000)
                return True
            except Exception:
                continue

        return False

    async def validate_selector_exists(
        self, page: Page, selectors: list[str], description: str = ""
    ) -> tuple[bool, str | None]:
        """
        Validate that at least one selector finds a visible element.
        Returns (success, working_selector).
        """
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    return True, selector
            except Exception:
                continue

        return False, None

    async def validate_click_action(
        self, page: Page, selectors: list[str], description: str = ""
    ) -> bool:
        """Validate that a click action can be performed."""
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    await element.click()
                    return True
            except Exception:
                continue

        return False

    async def validate_fill_action(
        self, page: Page, selectors: list[str], value: str, description: str = ""
    ) -> bool:
        """Validate that a fill action can be performed."""
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    await element.fill(value)
                    return True
            except Exception:
                continue

        return False

    async def take_screenshot(self, page: Page, name: str, screenshots_dir: Path):
        """Take a screenshot for debugging."""
        screenshot_path = screenshots_dir / f"{self.WORKFLOW_NAME}_{name}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        return screenshot_path

    async def run_full_workflow_validation(
        self, page: Page, workflow_path: Path, verbose: bool = True
    ):
        """Run full workflow validation against the current page."""
        validator = WorkflowValidator(page)
        report = await validator.validate_workflow(workflow_path)

        if verbose:
            print_validation_report(report)

        return report
