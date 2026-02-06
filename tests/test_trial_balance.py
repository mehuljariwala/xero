"""
E2E tests for Trial Balance report workflow.
"""
import pytest
from pathlib import Path
from playwright.async_api import Page

from tests.base_workflow_test import BaseWorkflowTest


@pytest.mark.e2e
class TestTrialBalanceWorkflow(BaseWorkflowTest):
    WORKFLOW_NAME = "trial_balance_report"
    WORKFLOW_FILE = "trial_balance_report.yaml"
    REPORT_SEARCH_TERM = "Trial Balance"

    @pytest.mark.asyncio
    async def test_search_input_selectors(self, page: Page):
        """Test that search input selectors work."""
        await self.navigate_to_reports_page(page)

        search_selectors = [
            "[data-automationid='search-reports--input']",
            "input[placeholder='Find a report']",
            "input.search-reports-input",
        ]

        found, working = await self.validate_selector_exists(
            page, search_selectors, "Search input"
        )

        assert found, f"Search input not found. Tried: {search_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_date_dropdown_selectors(self, page: Page):
        """Test that date dropdown selectors work on Trial Balance report page."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        date_dropdown_selectors = [
            "[data-automationid='report-settings-convenience-date-dropdown-button']",
            "button[aria-label='List of convenience dates']",
        ]

        found, working = await self.validate_selector_exists(
            page, date_dropdown_selectors, "Date dropdown"
        )

        assert found, f"Date dropdown not found. Tried: {date_dropdown_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_date_option_selectors(self, page: Page):
        """Test that date option selectors work (End of last financial year)."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.validate_click_action(
            page,
            ["[data-automationid='report-settings-convenience-date-dropdown-button']"],
            "Open date dropdown",
        )
        await page.wait_for_timeout(300)

        date_option_selectors = [
            "[data-automationid='report-settings-date-option-End of last financial year']",
            "[role='option']:has-text('End of last financial year')",
            "li:has-text('End of last financial year')",
        ]

        found, working = await self.validate_selector_exists(
            page, date_option_selectors, "End of last financial year option"
        )

        assert found, f"Date option not found. Tried: {date_option_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_columns_dropdown_selectors(self, page: Page):
        """Test that columns dropdown selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        columns_dropdown_selectors = [
            "[data-automationid='report-settings-columns-button']",
            "#report-settings-columns-button",
            "button:has-text('columns selected')",
        ]

        found, working = await self.validate_selector_exists(
            page, columns_dropdown_selectors, "Columns dropdown"
        )

        assert found, f"Columns dropdown not found. Tried: {columns_dropdown_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_update_button_selectors(self, page: Page):
        """Test that update button selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        update_button_selectors = [
            "[data-automationid='settings-panel-update-button']",
            "button:has-text('Update')",
        ]

        found, working = await self.validate_selector_exists(
            page, update_button_selectors, "Update button"
        )

        assert found, f"Update button not found. Tried: {update_button_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_export_button_selectors(self, page: Page):
        """Test that export button selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.validate_click_action(
            page,
            ["[data-automationid='settings-panel-update-button']"],
            "Click Update",
        )

        await page.wait_for_selector(
            "status:has-text('Report has finished loading'), table, [role='table']",
            timeout=15000,
        )

        export_button_selectors = [
            "button:has-text('Export')",
            "button[aria-label*='Export']",
        ]

        found, working = await self.validate_selector_exists(
            page, export_button_selectors, "Export button"
        )

        assert found, f"Export button not found. Tried: {export_button_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_full_workflow_validation(
        self, page: Page, workflow_path: Path, screenshots_dir: Path
    ):
        """Run full workflow validation and generate report."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.take_screenshot(page, "report_page_loaded", screenshots_dir)

        report = await self.run_full_workflow_validation(page, workflow_path)

        assert report.success_rate >= 80, (
            f"Workflow validation success rate too low: {report.success_rate:.1f}%"
        )

    @pytest.mark.asyncio
    async def test_end_to_end_flow(self, page: Page, screenshots_dir: Path):
        """Test the complete end-to-end flow without downloading."""
        await self.navigate_to_reports_page(page)
        await self.take_screenshot(page, "01_reports_page", screenshots_dir)

        assert await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.take_screenshot(page, "02_after_search", screenshots_dir)

        assert await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        assert await self.wait_for_report_page_load(page)
        await self.take_screenshot(page, "03_report_loaded", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='report-settings-convenience-date-dropdown-button']"],
            "Date dropdown",
        )
        await page.wait_for_timeout(300)
        await self.take_screenshot(page, "04_date_dropdown_open", screenshots_dir)

        assert await self.validate_click_action(
            page,
            [
                "[data-automationid='report-settings-date-option-End of last financial year']",
                "[role='option']:has-text('End of last financial year')",
            ],
            "Select date",
        )
        await page.wait_for_timeout(200)
        await self.take_screenshot(page, "05_date_selected", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='settings-panel-update-button']"],
            "Update button",
        )

        await page.wait_for_selector(
            "status:has-text('Report has finished loading'), table",
            timeout=15000,
        )
        await self.take_screenshot(page, "06_report_updated", screenshots_dir)

        found, _ = await self.validate_selector_exists(
            page, ["button:has-text('Export')"], "Export button"
        )
        assert found, "Export button should be visible after report loads"
        await self.take_screenshot(page, "07_ready_for_export", screenshots_dir)

        print("End-to-end flow completed successfully!")
