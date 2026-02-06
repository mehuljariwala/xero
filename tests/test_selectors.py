"""
Comprehensive Selector Validation Tests for Xero Workflow Automation

This test suite validates all selectors defined in workflow YAML files:
1. Syntax validation for CSS/Playwright selectors
2. Consistency checks across workflows
3. Pattern analysis for potential issues
4. Column count verification
"""

import pytest
import yaml
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class SelectorIssue:
    """Represents a potential selector issue"""
    workflow: str
    step_id: str
    selector: str
    issue_type: str
    severity: str  # 'error', 'warning', 'info'
    message: str


class SelectorValidator:
    """Validates Playwright/CSS selectors for common issues"""

    VALID_PSEUDO_SELECTORS = [
        'has-text', 'has', 'is', 'not', 'first-of-type', 'last-of-type',
        'nth-of-type', 'nth-child', 'first-child', 'last-child', 'visible',
        'hidden', 'enabled', 'disabled', 'checked', 'focus'
    ]

    VALID_ROLE_VALUES = [
        'button', 'checkbox', 'dialog', 'listbox', 'option', 'menuitem',
        'textbox', 'table', 'row', 'cell', 'link', 'tab', 'tabpanel',
        'heading', 'img', 'list', 'listitem', 'menu', 'navigation',
        'progressbar', 'radio', 'slider', 'switch', 'tree', 'treeitem'
    ]

    def __init__(self):
        self.issues: List[SelectorIssue] = []

    def validate_selector(self, selector: str, workflow: str, step_id: str) -> List[SelectorIssue]:
        """Validate a single selector and return any issues found"""
        issues = []

        # Check for empty selector
        if not selector or not selector.strip():
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="empty_selector",
                severity="error",
                message="Empty selector found"
            ))
            return issues

        # Check for unbalanced quotes
        if selector.count("'") % 2 != 0 or selector.count('"') % 2 != 0:
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="unbalanced_quotes",
                severity="error",
                message="Unbalanced quotes in selector"
            ))

        # Check for unbalanced brackets
        if selector.count('[') != selector.count(']'):
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="unbalanced_brackets",
                severity="error",
                message="Unbalanced square brackets"
            ))

        if selector.count('(') != selector.count(')'):
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="unbalanced_parens",
                severity="error",
                message="Unbalanced parentheses"
            ))

        # Check for invalid role selector syntax
        if 'role=' in selector:
            role_match = re.search(r'role=(\w+)', selector)
            if role_match:
                role_value = role_match.group(1)
                if role_value not in self.VALID_ROLE_VALUES:
                    issues.append(SelectorIssue(
                        workflow=workflow,
                        step_id=step_id,
                        selector=selector,
                        issue_type="invalid_role",
                        severity="warning",
                        message=f"Unknown role value: {role_value}"
                    ))

        # Check for potentially fragile selectors (too specific IDs)
        if re.search(r'#[a-f0-9]{8,}', selector, re.IGNORECASE):
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="fragile_id",
                severity="warning",
                message="Selector uses what appears to be a generated/hash ID which may change"
            ))

        # Check for :has-text() without quotes
        has_text_match = re.search(r':has-text\(([^)]+)\)', selector)
        if has_text_match:
            text_content = has_text_match.group(1)
            if not (text_content.startswith("'") or text_content.startswith('"')):
                issues.append(SelectorIssue(
                    workflow=workflow,
                    step_id=step_id,
                    selector=selector,
                    issue_type="unquoted_text",
                    severity="warning",
                    message="Text in :has-text() should be quoted"
                ))

        # Check for data-automationid selectors (good practice)
        if 'data-automationid' in selector:
            issues.append(SelectorIssue(
                workflow=workflow,
                step_id=step_id,
                selector=selector,
                issue_type="uses_automationid",
                severity="info",
                message="Good: Uses data-automationid attribute (stable selector)"
            ))

        return issues

    def validate_workflow(self, workflow_path: Path) -> Tuple[str, List[SelectorIssue]]:
        """Validate all selectors in a workflow file"""
        issues = []
        workflow_name = workflow_path.stem

        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)

        steps = workflow.get('steps', [])

        for step in steps:
            step_id = step.get('id', 'unknown')

            # Check main selectors
            selectors = step.get('selectors', [])
            for selector in selectors:
                issues.extend(self.validate_selector(selector, workflow_name, step_id))

            # Check sub_steps for loop actions
            sub_steps = step.get('sub_steps', [])
            for sub_step in sub_steps:
                sub_step_id = sub_step.get('id', 'unknown')
                sub_selectors = sub_step.get('selectors', [])
                for selector in sub_selectors:
                    issues.extend(self.validate_selector(selector, workflow_name, f"{step_id}/{sub_step_id}"))

            # Check batch_ensure_checked checkboxes
            checkboxes = step.get('checkboxes', [])
            for checkbox in checkboxes:
                cb_selectors = checkbox.get('selectors', [])
                for selector in cb_selectors:
                    issues.extend(self.validate_selector(selector, workflow_name, f"{step_id}/checkbox"))

        return workflow_name, issues


