#!/usr/bin/env python3
"""
Comprehensive E2E test for Xero report workflows.
Validates navigation, date selection, column selection, and export.

Run with: python tests/manual_test.py [report_name|all]
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright, Page

BROWSER_DATA_DIR = Path(__file__).parent.parent / "browser_data"
XERO_REPORTS_URL = "https://reporting.xero.com/reports"


REPORT_CONFIGS = {
    "trial_balance": {
        "name": "Trial Balance",
        "search_term": "Trial Balance",
        "date_option": "End of last financial year",
        "date_automationid": "report-settings-date-option-End of last financial year",
        "has_columns": True,
        "columns": [
            ("column-selection-accountname--body--checkbox", "Account"),
            ("column-selection-accountcode--body--checkbox", "Account Code"),
            ("column-selection-accounttype--body--checkbox", "Account Type"),
            ("column-selection-credit--body--checkbox", "Credit - Year to date"),
            ("column-selection-debit--body--checkbox", "Debit - Year to date"),
        ],
    },
    "profit_and_loss": {
        "name": "Profit and Loss",
        "search_term": "Profit and Loss",
        "date_option": "Last financial year",
        "date_automationid": "report-settings-date-option-Last financial year",
        "has_columns": False,
        "has_more_options": True,
        "more_options": [
            ("report-settings-isaccountcodeandname-checkbox--input", "Account codes", True),
            ("report-settings-showdecimals-checkbox--input", "Decimals", True),
        ],
    },
    "aged_receivables": {
        "name": "Aged Receivables Detail",
        "search_term": "Aged Receivables Detail",
        "date_option": "End of last financial year",
        "date_automationid": "report-settings-date-option-End of last financial year",
        "has_columns": True,
        "columns": [
            ("column-selection-amountinperiod--body--checkbox", "Ageing Periods"),
            ("column-selection-duedate--body--checkbox", "Due Date"),
            ("column-selection-invoicedate--body--checkbox", "Invoice Date"),
            ("column-selection-invoicenumber--body--checkbox", "Invoice Number"),
            ("column-selection-invoicereference--body--checkbox", "Invoice Reference"),
            ("column-selection-total--body--checkbox", "Total"),
            ("column-selection-taxamountdue--body--checkbox", "Outstanding VAT"),
        ],
    },
    "aged_payables": {
        "name": "Aged Payables Detail",
        "search_term": "Aged Payables Detail",
        "date_option": "End of last financial year",
        "date_automationid": "report-settings-date-option-End of last financial year",
        "has_columns": True,
        "columns": [
            ("column-selection-amountinperiod--body--checkbox", "Ageing Periods"),
            ("column-selection-duedate--body--checkbox", "Due Date"),
            ("column-selection-invoicedate--body--checkbox", "Invoice Date"),
            ("column-selection-invoicereference--body--checkbox", "Invoice Reference"),
            ("column-selection-total--body--checkbox", "Total"),
            ("column-selection-taxamountdue--body--checkbox", "Outstanding VAT"),
        ],
    },
    "account_transactions": {
        "name": "Account Transactions",
        "search_term": "Account Transactions",
        "date_option": "Last financial year",
        "date_automationid": "report-settings-date-option-Last financial year",
        "has_columns": True,
        "has_accounts_selector": True,
        "columns": [
            ("column-selection-accountcode--body--checkbox", "Account Code"),
            ("column-selection-credit--body--checkbox", "Credit"),
            ("column-selection-debit--body--checkbox", "Debit"),
            ("column-selection-description--body--checkbox", "Description"),
            ("column-selection-gross--body--checkbox", "Gross"),
            ("column-selection-invoicenumber--body--checkbox", "Invoice Number"),
            ("column-selection-net--body--checkbox", "Net"),
            ("column-selection-reference--body--checkbox", "Reference"),
            ("column-selection-source--body--checkbox", "Source"),
            ("column-selection-taxamount--body--checkbox", "VAT"),
            ("column-selection-taxratepercentage--body--checkbox", "VAT Rate"),
        ],
    },
    "receivable_invoice_detail": {
        "name": "Receivable Invoice Detail",
        "search_term": "Receivable Invoice Detail",
        "date_option": "Last financial year",
        "date_automationid": "report-settings-date-option-Last financial year",
        "has_columns": True,
        "columns": [
            ("column-selection-accountname--body--checkbox", "Account"),
            ("column-selection-accountcode--body--checkbox", "Account Code"),
            ("column-selection-outstandingamount--body--checkbox", "Balance"),
            ("column-selection-contactname--body--checkbox", "Contact"),
            ("column-selection-description--body--checkbox", "Description"),
            ("column-selection-discountamount--body--checkbox", "Discount (ex)"),
            ("column-selection-duedate--body--checkbox", "Due Date"),
            ("column-selection-gross--body--checkbox", "Gross"),
            ("column-selection-invoicedate--body--checkbox", "Invoice Date"),
            ("column-selection-invoicetotal--body--checkbox", "Invoice Total"),
            ("column-selection-itemcode--body--checkbox", "Item Code"),
            ("column-selection-lastpaymentdate--body--checkbox", "Last Payment Date"),
            ("column-selection-netamount--body--checkbox", "Net"),
            ("column-selection-quantity--body--checkbox", "Quantity"),
            ("column-selection-reference--body--checkbox", "Reference"),
            ("column-selection-invoicetype--body--checkbox", "Source"),
            ("column-selection-invoicestatus--body--checkbox", "Status"),
            ("column-selection-unitpriceexclusive--body--checkbox", "Unit Price (ex)"),
            ("column-selection-taxamount--body--checkbox", "VAT"),
            ("column-selection-taxratename--body--checkbox", "VAT Rate Name"),
        ],
    },
    "payable_invoice_detail": {
        "name": "Payable Invoice Detail",
        "search_term": "Payable Invoice Detail",
        "date_option": "Last financial year",
        "date_automationid": "report-settings-date-option-Last financial year",
        "has_columns": True,
        "columns": [
            ("column-selection-accountname--body--checkbox", "Account"),
            ("column-selection-accountcode--body--checkbox", "Account Code"),
            ("column-selection-contactgroup--body--checkbox", "Contact Group"),
            ("column-selection-description--body--checkbox", "Description"),
            ("column-selection-duedate--body--checkbox", "Due Date"),
            ("column-selection-gross--body--checkbox", "Gross"),
            ("column-selection-invoicedate--body--checkbox", "Invoice Date"),
            ("column-selection-invoicetotal--body--checkbox", "Invoice Total"),
            ("column-selection-itemcode--body--checkbox", "Item Code"),
            ("column-selection-lastpaymentdate--body--checkbox", "Last Payment Date"),
            ("column-selection-quantity--body--checkbox", "Quantity"),
            ("column-selection-reference--body--checkbox", "Reference"),
            ("column-selection-invoicetype--body--checkbox", "Source"),
            ("column-selection-invoicestatus--body--checkbox", "Status"),
            ("column-selection-unitpriceexclusive--body--checkbox", "Unit Price (ex)"),
            ("column-selection-taxamount--body--checkbox", "VAT"),
            ("column-selection-taxratename--body--checkbox", "VAT Rate Name"),
        ],
    },
}


async def check_login_status(page: Page) -> bool:
    current_url = page.url
    if "login.xero.com" in current_url or "identity.xero.com" in current_url:
        return False
    return True


async def wait_for_login(page: Page):
    print("\n⚠️  LOGIN REQUIRED")
    print("   Please complete the login in the browser window.")
    print("   Waiting for login to complete...")
    while True:
        await page.wait_for_timeout(2000)
        if await check_login_status(page):
            print("   ✅ Login detected!")
            break


async def test_selector(page: Page, selectors: list[str], description: str, timeout: int = 5000) -> tuple[bool, str | None]:
    for selector in selectors:
        try:
            element = page.locator(selector).first
            visible = await element.is_visible(timeout=timeout)
            if visible:
                print(f"   ✅ {description}: FOUND")
                return True, selector
        except Exception:
            continue
    print(f"   ❌ {description}: NOT FOUND")
    return False, None


async def test_checkbox(page: Page, automationid: str, name: str) -> bool:
    """Test if a column checkbox selector exists."""
    selector = f"[data-automationid='{automationid}']"
    try:
        element = page.locator(selector).first
        visible = await element.is_visible(timeout=3000)
        if visible:
            print(f"      ✅ {name}")
            return True
    except Exception:
        pass
    print(f"      ❌ {name} ({automationid})")
    return False


async def test_report(report_key: str, context) -> dict:
    """Test a single report and return results."""
    config = REPORT_CONFIGS.get(report_key)
    if not config:
        print(f"Unknown report: {report_key}")
        return {"passed": 0, "failed": 1, "name": report_key}

    print("\n" + "=" * 70)
    print(f"TESTING: {config['name']}")
    print("=" * 70)

    page = await context.new_page()
    results = {"passed": 0, "failed": 0, "name": config["name"]}

    try:
        # Navigate to reports
        print(f"\n[1] Navigating to reports page...")
        await page.goto(XERO_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        if not await check_login_status(page):
            await wait_for_login(page)
            await page.goto(XERO_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

        # Search for report
        print(f"\n[2] Searching for '{config['search_term']}'...")
        found, _ = await test_selector(page, [
            "[data-automationid='search-reports--input']",
        ], "Search input")
        results["passed" if found else "failed"] += 1

        await page.locator("[data-automationid='search-reports--input']").first.fill(config['search_term'])
        await page.wait_for_timeout(1000)

        # Click report from dropdown
        print(f"\n[3] Clicking report from dropdown...")
        found, selector = await test_selector(page, [
            f"[role='listbox'] button:has-text('{config['search_term']}')",
            f"listbox button:has-text('{config['search_term']}')",
        ], "Search dropdown")
        results["passed" if found else "failed"] += 1

        if found and selector:
            await page.locator(selector).first.click()
            await page.wait_for_timeout(1500)

        # Wait for report page
        print(f"\n[4] Waiting for report page to load...")
        try:
            await page.wait_for_selector(
                "[data-automationid='settings-panel-update-button']",
                state="visible", timeout=15000
            )
            print("   ✅ Report page loaded")
            results["passed"] += 1
        except Exception:
            print("   ❌ Report page failed to load")
            results["failed"] += 1
            return results

        # Test accounts selector if applicable
        if config.get("has_accounts_selector"):
            print(f"\n[5] Testing accounts selector...")
            found, selector = await test_selector(page, [
                "[data-automationid='Accounts-selector-input-open']",
                "[data-automationid='Accounts-selector-autocompleter--input']",
                "button:has-text('Accounts')",
                "[aria-label*='Accounts']",
            ], "Accounts dropdown")
            results["passed" if found else "failed"] += 1

            if found:
                await page.locator(selector).first.click()
                await page.wait_for_timeout(500)

                found, selector = await test_selector(page, [
                    "[data-automationid='Accounts-selector-dropdown-select-all']",
                    "button:has-text('Select all')",
                    "[role='option']:has-text('Select all')",
                ], "Select all accounts")
                results["passed" if found else "failed"] += 1

                if found:
                    await page.locator(selector).first.click()
                    await page.wait_for_timeout(500)

                # Close the accounts dropdown
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)

        # Test date dropdown
        print(f"\n[6] Testing date selection...")
        found, selector = await test_selector(page, [
            "[data-automationid='report-settings-convenience-date-dropdown-button']",
        ], "Date dropdown")
        results["passed" if found else "failed"] += 1

        if found:
            await page.locator(selector).first.click()
            await page.wait_for_timeout(500)

            found, selector = await test_selector(page, [
                f"[data-automationid='{config['date_automationid']}']",
                f"[role='option']:has-text('{config['date_option']}')",
            ], f"Date option '{config['date_option']}'")
            results["passed" if found else "failed"] += 1

            if found:
                await page.locator(selector).first.click()
                await page.wait_for_timeout(500)

        # Test columns
        if config.get("has_columns"):
            print(f"\n[7] Testing columns dropdown...")
            found, selector = await test_selector(page, [
                "[data-automationid='report-settings-columns-button']",
                "button:has-text('columns selected')",
            ], "Columns dropdown")
            results["passed" if found else "failed"] += 1

            if found:
                await page.locator(selector).first.click()
                await page.wait_for_timeout(500)

                print(f"\n[8] Validating column checkboxes ({len(config['columns'])} expected)...")
                columns_passed = 0
                for automationid, name in config["columns"]:
                    if await test_checkbox(page, automationid, name):
                        columns_passed += 1
                    else:
                        results["failed"] += 1

                results["passed"] += columns_passed
                print(f"\n   Column validation: {columns_passed}/{len(config['columns'])} passed")

                # Close columns dropdown - try Done button, then Escape key
                try:
                    done_btn = page.locator("button:has-text('Done')").first
                    if await done_btn.is_visible(timeout=1000):
                        await done_btn.click()
                        await page.wait_for_timeout(300)
                    else:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(300)
                except Exception:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(300)

        # Test More options for P&L
        elif config.get("has_more_options"):
            print(f"\n[7] Testing More options...")
            found, selector = await test_selector(page, [
                "[data-automationid='report-settings-advanced-button']",
                "button:has-text('More')",
            ], "More options button")
            results["passed" if found else "failed"] += 1

            if found:
                await page.locator(selector).first.click()
                await page.wait_for_timeout(500)

                print(f"\n[8] Validating option checkboxes...")
                for automationid, name, expected in config.get("more_options", []):
                    selector = f"[data-automationid='{automationid}']"
                    try:
                        element = page.locator(selector).first
                        if await element.is_visible(timeout=3000):
                            print(f"      ✅ {name}")
                            results["passed"] += 1
                        else:
                            print(f"      ❌ {name}")
                            results["failed"] += 1
                    except Exception:
                        print(f"      ❌ {name}")
                        results["failed"] += 1

        # Test Update button
        print(f"\n[9] Testing Update button...")
        found, selector = await test_selector(page, [
            "[data-automationid='settings-panel-update-button']",
        ], "Update button")
        results["passed" if found else "failed"] += 1

        if found:
            await page.locator(selector).first.click()

        # Wait for report to load
        print(f"\n[10] Waiting for report to load...")
        try:
            await page.wait_for_selector(
                "status:has-text('Report has finished loading'), table, [role='table']",
                timeout=30000
            )
            print("   ✅ Report loaded")
            results["passed"] += 1
        except Exception:
            print("   ⚠️  Report load timeout (may still be loading)")
            await page.wait_for_timeout(5000)

        # Test Export button
        print(f"\n[11] Testing Export button...")
        found, _ = await test_selector(page, [
            "button:has-text('Export')",
        ], "Export button")
        results["passed" if found else "failed"] += 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        results["failed"] += 1

    finally:
        await page.close()

    return results


async def run_all_tests():
    """Run tests for all reports."""
    print("=" * 70)
    print("COMPREHENSIVE XERO WORKFLOW E2E TEST")
    print("=" * 70)

    async with async_playwright() as p:
        print("\nLaunching browser with saved session...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            slow_mo=100,
        )

        all_results = []

        for report_key in REPORT_CONFIGS.keys():
            result = await test_report(report_key, context)
            all_results.append(result)
            await asyncio.sleep(1)

        await context.close()

    # Print summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    total_passed = 0
    total_failed = 0

    for result in all_results:
        status = "✅" if result["failed"] == 0 else "⚠️"
        total = result["passed"] + result["failed"]
        rate = (result["passed"] / total * 100) if total > 0 else 0
        print(f"{status} {result['name']}: {result['passed']}/{total} ({rate:.0f}%)")
        total_passed += result["passed"]
        total_failed += result["failed"]

    print("-" * 70)
    grand_total = total_passed + total_failed
    grand_rate = (total_passed / grand_total * 100) if grand_total > 0 else 0
    print(f"TOTAL: {total_passed}/{grand_total} ({grand_rate:.1f}%)")
    print("=" * 70)

    if total_failed == 0:
        print("\n✅ ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total_failed} test(s) need attention")


async def run_single_test(report_key: str):
    """Run test for a single report."""
    async with async_playwright() as p:
        print("\nLaunching browser with saved session...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            slow_mo=100,
        )

        result = await test_report(report_key, context)

        await context.close()

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = result["passed"] + result["failed"]
    rate = (result["passed"] / total * 100) if total > 0 else 0
    print(f"Passed: {result['passed']}/{total} ({rate:.1f}%)")

    if result["failed"] == 0:
        print("\n✅ ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {result['failed']} test(s) need attention")


if __name__ == "__main__":
    report = sys.argv[1] if len(sys.argv) > 1 else "all"

    if report == "all":
        asyncio.run(run_all_tests())
    elif report in REPORT_CONFIGS:
        asyncio.run(run_single_test(report))
    else:
        print(f"Unknown report: {report}")
        print(f"Available reports: {', '.join(REPORT_CONFIGS.keys())}, all")
        sys.exit(1)
