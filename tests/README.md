# Xero Workflow E2E Tests

End-to-end tests for validating Xero report workflows and selectors.

## Setup

1. Install dev dependencies:
```bash
uv pip install -e ".[dev]"
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

## Running Tests

### Prerequisites

Before running live tests, you need to be logged into Xero in the test browser:

1. Run the app once to create browser session:
```bash
python app.py
```

2. Log in to Xero through the web UI

3. The browser session is saved in `./browser_data/`

### Test Commands

```bash
# Run all tests against live Xero (headless mode)
pytest tests/ --live

# Run with visible browser for debugging
pytest tests/ --live --headed

# Run with slow motion (500ms delay between actions)
pytest tests/ --live --headed --slow-mo 500

# Run specific report tests
pytest tests/test_trial_balance.py --live --headed
pytest tests/test_profit_and_loss.py --live --headed
pytest tests/test_aged_receivables.py --live --headed
pytest tests/test_aged_payables.py --live --headed
pytest tests/test_account_transactions.py --live --headed

# Run only selector validation tests
pytest tests/ --live -k "selector"

# Run only end-to-end flow tests
pytest tests/ --live -k "end_to_end"

# Run only full workflow validation tests
pytest tests/ --live -k "full_workflow"

# Generate verbose output
pytest tests/ --live -v

# Stop on first failure
pytest tests/ --live -x
```

### Using the Test Runner Script

```bash
# Run all tests
python tests/run_tests.py --live

# Run with visible browser
python tests/run_tests.py --live --headed

# Run specific report
python tests/run_tests.py --live --report trial_balance

# Run with debugging (slow + visible)
python tests/run_tests.py --live --headed --slow-mo 500
```

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── base_workflow_test.py    # Base class with common test utilities
├── run_tests.py             # Convenient test runner script
├── utils/
│   ├── __init__.py
│   └── selector_validator.py  # Selector validation utilities
├── test_trial_balance.py    # Trial Balance report tests
├── test_profit_and_loss.py  # Profit & Loss report tests
├── test_aged_receivables.py # Aged Receivables Detail tests
├── test_aged_payables.py    # Aged Payables Detail tests
└── test_account_transactions.py  # Account Transactions tests
```

## Test Types

### 1. Selector Validation Tests
Test that individual selectors find visible elements on the page.

```python
async def test_date_dropdown_selectors(self, page, live_mode):
    # Validates selectors exist and are visible
```

### 2. Action Validation Tests
Test that click, fill, and other actions can be performed.

```python
async def test_date_option_selectors(self, page, live_mode):
    # Opens dropdown, validates options exist
```

### 3. Full Workflow Validation
Runs the SelectorValidator against all selectors in a workflow YAML.

```python
async def test_full_workflow_validation(self, page, workflow_path, live_mode):
    # Generates comprehensive validation report
```

### 4. End-to-End Flow Tests
Tests the complete workflow without actually downloading files.

```python
async def test_end_to_end_flow(self, page, live_mode, screenshots_dir):
    # Executes full flow, takes screenshots at each step
```

## Screenshots

Screenshots are saved to `tests/screenshots/` for debugging failed tests.

## Adding Tests for New Workflows

1. Create a new test file:
```python
# tests/test_new_report.py
from tests.base_workflow_test import BaseWorkflowTest

class TestNewReportWorkflow(BaseWorkflowTest):
    WORKFLOW_NAME = "new_report"
    WORKFLOW_FILE = "new_report.yaml"
    REPORT_SEARCH_TERM = "New Report Name"

    # Add test methods...
```

2. Inherit common utilities from `BaseWorkflowTest`
3. Use the validation methods for consistent testing

## Troubleshooting

### Tests skipped with "Requires --live flag"
Add `--live` to your pytest command to run against real Xero.

### Browser not logged in
Run the main app and log in first, or use the persistent context fixture.

### Selectors not found
1. Run with `--headed --slow-mo 500` to watch the browser
2. Check screenshots in `tests/screenshots/`
3. Use browser DevTools to inspect elements
4. Update workflow YAML with correct selectors

### Timeouts
Increase timeout in test or add `--slow-mo` flag.
