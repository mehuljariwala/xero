"""
E2E tests for Profit and Loss report workflow.
"""
import pytest
from pathlib import Path
from playwright.async_api import Page

from tests.base_workflow_test import BaseWorkflowTest


@pytest.mark.e2e
class TestProfitAndLossWorkflow(BaseWorkflowTest):
    WORKFLOW_NAME = "profit_and_loss"
    WORKFLOW_FILE = "profit_and_loss.yaml"
    REPORT_SEARCH_TERM = "Profit and Loss"

    @pytest.mark.asyncio
    async def test_date_option_selectors(self, page: Page):
        """Test that date option selectors work (Last financial year - range report)."""
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
            "[data-automationid='report-settings-date-option-Last financial year']",
            "[role='option']:has-text('Last financial year')",
            "li:has-text('Last financial year')",
        ]

        found, working = await self.validate_selector_exists(
            page, date_option_selectors, "Last financial year option"
        )

        assert found, f"Date option not found. Tried: {date_option_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_comparison_dropdown_selectors(self, page: Page):
        """Test that comparison period dropdown selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        comparison_dropdown_selectors = [
            "[data-automationid='report-settings-comparison-period-button']",
            "#report-settings-comparison-period-button",
            "button:has-text('Compare with')",
        ]

        found, working = await self.validate_selector_exists(
            page, comparison_dropdown_selectors, "Comparison dropdown"
        )

        assert found, f"Comparison dropdown not found. Tried: {comparison_dropdown_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_more_options_selectors(self, page: Page):
        """Test that More options button selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        more_button_selectors = [
            "[data-automationid='report-settings-advanced-button']",
            "button:has-text('More')",
        ]

        found, working = await self.validate_selector_exists(
            page, more_button_selectors, "More options button"
        )

        assert found, f"More options button not found. Tried: {more_button_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_checkbox_selectors(self, page: Page):
        """Test that checkbox selectors for options work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.validate_click_action(
            page,
            ["[data-automationid='report-settings-advanced-button']", "button:has-text('More')"],
            "Open More options",
        )
        await page.wait_for_timeout(300)

        account_codes_checkbox = [
            "[data-automationid='report-settings-isaccountcodeandname-checkbox--input']",
        ]

        found, working = await self.validate_selector_exists(
            page, account_codes_checkbox, "Account codes checkbox"
        )

        assert found, f"Account codes checkbox not found. Tried: {account_codes_checkbox}"
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
        assert await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        assert await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        assert await self.wait_for_report_page_load(page)
        await self.take_screenshot(page, "01_report_loaded", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='report-settings-convenience-date-dropdown-button']"],
            "Date dropdown",
        )
        await page.wait_for_timeout(300)

        assert await self.validate_click_action(
            page,
            [
                "[data-automationid='report-settings-date-option-Last financial year']",
                "[role='option']:has-text('Last financial year')",
            ],
            "Select date",
        )
        await page.wait_for_timeout(200)
        await self.take_screenshot(page, "02_date_selected", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='report-settings-comparison-period-button']"],
            "Comparison dropdown",
        )
        await page.wait_for_timeout(200)

        assert await self.validate_click_action(
            page,
            ["button:has-text('1 year')", "[role='option']:has-text('1 year')"],
            "Select 1 year comparison",
        )
        await page.wait_for_timeout(200)
        await self.take_screenshot(page, "03_comparison_selected", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='settings-panel-update-button']"],
            "Update button",
        )

        await page.wait_for_selector(
            "status:has-text('Report has finished loading'), table, .report-body",
            timeout=15000,
        )
        await self.take_screenshot(page, "04_report_updated", screenshots_dir)

        found, _ = await self.validate_selector_exists(
            page, ["button:has-text('Export')"], "Export button"
        )
        assert found, "Export button should be visible after report loads"

        print("End-to-end flow completed successfully!")
