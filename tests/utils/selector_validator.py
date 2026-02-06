"""
Selector validation utilities for E2E testing.
"""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Page, Locator


@dataclass
class SelectorResult:
    selector: str
    found: bool
    visible: bool
    element_count: int
    tag_name: str | None = None
    text_content: str | None = None
    attributes: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class StepValidationResult:
    step_id: str
    action: str
    description: str
    selectors: list[str]
    selector_results: list[SelectorResult]
    passed: bool
    first_working_selector: str | None = None


@dataclass
class WorkflowValidationReport:
    workflow_name: str
    total_steps: int
    steps_with_selectors: int
    steps_passed: int
    steps_failed: int
    step_results: list[StepValidationResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.steps_with_selectors == 0:
            return 100.0
        return (self.steps_passed / self.steps_with_selectors) * 100


class SelectorValidator:
    def __init__(self, page: Page, timeout: int = 5000):
        self.page = page
        self.timeout = timeout

    async def validate_selector(self, selector: str) -> SelectorResult:
        """Validate a single selector against the current page."""
        result = SelectorResult(
            selector=selector,
            found=False,
            visible=False,
            element_count=0,
        )

        try:
            locator = self.page.locator(selector)
            count = await locator.count()
            result.element_count = count

            if count > 0:
                result.found = True
                first_element = locator.first

                try:
                    result.visible = await first_element.is_visible(timeout=self.timeout)
                except Exception:
                    result.visible = False

                if result.visible:
                    try:
                        result.tag_name = await first_element.evaluate("el => el.tagName.toLowerCase()")
                        result.text_content = await first_element.text_content()
                        if result.text_content:
                            result.text_content = result.text_content[:100].strip()

                        attrs = await first_element.evaluate("""el => {
                            const attrs = {};
                            for (const attr of el.attributes) {
                                if (['id', 'class', 'data-automationid', 'aria-label', 'role', 'type'].includes(attr.name)) {
                                    attrs[attr.name] = attr.value;
                                }
                            }
                            return attrs;
                        }""")
                        result.attributes = attrs
                    except Exception:
                        pass

        except Exception as e:
            result.error = str(e)

        return result

    async def validate_selectors(self, selectors: list[str]) -> list[SelectorResult]:
        """Validate multiple selectors against the current page."""
        results = []
        for selector in selectors:
            result = await self.validate_selector(selector)
            results.append(result)
        return results

    async def find_first_working_selector(self, selectors: list[str]) -> tuple[str | None, SelectorResult | None]:
        """Find the first selector that matches a visible element."""
        for selector in selectors:
            result = await self.validate_selector(selector)
            if result.found and result.visible:
                return selector, result
        return None, None


class WorkflowValidator:
    def __init__(self, page: Page, timeout: int = 5000):
        self.page = page
        self.validator = SelectorValidator(page, timeout)

    def load_workflow(self, workflow_path: Path) -> dict:
        """Load a workflow YAML file."""
        with open(workflow_path) as f:
            return yaml.safe_load(f)

    def get_steps_with_selectors(self, workflow: dict) -> list[dict]:
        """Extract steps that have selectors to validate."""
        steps_with_selectors = []
        for step in workflow.get("steps", []):
            selectors = step.get("selectors", [])
            checkboxes = step.get("checkboxes", [])

            if selectors:
                steps_with_selectors.append(step)
            elif checkboxes:
                steps_with_selectors.append(step)

        return steps_with_selectors

    async def validate_step(self, step: dict) -> StepValidationResult:
        """Validate all selectors in a workflow step."""
        step_id = step.get("id", "unknown")
        action = step.get("action", "unknown")
        description = step.get("description", "")
        selectors = step.get("selectors", [])

        if step.get("checkboxes"):
            selectors = []
            for checkbox in step["checkboxes"]:
                selectors.extend(checkbox.get("selectors", []))

        selector_results = await self.validator.validate_selectors(selectors)
        first_working, _ = await self.validator.find_first_working_selector(selectors)

        passed = first_working is not None or step.get("optional", False)

        return StepValidationResult(
            step_id=step_id,
            action=action,
            description=description,
            selectors=selectors,
            selector_results=selector_results,
            passed=passed,
            first_working_selector=first_working,
        )

    async def validate_workflow(self, workflow_path: Path) -> WorkflowValidationReport:
        """Validate all selectors in a workflow against the current page."""
        workflow = self.load_workflow(workflow_path)
        workflow_name = workflow.get("name", workflow_path.stem)
        all_steps = workflow.get("steps", [])
        steps_with_selectors = self.get_steps_with_selectors(workflow)

        report = WorkflowValidationReport(
            workflow_name=workflow_name,
            total_steps=len(all_steps),
            steps_with_selectors=len(steps_with_selectors),
            steps_passed=0,
            steps_failed=0,
        )

        for step in steps_with_selectors:
            result = await self.validate_step(step)
            report.step_results.append(result)

            if result.passed:
                report.steps_passed += 1
            else:
                report.steps_failed += 1

        return report


def print_validation_report(report: WorkflowValidationReport):
    """Print a human-readable validation report."""
    print("\n" + "=" * 70)
    print(f"WORKFLOW VALIDATION REPORT: {report.workflow_name}")
    print("=" * 70)
    print(f"Total steps: {report.total_steps}")
    print(f"Steps with selectors: {report.steps_with_selectors}")
    print(f"Passed: {report.steps_passed}")
    print(f"Failed: {report.steps_failed}")
    print(f"Success rate: {report.success_rate:.1f}%")
    print("-" * 70)

    for result in report.step_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"\n[{status}] Step: {result.step_id}")
        print(f"       Action: {result.action}")
        print(f"       Description: {result.description}")

        if result.first_working_selector:
            print(f"       Working selector: {result.first_working_selector}")
        else:
            print("       No working selector found!")

        for sr in result.selector_results:
            found_status = "Found" if sr.found else "Not found"
            visible_status = "Visible" if sr.visible else "Not visible"
            print(f"         - {sr.selector}")
            print(f"           {found_status}, {visible_status}, Count: {sr.element_count}")
            if sr.error:
                print(f"           Error: {sr.error}")

    print("\n" + "=" * 70)
