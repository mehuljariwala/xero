"""
E2E tests for Account Transactions report workflow.
"""
import pytest
from pathlib import Path
from playwright.async_api import Page

from tests.base_workflow_test import BaseWorkflowTest


@pytest.mark.e2e
class TestAccountTransactionsWorkflow(BaseWorkflowTest):
    WORKFLOW_NAME = "account_transactions"
    WORKFLOW_FILE = "account_transactions.yaml"
    REPORT_SEARCH_TERM = "Account Transactions"

    @pytest.mark.asyncio
    async def test_accounts_selector_dropdown(self, page: Page):
        """Test that Accounts selector dropdown works."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        accounts_dropdown_selectors = [
            "[data-automationid='Accounts-selector-input-open']",
            "[data-automationid='Accounts-selector-autocompleter--input']",
        ]

        found, working = await self.validate_selector_exists(
            page, accounts_dropdown_selectors, "Accounts dropdown"
        )

        assert found, f"Accounts dropdown not found. Tried: {accounts_dropdown_selectors}"
        print(f"Working selector: {working}")

    @pytest.mark.asyncio
    async def test_select_all_accounts(self, page: Page):
        """Test that Select All accounts button works."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.validate_click_action(
            page,
            ["[data-automationid='Accounts-selector-input-open']"],
            "Open accounts dropdown",
        )
        await page.wait_for_timeout(300)

        select_all_selectors = [
            "[data-automationid='Accounts-selector-dropdown-select-all']",
            "button:has-text('Select all')",
        ]

        found, working = await self.validate_selector_exists(
            page, select_all_selectors, "Select all button"
        )

        assert found, f"Select all button not found. Tried: {select_all_selectors}"
        print(f"Working selector: {working}")

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
    async def test_column_checkbox_selectors(self, page: Page):
        """Test that column checkbox selectors work."""
        await self.navigate_to_reports_page(page)
        await self.search_for_report(page, self.REPORT_SEARCH_TERM)
        await self.click_report_from_dropdown(page, self.REPORT_SEARCH_TERM)
        await self.wait_for_report_page_load(page)

        await self.validate_click_action(
            page,
            [
                "[data-automationid='report-settings-columns-button']",
                "button:has-text('columns selected')",
            ],
            "Open columns dropdown",
        )
        await page.wait_for_timeout(300)

        column_checkboxes = [
            "[data-automationid='column-selection-accountcode--body--checkbox']",
            "[data-automationid='column-selection-contactname--body--checkbox']",
            "[data-automationid='column-selection-debit--body--checkbox']",
            "[data-automationid='column-selection-credit--body--checkbox']",
        ]

        for checkbox_selector in column_checkboxes:
            found, working = await self.validate_selector_exists(
                page, [checkbox_selector], f"Checkbox {checkbox_selector}"
            )
            assert found, f"Column checkbox not found: {checkbox_selector}"

        print("All column checkbox selectors validated successfully!")

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
            ["[data-automationid='Accounts-selector-input-open']"],
            "Open accounts",
        )
        await page.wait_for_timeout(300)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='Accounts-selector-dropdown-select-all']", "button:has-text('Select all')"],
            "Select all accounts",
        )
        await page.wait_for_timeout(300)
        await self.take_screenshot(page, "02_accounts_selected", screenshots_dir)

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
        await self.take_screenshot(page, "03_date_selected", screenshots_dir)

        assert await self.validate_click_action(
            page,
            ["[data-automationid='settings-panel-update-button']"],
            "Update button",
        )

        await page.wait_for_selector(
            "status:has-text('Report has finished loading'), table, [role='table']",
            timeout=30000,
        )
        await self.take_screenshot(page, "04_report_updated", screenshots_dir)

        found, _ = await self.validate_selector_exists(
            page, ["button:has-text('Export')"], "Export button"
        )
        assert found, "Export button should be visible after report loads"

        print("End-to-end flow completed successfully!")