class WorkflowAnalyzer:
    """Analyzes workflow YAML files for completeness and correctness"""

    EXPECTED_COLUMNS = {
        'trial_balance_report': 5,
        'profit_and_loss': 0,  # Uses options, not columns
        'aged_receivables_detail': 7,
        'aged_payables_detail': 6,
        'account_transactions': 15,
        'receivable_invoice_detail': 20,
        'payable_invoice_detail': 17,
    }

    REQUIRED_STEPS = {
        'reports': ['wait_for_reports_ready', 'click_update_button', 'click_export_button', 'click_excel_and_download'],
        'vat': ['wait_for_vat_page', 'process_vat_returns'],
    }

    def __init__(self, workflows_dir: Path):
        self.workflows_dir = workflows_dir
        self.workflows: Dict[str, Dict] = {}
        self._load_workflows()

    def _load_workflows(self):
        """Load all workflow YAML files"""
        for yaml_file in self.workflows_dir.glob('*.yaml'):
            with open(yaml_file, 'r') as f:
                self.workflows[yaml_file.stem] = yaml.safe_load(f)

    def count_columns(self, workflow_name: str) -> Tuple[int, int]:
        """Count columns enabled and disabled in a workflow"""
        workflow = self.workflows.get(workflow_name, {})
        enabled = 0
        disabled = 0

        for step in workflow.get('steps', []):
            # New select_columns action
            if step.get('action') == 'select_columns':
                enabled += len(step.get('columns', []))
            # Legacy batch_ensure_checked action (used for P&L options)
            elif step.get('action') == 'batch_ensure_checked':
                for checkbox in step.get('checkboxes', []):
                    if checkbox.get('checked', True):
                        enabled += 1
                    else:
                        disabled += 1

        return enabled, disabled

    def analyze_step_coverage(self, workflow_name: str) -> Dict[str, bool]:
        """Check if workflow has required steps"""
        workflow = self.workflows.get(workflow_name, {})
        step_ids = [step.get('id') for step in workflow.get('steps', [])]

        workflow_type = 'vat' if 'vat' in workflow_name else 'reports'
        required = self.REQUIRED_STEPS.get(workflow_type, [])

        coverage = {}
        for req_step in required:
            coverage[req_step] = req_step in step_ids

        return coverage

    def find_duplicate_selectors(self) -> Dict[str, List[str]]:
        """Find selectors used across multiple workflows"""
        selector_usage = defaultdict(list)

        for name, workflow in self.workflows.items():
            for step in workflow.get('steps', []):
                for selector in step.get('selectors', []):
                    selector_usage[selector].append(f"{name}:{step.get('id')}")

        return {k: v for k, v in selector_usage.items() if len(v) > 1}

    def validate_date_selection_pattern(self, workflow_name: str) -> List[str]:
        """Check if workflow follows the correct date selection pattern"""
        workflow = self.workflows.get(workflow_name, {})
        steps = workflow.get('steps', [])

        issues = []
        step_sequence = [s.get('id') for s in steps]

        # Check for proper date selection sequence
        if 'click_date_dropdown' in step_sequence:
            date_idx = step_sequence.index('click_date_dropdown')

            # Should have wait_for_date_options or wait_for_date_dropdown after click_date_dropdown
            has_wait = 'wait_for_date_options' in step_sequence or 'wait_for_date_dropdown' in step_sequence
            if not has_wait:
                issues.append("Missing date wait step - may cause race condition")
            else:
                # Find the wait step index
                wait_step = 'wait_for_date_options' if 'wait_for_date_options' in step_sequence else 'wait_for_date_dropdown'
                wait_idx = step_sequence.index(wait_step)
                if wait_idx != date_idx + 1:
                    issues.append(f"'{wait_step}' should immediately follow 'click_date_dropdown'")

            # Should have select_last_financial_year or select_end_of_last_financial_year after wait
            has_date_select = (
                'select_last_financial_year' in step_sequence or
                'select_end_of_last_financial_year' in step_sequence
            )
            if not has_date_select:
                issues.append("Missing date selection step (select_last_financial_year or select_end_of_last_financial_year)")

        return issues

    def get_full_report(self) -> str:
        """Generate a comprehensive analysis report"""
        lines = []
        lines.append("=" * 80)
        lines.append("WORKFLOW ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Column verification
        lines.append("COLUMN COUNT VERIFICATION")
        lines.append("-" * 40)
        for name, expected in self.EXPECTED_COLUMNS.items():
            if name in self.workflows:
                actual_enabled, actual_disabled = self.count_columns(name)
                status = "✅" if actual_enabled == expected else "❌"
                lines.append(f"{status} {name}: Expected {expected}, Found {actual_enabled} enabled ({actual_disabled} disabled)")
            else:
                lines.append(f"⚠️ {name}: Workflow not found")
        lines.append("")

        # Date selection pattern
        lines.append("DATE SELECTION PATTERN CHECK")
        lines.append("-" * 40)
        for name in self.workflows:
            issues = self.validate_date_selection_pattern(name)
            if issues:
                lines.append(f"❌ {name}:")
                for issue in issues:
                    lines.append(f"   - {issue}")
            else:
                lines.append(f"✅ {name}: Correct date selection pattern")
        lines.append("")

        # Step coverage
        lines.append("REQUIRED STEP COVERAGE")
        lines.append("-" * 40)
        for name in self.workflows:
            coverage = self.analyze_step_coverage(name)
            missing = [k for k, v in coverage.items() if not v]
            if missing:
                lines.append(f"❌ {name}: Missing steps: {', '.join(missing)}")
            else:
                lines.append(f"✅ {name}: All required steps present")
        lines.append("")

        return "\n".join(lines)


# Test fixtures
@pytest.fixture
def workflows_dir():
    return Path(__file__).parent.parent / "workflows"


@pytest.fixture
def validator():
    return SelectorValidator()


@pytest.fixture
def analyzer(workflows_dir):
    return WorkflowAnalyzer(workflows_dir)


# Tests
class TestSelectorSyntax:
    """Test selector syntax validation"""

    def test_all_selectors_valid_syntax(self, workflows_dir, validator):
        """Verify all selectors have valid syntax"""
        errors = []

        for yaml_file in workflows_dir.glob('*.yaml'):
            workflow_name, issues = validator.validate_workflow(yaml_file)
            for issue in issues:
                if issue.severity == 'error':
                    errors.append(f"{issue.workflow}/{issue.step_id}: {issue.message} - {issue.selector}")

        assert len(errors) == 0, f"Found {len(errors)} syntax errors:\n" + "\n".join(errors)

    def test_no_unbalanced_brackets(self, workflows_dir, validator):
        """Check for unbalanced brackets in selectors"""
        bracket_errors = []

        for yaml_file in workflows_dir.glob('*.yaml'):
            _, issues = validator.validate_workflow(yaml_file)
            for issue in issues:
                if issue.issue_type in ['unbalanced_brackets', 'unbalanced_parens', 'unbalanced_quotes']:
                    bracket_errors.append(f"{issue.workflow}/{issue.step_id}: {issue.selector}")

        assert len(bracket_errors) == 0, f"Found unbalanced brackets:\n" + "\n".join(bracket_errors)


class TestColumnCounts:
    """Test column configuration in workflows"""

    @pytest.mark.parametrize("workflow_name,expected_columns", [
        ("trial_balance_report", 5),
        ("aged_receivables_detail", 7),
        ("aged_payables_detail", 6),
        ("account_transactions", 11),
        ("receivable_invoice_detail", 20),
        ("payable_invoice_detail", 17),
    ])
    def test_column_count(self, analyzer, workflow_name, expected_columns):
        """Verify each workflow has the expected number of columns enabled"""
        enabled, _ = analyzer.count_columns(workflow_name)
        assert enabled == expected_columns, (
            f"{workflow_name}: Expected {expected_columns} columns, found {enabled}"
        )


class TestDateSelectionPattern:
    """Test date selection follows correct pattern to avoid race conditions"""

    @pytest.mark.parametrize("workflow_name", [
        "trial_balance_report",
        "profit_and_loss",
        "aged_receivables_detail",
        "aged_payables_detail",
        "account_transactions",
        "receivable_invoice_detail",
        "payable_invoice_detail",
        "get_financial_year_end",
    ])
    def test_date_selection_has_wait(self, analyzer, workflow_name):
        """Verify date wait step exists after click_date_dropdown"""
        issues = analyzer.validate_date_selection_pattern(workflow_name)
        assert len(issues) == 0, f"{workflow_name}: {'; '.join(issues)}"


class TestRequiredSteps:
    """Test workflows have all required steps"""

    @pytest.mark.parametrize("workflow_name", [
        "trial_balance_report",
        "profit_and_loss",
        "aged_receivables_detail",
        "aged_payables_detail",
        "account_transactions",
        "receivable_invoice_detail",
        "payable_invoice_detail",
    ])
    def test_required_steps_present(self, analyzer, workflow_name):
        """Verify workflow has all required steps"""
        coverage = analyzer.analyze_step_coverage(workflow_name)
        missing = [k for k, v in coverage.items() if not v]
        assert len(missing) == 0, f"{workflow_name}: Missing required steps: {missing}"


class TestSelectorConsistency:
    """Test selector patterns are consistent across workflows"""

    def test_date_dropdown_selector_consistent(self, workflows_dir):
        """Verify date dropdown uses consistent selector across workflows"""
        date_selectors = []

        for yaml_file in workflows_dir.glob('*.yaml'):
            with open(yaml_file, 'r') as f:
                workflow = yaml.safe_load(f)

            for step in workflow.get('steps', []):
                if step.get('id') == 'click_date_dropdown':
                    date_selectors.append({
                        'workflow': yaml_file.stem,
                        'selectors': step.get('selectors', [])
                    })

        # All date dropdowns should have similar selectors
        if date_selectors:
            first_selectors = set(date_selectors[0]['selectors'])
            for item in date_selectors[1:]:
                current_selectors = set(item['selectors'])
                # At least one selector should match
                assert first_selectors & current_selectors, (
                    f"Inconsistent date dropdown selectors: "
                    f"{date_selectors[0]['workflow']} vs {item['workflow']}"
                )

    def test_export_button_selector_consistent(self, workflows_dir):
        """Verify export button uses consistent selector across workflows"""
        export_selectors = []

        for yaml_file in workflows_dir.glob('*.yaml'):
            with open(yaml_file, 'r') as f:
                workflow = yaml.safe_load(f)

            for step in workflow.get('steps', []):
                if step.get('id') == 'click_export_button':
                    export_selectors.append({
                        'workflow': yaml_file.stem,
                        'selectors': step.get('selectors', [])
                    })

        if len(export_selectors) > 1:
            first = set(export_selectors[0]['selectors'])
            for item in export_selectors[1:]:
                current = set(item['selectors'])
                assert first & current, (
                    f"Inconsistent export button selectors: "
                    f"{export_selectors[0]['workflow']} vs {item['workflow']}"
                )


class TestVATWorkflow:
    """Test VAT-specific workflow configurations"""

    def test_vat_has_skip_conditions(self, workflows_dir):
        """Verify VAT workflow has proper skip condition handling"""
        vat_file = workflows_dir / "vat_returns_export.yaml"
        if not vat_file.exists():
            pytest.skip("VAT workflow not found")

        with open(vat_file, 'r') as f:
            workflow = yaml.safe_load(f)

        # Check for loop_vat_returns action
        has_loop = False
        for step in workflow.get('steps', []):
            if step.get('action') == 'loop_vat_returns':
                has_loop = True
                break

        assert has_loop, "VAT workflow should have loop_vat_returns action"


def run_full_analysis():
    """Run complete analysis and print report"""
    workflows_dir = Path(__file__).parent.parent / "workflows"

    print("\n" + "=" * 80)
    print("RUNNING FULL SELECTOR ANALYSIS")
    print("=" * 80 + "\n")

    # Run selector validation
    validator = SelectorValidator()
    all_issues = []

    for yaml_file in workflows_dir.glob('*.yaml'):
        workflow_name, issues = validator.validate_workflow(yaml_file)
        all_issues.extend(issues)

        error_count = len([i for i in issues if i.severity == 'error'])
        warning_count = len([i for i in issues if i.severity == 'warning'])
        info_count = len([i for i in issues if i.severity == 'info'])

        status = "✅" if error_count == 0 else "❌"
        print(f"{status} {workflow_name}: {error_count} errors, {warning_count} warnings, {info_count} info")

    # Print detailed issues
    errors = [i for i in all_issues if i.severity == 'error']
    warnings = [i for i in all_issues if i.severity == 'warning']

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for issue in errors:
            print(f"  - {issue.workflow}/{issue.step_id}: {issue.message}")
            print(f"    Selector: {issue.selector[:80]}...")

    if warnings:
        print(f"\n⚠️ WARNINGS ({len(warnings)}):")
        for issue in warnings:
            print(f"  - {issue.workflow}/{issue.step_id}: {issue.message}")

    # Run workflow analysis
    print("\n")
    analyzer = WorkflowAnalyzer(workflows_dir)
    print(analyzer.get_full_report())

    return len(errors) == 0


if __name__ == "__main__":
    success = run_full_analysis()
    exit(0 if success else 1)
