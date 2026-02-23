import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Page, BrowserContext, async_playwright

from src.utils.logger import get_logger
from src.engine.report_generator import WorkflowReportGenerator


class StepFailedError(Exception):
    """Raised when a workflow step fails and should stop execution."""
    pass


@dataclass
class WorkflowState:
    variables: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


class WorkflowEngine:
    def __init__(self, workflow_path: Path, env_vars: dict[str, str] | None = None):
        self.workflow_path = workflow_path
        self.workflow = self._load_workflow()
        self.env_vars = env_vars or dict(os.environ)
        self.log = get_logger("WorkflowEngine")
        self.state = WorkflowState()
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self.log_callback = None
        self.variable_callback = None
        self.report = WorkflowReportGenerator()
        self.generate_report = True

    async def _emit_log(self, level: str, message: str, **kwargs):
        self.log.info(message, **kwargs) if level == "info" else (
            self.log.warning(message, **kwargs) if level == "warning" else
            self.log.error(message, **kwargs) if level == "error" else
            self.log.info(message, **kwargs)
        )
        if self.log_callback:
            try:
                await self.log_callback(level, message, **kwargs)
            except Exception:
                pass

    async def _emit_variables(self):
        if self.variable_callback:
            try:
                await self.variable_callback(dict(self.state.variables))
            except Exception:
                pass

    async def _store_variable(self, key: str, value: Any):
        self.state.variables[key] = value
        await self._emit_variables()

        filter_keywords = ['date', 'period', 'year', 'client', 'company', 'column']
        if any(kw in key.lower() for kw in filter_keywords):
            self.report.log_filter(key, str(value))

    def _load_workflow(self) -> dict:
        with open(self.workflow_path) as f:
            if self.workflow_path.suffix in ('.yaml', '.yml'):
                return yaml.safe_load(f)
            return json.load(f)

    def _parse_date(self, date_str: str) -> datetime | None:
        formats = [
            '%d %b %Y',      # 31 Mar 2025
            '%d %B %Y',      # 31 March 2025
            '%Y-%m-%d',      # 2025-03-31
            '%d/%m/%Y',      # 31/03/2025
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def _format_date(self, dt: datetime, fmt: str = '%d %b %Y') -> str:
        return dt.strftime(fmt)

    def _resolve_variable(self, value: str) -> str:
        if not isinstance(value, str):
            return value

        # Handle special date expressions: ${TODAY}, ${DATE_ADD:var_name:days}
        today_pattern = r'\$\{TODAY(?::([^}]+))?\}'
        def replace_today(match):
            fmt = match.group(1) or '%d %b %Y'
            return self._format_date(datetime.now(), fmt)

        value = re.sub(today_pattern, replace_today, value)

        # Handle DATE_ADD: ${DATE_ADD:var_name:days} or ${DATE_ADD:var_name:days:format}
        date_add_pattern = r'\$\{DATE_ADD:(\w+):(-?\d+)(?::([^}]+))?\}'
        def replace_date_add(match):
            var_name = match.group(1)
            days = int(match.group(2))
            fmt = match.group(3) or '%d %b %Y'
            date_str = self.state.variables.get(var_name, '')
            if not date_str:
                return ''
            dt = self._parse_date(date_str)
            if dt:
                new_dt = dt + timedelta(days=days)
                return self._format_date(new_dt, fmt)
            return ''

        value = re.sub(date_add_pattern, replace_date_add, value)

        # Handle standard variable substitution
        pattern = r'\$\{(\w+)\}'
        def replace(match):
            var_name = match.group(1)
            return self.env_vars.get(var_name, self.state.variables.get(var_name, ''))

        return re.sub(pattern, replace, value)

    def _get_step_by_id(self, step_id: str) -> dict | None:
        for step in self.workflow.get('steps', []):
            if step.get('id') == step_id:
                return step
        return None

    def _get_step_index(self, step_id: str) -> int:
        for i, step in enumerate(self.workflow.get('steps', [])):
            if step.get('id') == step_id:
                return i
        return -1

    async def _try_selectors(self, selectors: list[str], action: str = 'find') -> Any:
        if isinstance(selectors, str):
            selectors = [selectors]

        for selector in selectors:
            try:
                element = self._page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    if action == 'find':
                        return element
                    elif action == 'click':
                        await element.click()
                        return True
            except Exception:
                continue
        return None

    async def _execute_goto(self, step: dict) -> str | None:
        url = self._resolve_variable(step['url'])
        wait_until = step.get('wait_until', 'domcontentloaded')
        timeout = step.get('timeout', 30000)

        current_url = self._page.url
        await self._emit_log("info", f"🌐 Navigating from: {current_url}")
        await self._emit_log("info", f"🌐 Navigating to: {url}")

        try:
            response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)
            await asyncio.sleep(step.get('wait_after', 1000) / 1000)

            new_url = self._page.url
            await self._emit_log("info", f"   📍 Now at: {new_url}")

            if new_url == current_url and url not in current_url:
                await self._emit_log("warning", f"   ⚠️  Page URL unchanged, trying reload...")
                await self._page.evaluate(f"window.location.href = '{url}'")
                await asyncio.sleep(2)
                await self._page.wait_for_load_state('domcontentloaded', timeout=timeout)
                new_url = self._page.url
                await self._emit_log("info", f"   📍 After reload: {new_url}")

            await self._emit_log("info", f"   ✅ Page loaded successfully")
            return None
        except Exception as e:
            await self._emit_log("error", f"   ❌ Navigation failed: {str(e)}")
            return step.get('on_error')

    async def _execute_fill(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        value = self._resolve_variable(step.get('value', ''))
        timeout = step.get('timeout', 10000)

        await self._emit_log("info", f"⌨️  Filling input with: '{value}'")

        for selector in selectors:
            try:
                element = self._page.locator(selector)
                if step.get('wait_visible'):
                    await element.wait_for(state='visible', timeout=timeout)
                await element.fill(value)
                await self._emit_log("info", f"   ✅ Input filled successfully")
                if step.get('wait_after'):
                    await asyncio.sleep(step['wait_after'] / 1000)
                return None
            except Exception:
                continue

        await self._emit_log("error", f"   ❌ No matching input field found")
        if not step.get('optional'):
            raise StepFailedError(f"No matching selector found for fill: {selectors}")
        return step.get('on_error')

    async def _execute_press_key(self, step: dict) -> str | None:
        key = step.get('key', 'Enter')

        await self._emit_log("info", f"⌨️  Pressing key: '{key}'")

        try:
            await self._page.keyboard.press(key)
            await self._emit_log("info", f"   ✅ Key pressed successfully")
            if step.get('wait_after'):
                await asyncio.sleep(step['wait_after'] / 1000)
            return None
        except Exception as e:
            await self._emit_log("error", f"   ❌ Failed to press key: {str(e)}")
            if not step.get('optional'):
                raise StepFailedError(f"Failed to press key '{key}': {str(e)}")
            return step.get('on_error')

    async def _execute_click(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        description = step.get('description', '')

        button_name = ''
        if selectors:
            match = re.search(r"has-text\(['\"](.+?)['\"]\)", selectors[0])
            if match:
                button_name = match.group(1)

        if button_name:
            await self._emit_log("info", f"🖱️  Clicking: '{button_name}'")
        else:
            await self._emit_log("info", f"🖱️  Clicking element...")

        for selector in selectors:
            try:
                resolved_selector = self._resolve_variable(selector)
                element = self._page.locator(resolved_selector).first
                if await element.is_visible(timeout=5000):
                    if step.get('expect_popup') or step.get('expect_new_tab'):
                        async with self._page.context.expect_page(timeout=10000) as new_page_info:
                            await element.click()
                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state('domcontentloaded')
                        self._page = new_page
                        await self._emit_log("info", f"   ✅ Click opened new tab: {new_page.url}")
                    else:
                        await element.click()
                        if step.get('wait_after'):
                            await asyncio.sleep(step['wait_after'] / 1000)
                        await self._emit_log("info", f"   ✅ Click successful")
                    return None
            except Exception:
                continue

        await self._emit_log("error", f"   ❌ Could not find element to click")
        if not step.get('optional'):
            raise StepFailedError(f"No matching selector found for click: {selectors}")
        return step.get('on_error')

    async def _execute_check_url(self, step: dict) -> str | None:
        current_url = self._page.url.lower()
        await self._emit_log("info", f"🔍 Checking current URL...")

        for condition in step.get('conditions', []):
            if condition.get('contains') and condition['contains'].lower() in current_url:
                return condition.get('goto_step')
            if condition.get('matches'):
                if re.search(condition['matches'], current_url):
                    return condition.get('goto_step')

        return step.get('default_step')

    async def _execute_wait_for_url(self, step: dict) -> str | None:
        patterns = step.get('patterns', [])
        timeout = step.get('timeout', 30000)

        await self._emit_log("info", f"⏳ Waiting for page to load...")

        for pattern in patterns:
            try:
                await self._page.wait_for_url(pattern, timeout=timeout)
                await self._emit_log("info", f"   ✅ Page ready")
                return None
            except Exception:
                continue

        current_url = self._page.url if self._page else "unknown"
        await self._emit_log("error", f"   ❌ Page load timeout (URL: {current_url})")
        try:
            screenshot_path = f"downloads/debug_{step.get('id', 'unknown')}.png"
            await self._page.screenshot(path=screenshot_path)
            await self._emit_log("warning", f"   Debug screenshot saved: {screenshot_path}")
        except Exception:
            pass
        if not step.get('optional'):
            raise StepFailedError(f"Timeout waiting for URL pattern: {patterns}")
        return step.get('on_timeout')

    async def _execute_capture_state(self, step: dict) -> str | None:
        save_config = step.get('save', {})

        await self._emit_log("info", "📸 Capturing page state...")

        if 'url' in save_config:
            await self._store_variable(save_config['url'], self._page.url)
            await self._emit_log("info", f"   🔗 Saved URL: {self._page.url}")

        if 'screenshot' in save_config:
            path = Path(save_config['screenshot'])
            await self._page.screenshot(path=str(path), full_page=True)
            await self._emit_log("info", f"   🖼️  Screenshot saved: {path}")

        if 'html' in save_config:
            path = Path(save_config['html'])
            html = await self._page.content()
            path.write_text(html)
            await self._emit_log("info", f"   📄 HTML saved: {path}")

        await self._emit_log("info", "   ✅ State captured")
        return None

    async def _execute_scrape(self, step: dict) -> str | None:
        target = step.get('target', 'scraped_data')
        await self._emit_log("info", f"🔎 Scraping data: {target}")

        container_selectors = step.get('container', {}).get('selectors', [])
        item_selectors = step.get('items', {}).get('selectors', [])
        fields_config = step.get('fields', {})

        container = await self._try_selectors(container_selectors)
        if not container:
            await self._emit_log("info", "   ⚠️  Container not found, using page body")
            container = self._page.locator('body')

        items = []
        for item_selector in item_selectors:
            try:
                rows = container.locator(item_selector)
                count = await rows.count()
                await self._emit_log("info", f"   📊 Found {count} items")

                for i in range(count):
                    row = rows.nth(i)
                    item_data = {}

                    for field_name, field_config in fields_config.items():
                        for sel in field_config.get('selectors', []):
                            try:
                                el = row.locator(sel).first
                                if await el.is_visible(timeout=1000):
                                    attr = field_config.get('attribute', 'textContent')
                                    if attr == 'textContent':
                                        value = await el.text_content()
                                    else:
                                        value = await el.get_attribute(attr)

                                    if value and field_config.get('extract_pattern'):
                                        match = re.search(field_config['extract_pattern'], value)
                                        if match:
                                            value = match.group(1)

                                    item_data[field_name] = value.strip() if value else None
                                    break
                            except Exception:
                                continue

                    if item_data and any(item_data.values()):
                        items.append(item_data)

                if items:
                    break
            except Exception as e:
                await self._emit_log("warning", f"   ⚠️  Scrape attempt failed: {str(e)}")

        self.state.results[target] = items
        await self._emit_log("info", f"   ✅ Scraped {len(items)} items")

        if step.get('save_to'):
            save_path = Path(step['save_to'])
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w') as f:
                json.dump({
                    'items': items,
                    'scraped_at': datetime.now().isoformat(),
                    'source_url': self._page.url
                }, f, indent=2)
            await self._emit_log("info", f"   💾 Data saved to: {save_path}")

        return None

    async def _execute_manual_intervention(self, step: dict) -> str | None:
        message = step.get('message', 'Manual action required')

        await self._emit_log("warning", "")
        await self._emit_log("warning", "═" * 50)
        await self._emit_log("warning", f"⚠️  MANUAL ACTION REQUIRED")
        await self._emit_log("warning", f"   {message}")
        await self._emit_log("warning", "═" * 50)
        await self._emit_log("warning", "")

        if step.get('wait_for_url'):
            timeout = step.get('timeout', 120000)
            await self._emit_log("info", f"⏳ Waiting for manual completion...")
            await self._page.wait_for_url(step['wait_for_url'], timeout=timeout)
            await self._emit_log("info", f"   ✅ Manual action completed")

        return None

    async def _execute_ensure_checked(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        should_be_checked = step.get('checked', True)
        state_text = "checked" if should_be_checked else "unchecked"

        await self._emit_log("info", f"☑️  Ensuring checkbox is {state_text}...")

        for selector in selectors:
            try:
                element = self._page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    is_checked = await element.is_checked()
                    if is_checked != should_be_checked:
                        await element.click()
                        await self._emit_log("info", f"   🔄 Toggled checkbox to {state_text}")
                    else:
                        await self._emit_log("info", f"   ✅ Checkbox already {state_text}")
                    if step.get('wait_after'):
                        await asyncio.sleep(step['wait_after'] / 1000)
                    return None
            except Exception:
                continue

        await self._emit_log("error", f"   ❌ No matching checkbox found")
        if not step.get('optional'):
            raise StepFailedError(f"No matching checkbox found: {step.get('selectors', [])}")
        return step.get('on_error')

    async def _execute_batch_ensure_checked(self, step: dict) -> str | None:
        """Set multiple checkboxes to their desired state."""
        checkboxes = step.get('checkboxes', [])
        await self._emit_log("info", f"☑️  Setting {len(checkboxes)} options...")

        success_count = 0
        failed_count = 0

        for item in checkboxes:
            should_be_checked = item.get('checked', True)
            selectors = item.get('selectors', [])

            found = False
            for selector in selectors:
                if selector.startswith('role='):
                    continue

                try:
                    cb = self._page.locator(selector).first
                    if await cb.is_visible(timeout=2000):
                        is_checked = await cb.get_attribute('aria-checked') == 'true'
                        if is_checked != should_be_checked:
                            await cb.click()
                            await asyncio.sleep(0.1)
                        success_count += 1
                        found = True
                        break
                except Exception:
                    continue

            if not found:
                failed_count += 1

        await self._emit_log("info", f"   ✅ {success_count} options set, {failed_count} failed")

        if step.get('wait_after'):
            await asyncio.sleep(step['wait_after'] / 1000)
        return None

    async def _execute_deselect_all_columns(self, step: dict) -> str | None:
        """Deselect all column checkboxes except required ones."""
        required_columns = step.get('except', [])
        await self._emit_log("info", f"☑️  Deselecting all columns...")

        # Find all checked column checkboxes - only --body--checkbox contains input
        js_get_checked = """
        () => {
            const labels = document.querySelectorAll('[data-automationid*="--body--checkbox"]');
            const checked = [];
            for (const label of labels) {
                const input = label.querySelector('input[type="checkbox"]');
                if (input && input.checked) {
                    checked.push(label.getAttribute('data-automationid'));
                }
            }
            return checked;
        }
        """
        checked_columns = await self._page.evaluate(js_get_checked)

        # Filter out required columns
        to_deselect = [c for c in checked_columns if c not in required_columns]

        if to_deselect:
            await self._emit_log("info", f"   🔄 Deselecting {len(to_deselect)} columns...")
            for automationid in to_deselect:
                try:
                    selector = f"[data-automationid='{automationid}']"
                    cb = self._page.locator(selector).first
                    await cb.scroll_into_view_if_needed()
                    await asyncio.sleep(0.05)
                    await cb.click()
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            await self._emit_log("info", f"   ✅ Deselected {len(to_deselect)} columns")
        else:
            await self._emit_log("info", f"   ✅ No columns to deselect")

        if step.get('wait_after'):
            await asyncio.sleep(step['wait_after'] / 1000)
        return None

    async def _execute_select_columns(self, step: dict) -> str | None:
        """Deselect ALL columns first, then select only the required ones."""
        columns = step.get('columns', [])
        required_selectors = [col.get('selector') for col in columns if col.get('selector')]

        await self._emit_log("info", f"☑️  Setting {len(columns)} columns...")

        # Step 1: Deselect all columns that are NOT in our required list
        js_get_checked = """
        () => {
            const labels = document.querySelectorAll('[data-automationid*="--body--checkbox"]');
            const checked = [];
            for (const label of labels) {
                const input = label.querySelector('input[type="checkbox"]');
                if (input && input.checked) {
                    checked.push({
                        automationid: label.getAttribute('data-automationid'),
                        selector: '[data-automationid=\"' + label.getAttribute('data-automationid') + '\"]'
                    });
                }
            }
            return checked;
        }
        """
        checked_cols = await self._page.evaluate(js_get_checked)

        # Only deselect columns that are NOT in our required list
        to_deselect = [c for c in checked_cols if c['selector'] not in required_selectors]

        if to_deselect:
            await self._emit_log("info", f"   🔄 Deselecting {len(to_deselect)} unwanted columns...")
            for col_info in to_deselect:
                try:
                    cb = self._page.locator(col_info['selector']).first
                    await cb.scroll_into_view_if_needed(timeout=3000)
                    await asyncio.sleep(0.15)
                    await cb.click(timeout=3000)
                    await asyncio.sleep(0.2)
                except Exception:
                    pass

        # Step 2: Select required columns that are NOT already checked
        await self._emit_log("info", f"   ✅ Selecting {len(columns)} required columns...")
        success_count = 0
        failed_count = 0

        # Get currently checked columns
        checked_now = await self._page.evaluate(js_get_checked)
        checked_selectors = [c['selector'] for c in checked_now]

        for col in columns:
            selector = col.get('selector')
            name = col.get('name', selector)

            if not selector:
                failed_count += 1
                continue

            try:
                if selector in checked_selectors:
                    await self._emit_log("info", f"      ✅ {name} (already selected)")
                else:
                    cb = self._page.locator(selector).first
                    await cb.scroll_into_view_if_needed(timeout=3000)
                    await asyncio.sleep(0.15)
                    await cb.click(timeout=3000)
                    await asyncio.sleep(0.2)
                    await self._emit_log("info", f"      ✅ {name}")
                success_count += 1
            except Exception as e:
                failed_count += 1
                await self._emit_log("warning", f"      ❌ {name} - {str(e)}")

        await self._emit_log("info", f"   📊 {success_count}/{len(columns)} columns selected")

        if step.get('wait_after'):
            await asyncio.sleep(step['wait_after'] / 1000)

        if failed_count > 0 and not step.get('optional'):
            raise StepFailedError(f"Failed to select {failed_count} columns")
        return None

    async def _wait_for_network_idle(self, timeout: int = 5000, idle_time: int = 500) -> None:
        """Wait for network to be idle (no requests for idle_time ms)."""
        try:
            await self._page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception:
            pass

    async def _execute_wait_for_selector(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        timeout = step.get('timeout', 30000)
        description = step.get('description', '')

        element_hint = ''
        if selectors:
            match = re.search(r"has-text\(['\"](.+?)['\"]\)", selectors[0])
            if match:
                element_hint = f"'{match.group(1)}'"

        if element_hint:
            await self._emit_log("info", f"⏳ Waiting for element: {element_hint}")
        else:
            await self._emit_log("info", f"⏳ Waiting for page element to appear...")

        for selector in selectors:
            try:
                resolved_selector = self._resolve_variable(selector)
                await self._page.wait_for_selector(resolved_selector, state='visible', timeout=timeout)
                await self._emit_log("info", f"   ✅ Element found and visible")
                return None
            except Exception:
                continue

        current_url = self._page.url if self._page else "unknown"
        await self._emit_log("error", f"   ❌ Element not found within timeout (URL: {current_url})")
        try:
            screenshot_path = f"downloads/debug_{step.get('id', 'unknown')}.png"
            await self._page.screenshot(path=screenshot_path)
            await self._emit_log("warning", f"   Debug screenshot saved: {screenshot_path}")
        except Exception:
            pass
        if not step.get('optional'):
            raise StepFailedError(f"Timeout waiting for selector: {selectors}")
        return step.get('on_timeout')

    async def _execute_read_input(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        save_as = step.get('save_as')
        timeout = step.get('timeout', 5000)

        await self._emit_log("info", f"📖 Reading input value...")

        for selector in selectors:
            try:
                element = self._page.locator(selector).first
                if await element.is_visible(timeout=timeout):
                    value = await element.input_value()
                    if save_as:
                        await self._store_variable(save_as, value)
                        await self._emit_log("info", f"   💾 Saved '{save_as}' = '{value}'")
                    else:
                        await self._emit_log("info", f"   📝 Value: '{value}'")
                    return None
            except Exception:
                continue

        await self._emit_log("error", f"   ❌ No matching input found")
        if not step.get('optional'):
            raise StepFailedError(f"No matching input found: {selectors}")
        return step.get('on_error')

    async def _execute_read_text(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        save_as = step.get('save_as')
        timeout = step.get('timeout', 5000)
        extract_pattern = step.get('extract_pattern')

        await self._emit_log("info", f"📖 Reading text from page...")

        for selector in selectors:
            try:
                element = self._page.locator(selector).first
                if await element.is_visible(timeout=timeout):
                    tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name == 'input':
                        value = await element.input_value()
                    else:
                        value = await element.text_content()

                    if value:
                        value = value.strip()
                        if extract_pattern:
                            match = re.search(extract_pattern, value)
                            if match:
                                value = match.group(1) if match.groups() else match.group(0)
                        if save_as and value:
                            await self._store_variable(save_as, value)
                            await self._emit_log("info", f"   💾 Saved '{save_as}' = '{value}'")
                        else:
                            await self._emit_log("info", f"   📝 Value: '{value}'")
                        return None
            except Exception:
                continue

        await self._emit_log("error", f"   ❌ No matching element found")
        if not step.get('optional'):
            raise StepFailedError(f"No matching element found: {selectors}")
        return step.get('on_error')

    def _extract_date_from_range(self, text: str, mode: str = 'start') -> datetime | None:
        text = text.strip()
        if ' - ' in text:
            parts = text.split(' - ')
            date_str = parts[0].strip() if mode == 'start' else parts[1].strip()
            return self._parse_date(date_str)
        return self._parse_date(text)

    async def _execute_loop_vat_returns(self, step: dict) -> str | None:
        filter_date_from = step.get('filter_date_from')
        sub_steps = step.get('sub_steps', [])
        reverse_order = step.get('reverse_order', True)

        await self._emit_log("info", "═" * 60)
        await self._emit_log("info", "🔄 Starting VAT Returns Export Process")
        await self._emit_log("info", "═" * 60)

        await self._emit_log("info", "⏳ Waiting for VAT returns page to fully load...")
        await asyncio.sleep(3)

        try:
            await self._page.wait_for_selector('.xui-contentblockitem', state='visible', timeout=15000)
            await self._emit_log("info", "   ✅ VAT returns list detected")
        except Exception:
            await self._emit_log("warning", "   ⚠️ Could not detect VAT returns list, continuing anyway...")

        vat_page_issues = await self._page.evaluate("""
        () => {
            const pageText = document.body.innerText || '';
            if (pageText.includes('could not access outstanding VAT returns from HMRC')) {
                return 'hmrc_access_error';
            }
            if (pageText.includes('VAT registration number needs to be entered')) {
                return 'no_vat_registration';
            }
            if (pageText.includes('Filed VAT returns will be shown here') &&
                !document.querySelector('button[data-automationid*="row-button"]')) {
                return 'no_vat_returns';
            }
            return null;
        }
        """)

        if vat_page_issues:
            issue_messages = {
                'hmrc_access_error': 'Cannot access HMRC - VAT registration missing',
                'no_vat_registration': 'No VAT registration number configured',
                'no_vat_returns': 'No VAT returns available to export'
            }
            skip_reason = issue_messages.get(vat_page_issues, vat_page_issues)
            await self._emit_log("warning", f"⏭️  Skipping VAT exports: {skip_reason}")
            await self._emit_log("info", "═" * 60)
            await self._store_variable('loop_processed_count', 0)
            self.report.log_skip(skip_reason, "VAT Returns Page")
            return None

        filter_date = None
        if filter_date_from:
            date_str = self._resolve_variable(filter_date_from)
            filter_date = self._parse_date(date_str)
            await self._emit_log("info", f"📅 Financial Year Start Date: {date_str}")
            await self._emit_log("info", f"📋 Will export all VAT returns from {date_str} onwards")

        js_get_vat_returns = """
        () => {
            const results = [];
            const seenButtonIds = new Set();
            const vatItems = document.querySelectorAll('.xui-contentblockitem');

            vatItems.forEach((item, index) => {
                const datePara = item.querySelector('p[class*="vat-list-contentblock-title"]') ||
                                 item.querySelector('.xui-contentblockitem--primaryheading p');

                if (datePara) {
                    const text = datePara.textContent.trim();
                    const dateMatch = text.match(/^(\\d{1,2} \\w{3} \\d{4})\\s*[-–]\\s*(\\d{1,2} \\w{3} \\d{4})$/);

                    if (dateMatch) {
                        const reviewBtn = item.querySelector('button[data-automationid*="row-button"]');
                        if (reviewBtn) {
                            const automationId = reviewBtn.getAttribute('data-automationid') || '';
                            // Skip if we've already seen this button ID (prevent duplicates)
                            if (automationId && !seenButtonIds.has(automationId)) {
                                seenButtonIds.add(automationId);
                                results.push({
                                    dateRange: text,
                                    startDate: dateMatch[1],
                                    endDate: dateMatch[2],
                                    index: index,
                                    buttonId: automationId
                                });
                            }
                        }
                    }
                }
            });

            return results;
        }
        """

        vat_returns = await self._page.evaluate(js_get_vat_returns)
        total_found = len(vat_returns)

        await self._emit_log("info", "")
        await self._emit_log("info", "📊 ANALYZING VAT RETURNS ON PAGE")
        await self._emit_log("info", "─" * 40)
        await self._emit_log("info", f"   Total VAT returns found: {total_found}")

        for idx, vr in enumerate(vat_returns):
            await self._emit_log("info", f"   Row {idx + 1}: {vr['dateRange']} (Button: {vr['buttonId']})")

        await self._emit_log("info", "─" * 40)

        if reverse_order:
            vat_returns = vat_returns[::-1]
            await self._emit_log("info", "🔃 Will process in chronological order (oldest first)")

        to_process = []
        skipped = []
        for vat_return in vat_returns:
            date_range = vat_return['dateRange']
            start_date_str = vat_return['startDate']
            row_date = self._parse_date(start_date_str)

            if filter_date and row_date:
                if row_date < filter_date:
                    skipped.append(date_range)
                    continue
            to_process.append(vat_return)

        await self._emit_log("info", "")
        await self._emit_log("info", f"📋 PROCESSING PLAN")
        await self._emit_log("info", "─" * 40)
        await self._emit_log("info", f"   VAT returns to export: {len(to_process)}")
        await self._emit_log("info", f"   VAT returns to skip:   {len(skipped)} (before filter date)")

        if to_process:
            await self._emit_log("info", "")
            await self._emit_log("info", "   Will process these VAT returns:")
            for idx, vr in enumerate(to_process):
                await self._emit_log("info", f"     {idx + 1}. {vr['dateRange']}")

        await self._emit_log("info", "─" * 40)
        await self._emit_log("info", "")

        processed_button_ids = set()
        processed = 0

        for i, vat_return in enumerate(to_process):
            date_range = vat_return['dateRange']
            start_date_str = vat_return['startDate']
            end_date_str = vat_return['endDate']
            button_id = vat_return.get('buttonId', '')

            if button_id in processed_button_ids:
                await self._emit_log("warning", f"   ⏭️  Skipping {date_range} - already processed")
                continue

            await self._emit_log("info", "")
            await self._emit_log("info", f"📁 VAT Return {i + 1} of {len(to_process)}")
            await self._emit_log("info", f"   Period:    {date_range}")
            await self._emit_log("info", f"   Button ID: {button_id}")

            await self._store_variable('vat_return_period', date_range)
            await self._store_variable('vat_return_start_date', start_date_str)
            await self._store_variable('vat_return_end_date', end_date_str)
            await self._store_variable('vat_return_progress', f"{i + 1} of {len(to_process)}")

            await self._emit_log("info", f"   🖱️  Clicking Review button...")

            click_result = await self._page.evaluate(f"""
            () => {{
                // Primary: click by unique button ID
                const buttonId = '{button_id}';
                if (buttonId) {{
                    const btn = document.querySelector(`button[data-automationid="${{buttonId}}"]`);
                    if (btn) {{
                        btn.click();
                        return {{ success: true, method: 'buttonId' }};
                    }}
                }}

                // Fallback: find by date range text
                const targetDateRange = '{date_range}';
                const vatItems = document.querySelectorAll('.xui-contentblockitem');

                for (const item of vatItems) {{
                    const datePara = item.querySelector('p[class*="vat-list-contentblock-title"]') ||
                                     item.querySelector('.xui-contentblockitem--primaryheading p');

                    if (datePara && datePara.textContent.trim() === targetDateRange) {{
                        const reviewBtn = item.querySelector('button[data-automationid*="row-button"]');
                        if (reviewBtn) {{
                            reviewBtn.click();
                            return {{ success: true, method: 'dateRange' }};
                        }}
                    }}
                }}

                return {{ success: false }};
            }}
            """)

            if not click_result or not click_result.get('success'):
                await self._emit_log("warning", f"   ⚠️  Could not find Review button for {date_range}")
                continue

            await self._emit_log("info", f"   ✅ Clicked via {click_result.get('method', 'unknown')}")
            processed_button_ids.add(button_id)

            await asyncio.sleep(3)

            has_preparation_prompt = await self._page.evaluate("""
            () => {
                const pageText = document.body.innerText || '';
                return pageText.includes('How would you like to prepare your VAT');
            }
            """)

            if has_preparation_prompt:
                await self._emit_log("warning", f"   ⏭️  Skipping {date_range} - VAT preparation not configured")
                self.report.log_skip("VAT preparation not configured", date_range)
                await self._navigate_back_to_vat_list()
                continue

            sub_step_failed = False
            for sub_step in sub_steps:
                try:
                    await self._execute_step(sub_step)
                except StepFailedError as e:
                    await self._emit_log("warning", f"   ⚠️  Sub-step failed: {str(e)}")
                    sub_step_failed = True
                    break

            if sub_step_failed:
                await self._emit_log("info", f"   🔄 Navigating back to VAT list...")
                await self._navigate_back_to_vat_list()
                continue

            processed += 1
            await self._emit_log("info", f"   ✅ Completed export for period {date_range}")

            await self._emit_log("info", f"   ⏳ Waiting for VAT list to reload...")
            await asyncio.sleep(2)

            try:
                await self._page.wait_for_selector('.xui-contentblockitem', state='visible', timeout=10000)
            except Exception:
                await self._emit_log("warning", "   ⚠️ VAT list may not have reloaded, continuing...")

        await self._emit_log("info", "")
        await self._emit_log("info", "═" * 60)
        await self._emit_log("info", f"🎉 VAT Returns Export Complete!")
        await self._emit_log("info", f"   Total processed: {processed} of {len(to_process)}")
        await self._emit_log("info", f"   Total skipped:   {len(skipped)}")
        await self._emit_log("info", "═" * 60)

        await self._store_variable('loop_processed_count', processed)
        return None

    async def _navigate_back_to_vat_list(self):
        """Helper to navigate back to the VAT returns list."""
        try:
            tax_btn = self._page.locator("button:has-text('Tax')").first
            if await tax_btn.is_visible(timeout=3000):
                await tax_btn.click()
                await asyncio.sleep(0.5)
                vat_link = self._page.locator("a:has-text('VAT returns')").first
                if await vat_link.is_visible(timeout=3000):
                    await vat_link.click()
                    await asyncio.sleep(3)
                    try:
                        await self._page.wait_for_selector('.xui-contentblockitem', state='visible', timeout=10000)
                    except Exception:
                        pass
                    return
        except Exception:
            pass

        await self._page.goto("https://go.xero.com")
        await asyncio.sleep(2)
        try:
            tax_btn = self._page.locator("button:has-text('Tax')").first
            if await tax_btn.is_visible(timeout=5000):
                await tax_btn.click()
                await asyncio.sleep(0.5)
                vat_link = self._page.locator("a:has-text('VAT returns')").first
                if await vat_link.is_visible(timeout=3000):
                    await vat_link.click()
                    await asyncio.sleep(3)
        except Exception as nav_err:
            await self._emit_log("warning", f"   ⚠️  Navigation back failed: {str(nav_err)}")

    async def _execute_loop_elements(self, step: dict) -> str | None:
        container_selector = step.get('container')
        item_selector = step.get('item_selector')
        date_field_selector = step.get('date_field_selector')
        filter_date_from = step.get('filter_date_from')
        date_extract_mode = step.get('date_extract_mode', 'start')
        action_selector = step.get('action_selector')
        sub_steps = step.get('sub_steps', [])
        reverse_order = step.get('reverse_order', True)

        await self._emit_log("info", "═" * 60)
        await self._emit_log("info", "🔄 Starting Loop Processing")
        await self._emit_log("info", "═" * 60)

        filter_date = None
        if filter_date_from:
            date_str = self._resolve_variable(filter_date_from)
            filter_date = self._parse_date(date_str)
            await self._emit_log("info", f"📅 Filter date: {date_str}")

        container = self._page
        if container_selector:
            container = self._page.locator(container_selector)

        rows = container.locator(item_selector)
        count = await rows.count()
        await self._emit_log("info", f"📊 Found {count} elements to process")

        indices = list(range(count))
        if reverse_order:
            indices = indices[::-1]
            await self._emit_log("info", "🔃 Processing in reverse order")

        processed = 0
        skipped = 0
        for i in indices:
            row = rows.nth(i)

            if filter_date and date_field_selector:
                try:
                    date_el = row.locator(date_field_selector).first
                    date_text = await date_el.text_content()
                    if date_text:
                        row_date = self._extract_date_from_range(date_text, date_extract_mode)
                        if row_date and row_date < filter_date:
                            skipped += 1
                            continue
                except Exception:
                    pass

            await self._emit_log("info", f"📁 Processing item {processed + 1}...")

            if action_selector:
                try:
                    action_btn = row.locator(action_selector).first
                    if await action_btn.is_visible(timeout=2000):
                        await action_btn.click()
                        await asyncio.sleep(1)
                except Exception as e:
                    await self._emit_log("warning", f"   ⚠️  Could not click action button: {str(e)}")
                    continue

            for sub_step in sub_steps:
                try:
                    await self._execute_step(sub_step)
                except StepFailedError as e:
                    await self._emit_log("warning", f"   ⚠️  Sub-step failed: {str(e)}")
                    break

            processed += 1
            await self._emit_log("info", f"   ✅ Item {processed} completed")

        await self._emit_log("info", "")
        await self._emit_log("info", "═" * 60)
        await self._emit_log("info", f"🎉 Loop Processing Complete!")
        await self._emit_log("info", f"   Total processed: {processed}")
        if skipped > 0:
            await self._emit_log("info", f"   Total skipped:   {skipped}")
        await self._emit_log("info", "═" * 60)

        await self._store_variable('loop_processed_count', processed)
        return None

    def _get_report_prefix(self, workflow_name: str) -> tuple[str, str, bool]:
        """Returns (number_prefix, full_name, is_vat) for a workflow."""
        report_map = {
            'trial_balance_report': ('1', 'Trial Balance', False),
            'profit_and_loss': ('2', 'Profit and Loss', False),
            'aged_receivables_detail': ('3', 'Aged Receivables Detail', False),
            'aged_payables_detail': ('4', 'Aged Payables Detail', False),
            'account_transactions': ('5', 'Account Transactions', False),
            'receivable_invoice_detail': ('6', 'Receivable Invoice Detail', False),
            'payable_invoice_detail': ('7', 'Payable Invoice Detail', False),
            'vat_returns': ('1', 'VAT', True),
            'vat_returns_export': ('1', 'VAT', True),
            'get_financial_year_end': ('', 'Financial Year End', False),
        }
        return report_map.get(workflow_name, ('', workflow_name, False))

    def _format_date_compact(self, date_str: str) -> str:
        """Convert date string like '01 Apr 2024' to '01042024' format."""
        if not date_str:
            return ''
        parsed = self._parse_date(date_str)
        if parsed:
            return parsed.strftime('%d%m%Y')
        return date_str.replace(' ', '').replace('-', '')

    def _format_download_filename(self, workflow_name: str, company_name: str, file_ext: str) -> tuple[str, str, str]:
        """Generate filename and folder based on workflow type."""
        num_prefix, report_name, is_vat = self._get_report_prefix(workflow_name)
        safe_company = re.sub(r'[<>:"/\\|?*]', '', company_name) if company_name else 'Unknown'

        client_folder = safe_company
        subfolder = ""

        if is_vat:
            period_start = self.state.variables.get('vat_return_start_date', '')
            period_end = self.state.variables.get('vat_return_end_date', '')

            if period_start and period_end:
                start_compact = self._format_date_compact(period_start)
                end_compact = self._format_date_compact(period_end)
                period_str = f"{start_compact}-{end_compact}"
                new_filename = f"{num_prefix} VAT_{period_str}_{safe_company}{file_ext}"
            else:
                new_filename = f"{num_prefix} VAT_{safe_company}{file_ext}"
        else:
            if num_prefix:
                new_filename = f"{num_prefix} {report_name}_{safe_company}{file_ext}"
            else:
                new_filename = f"{report_name}_{safe_company}{file_ext}"

        return new_filename, client_folder, subfolder

    async def _execute_wait_for_download(self, step: dict) -> str | None:
        timeout = step.get('timeout', 30000)
        save_to = step.get('save_to', 'downloads/')

        await self._emit_log("info", "📥 Waiting for download to start...")

        try:
            async with self._page.expect_download(timeout=timeout) as download_info:
                await asyncio.sleep(1)

            download = await download_info.value
            original_filename = download.suggested_filename
            await self._emit_log("info", f"   📄 Original file: {original_filename}")

            # Wait for the download to actually complete
            await self._emit_log("info", f"   ⏳ Waiting for download to complete...")
            temp_path = await download.path()

            # Check if download failed
            failure = await download.failure()
            if failure:
                raise StepFailedError(f"Download failed: {failure}")

            if not temp_path:
                raise StepFailedError("Download completed but no file path returned")

            # Wait for file to be fully written (race condition fix)
            temp_size = 0
            for attempt in range(10):
                await asyncio.sleep(0.5)
                if Path(temp_path).exists():
                    temp_size = Path(temp_path).stat().st_size
                    if temp_size > 0:
                        break
                await self._emit_log("info", f"   ⏳ Waiting for file write... (attempt {attempt + 1})")

            await self._emit_log("info", f"   📦 Temp file size: {temp_size} bytes")

            if temp_size == 0:
                raise StepFailedError("Download completed but temp file is 0 bytes - possible session expiry or server error")

            client_name = self.state.variables.get('selected_client', '')
            company_name = self.state.variables.get('company_name', client_name)

            if not company_name and '_-_' in original_filename:
                parts = original_filename.split('_-_', 1)
                company_name = parts[0].strip()

            if company_name:
                await self._store_variable('company_name', company_name)

            workflow_name = self.workflow.get('name', '')
            file_ext = Path(original_filename).suffix

            new_filename, client_folder, subfolder = self._format_download_filename(
                workflow_name, company_name, file_ext
            )

            save_path = Path(save_to) / client_folder / subfolder
            save_path.mkdir(parents=True, exist_ok=True)

            file_path = save_path / new_filename

            await self._emit_log("info", f"   ⏳ Copying to: {file_path}")
            await download.save_as(str(file_path))

            final_size = file_path.stat().st_size
            await self._emit_log("info", f"   ✅ Download saved ({final_size} bytes)")

            if final_size == 0:
                raise StepFailedError("Download completed but file is 0 bytes")

            await self._store_variable('downloaded_file', str(file_path))
            await self._emit_log("info", f"   🏢 Client: {company_name}")
            await self._emit_log("info", f"   📂 Folder: {client_folder}/{subfolder}")
            await self._emit_log("info", f"   💾 Saved as: {new_filename}")
            await self._emit_log("info", f"   ✅ Download complete")
            self.report.log_download(new_filename, str(file_path))
            return None
        except Exception as e:
            await self._emit_log("error", f"   ❌ Download failed: {str(e)}")
            if not step.get('optional'):
                raise StepFailedError(f"Download failed: {str(e)}")
            return step.get('on_error')

    async def _execute_script(self, step: dict) -> str | None:
        script = step.get('script', '')
        save_to = step.get('save_to')

        await self._emit_log("info", "📜 Executing script...")

        try:
            result = await self._page.evaluate(script)
            if save_to and result is not None:
                await self._store_variable(save_to, str(result))
                await self._emit_log("info", f"   ✅ Script result saved to: {save_to} = {result}")
            else:
                await self._emit_log("info", f"   ✅ Script executed successfully")
            if step.get('wait_after'):
                await asyncio.sleep(step['wait_after'] / 1000)
            return None
        except Exception as e:
            await self._emit_log("error", f"   ❌ Script execution failed: {str(e)}")
            if not step.get('optional'):
                raise StepFailedError(f"Script execution failed: {str(e)}")
            return step.get('on_error')

    async def _execute_validate_filters(self, step: dict) -> str | None:
        """Validate that all report filters are correctly set before export."""
        await self._emit_log("info", "🔍 Validating report filters before export...")

        checks = step.get('checks', {})
        fail_on_error = step.get('fail_on_error', False)
        validation_errors = []
        validation_passed = []

        js_validate_filters = """
        () => {
            const result = {
                date_period: null,
                columns: [],
                has_data: false,
                row_count: 0,
                report_status: null
            };

            // Get date period from various possible locations
            const dateInputs = document.querySelectorAll('input[type="text"], input[aria-label*="date"], input[placeholder*="date"]');
            for (const input of dateInputs) {
                const value = input.value;
                if (value && /\\d{1,2}\\s+\\w{3}\\s+\\d{4}/.test(value)) {
                    if (!result.date_period) result.date_period = {};
                    if (input.getAttribute('aria-label')?.toLowerCase().includes('start') ||
                        input.getAttribute('data-automationid')?.includes('start')) {
                        result.date_period.start = value;
                    } else if (input.getAttribute('aria-label')?.toLowerCase().includes('end') ||
                               input.getAttribute('data-automationid')?.includes('end')) {
                        result.date_period.end = value;
                    }
                }
            }

            // Get selected columns from column button text or checkboxes
            const columnBtn = document.querySelector('button:has-text("columns selected"), button:has-text("Columns")');
            if (columnBtn) {
                const match = columnBtn.textContent.match(/(\\d+)\\s+columns?\\s+selected/i);
                if (match) {
                    result.columns_count = parseInt(match[1]);
                }
            }

            // Check for visible column headers in table
            const tableHeaders = document.querySelectorAll('th, [role="columnheader"]');
            tableHeaders.forEach(th => {
                const text = th.textContent?.trim();
                if (text && text.length < 50) {
                    result.columns.push(text);
                }
            });

            // Check if report has data rows
            const tableRows = document.querySelectorAll('tbody tr, [role="row"]:not([role="columnheader"])');
            result.row_count = tableRows.length;
            result.has_data = result.row_count > 0;

            // Check for report status message
            const statusEl = document.querySelector('status, [role="status"], [aria-live="polite"]');
            if (statusEl) {
                result.report_status = statusEl.textContent?.trim();
            }

            // Check for loading indicators (should be absent)
            const loadingIndicators = document.querySelectorAll('[aria-busy="true"], .loading, .spinner');
            result.is_loading = loadingIndicators.length > 0;

            return result;
        }
        """

        try:
            page_state = await self._page.evaluate(js_validate_filters)

            await self._emit_log("info", "   📊 Current report state:")

            if page_state.get('date_period'):
                date_info = page_state['date_period']
                start = date_info.get('start', 'N/A')
                end = date_info.get('end', 'N/A')
                await self._emit_log("info", f"      📅 Date range: {start} to {end}")
                validation_passed.append(f"Date period set: {start} - {end}")
            else:
                await self._emit_log("warning", f"      📅 Date range: Could not detect (may be using dropdown selection)")

            if page_state.get('columns_count'):
                await self._emit_log("info", f"      📋 Columns selected: {page_state['columns_count']}")
                validation_passed.append(f"Columns selected: {page_state['columns_count']}")
            elif page_state.get('columns'):
                col_count = len(page_state['columns'])
                await self._emit_log("info", f"      📋 Column headers found: {col_count}")
                if checks.get('expected_columns'):
                    expected = set(checks['expected_columns'])
                    found = set(page_state['columns'])
                    missing = expected - found
                    if missing:
                        validation_errors.append(f"Missing columns: {', '.join(missing)}")
                        await self._emit_log("warning", f"      ⚠️  Missing columns: {', '.join(missing)}")
                    else:
                        validation_passed.append("All expected columns present")

            if page_state.get('is_loading'):
                validation_errors.append("Report is still loading")
                await self._emit_log("warning", f"      ⏳ Report appears to still be loading")
            else:
                validation_passed.append("Report finished loading")

            if page_state.get('has_data'):
                await self._emit_log("info", f"      ✅ Report has data: {page_state['row_count']} rows")
                validation_passed.append(f"Report has {page_state['row_count']} data rows")
            else:
                validation_errors.append("Report appears to have no data")
                await self._emit_log("warning", f"      ⚠️  Report appears to have no data rows")

            if checks.get('min_rows') and page_state.get('row_count', 0) < checks['min_rows']:
                validation_errors.append(f"Expected at least {checks['min_rows']} rows, got {page_state.get('row_count', 0)}")

            await self._store_variable('validation_result', {
                'passed': validation_passed,
                'errors': validation_errors,
                'page_state': page_state
            })

            self.report.log_validation(validation_passed, validation_errors)

            if validation_errors:
                await self._emit_log("info", "")
                await self._emit_log("warning", "   ⚠️  VALIDATION WARNINGS:")
                for error in validation_errors:
                    await self._emit_log("warning", f"      • {error}")

                if fail_on_error:
                    await self._emit_log("error", "   ❌ Validation failed - stopping before export")
                    raise StepFailedError(f"Filter validation failed: {'; '.join(validation_errors)}")
                else:
                    await self._emit_log("info", "   ⏩ Continuing despite warnings (fail_on_error=false)")
            else:
                await self._emit_log("info", "   ✅ All filter validations passed!")

            return None

        except StepFailedError:
            raise
        except Exception as e:
            await self._emit_log("error", f"   ❌ Validation check failed: {str(e)}")
            if fail_on_error:
                raise StepFailedError(f"Validation check failed: {str(e)}")
            return step.get('on_error')

    def _extract_company_from_filename(self, filename: str) -> str:
        """Extract company name from Xero filename patterns."""
        name_without_ext = Path(filename).stem

        # Pattern 1: COMPANY_NAME_-_Report_Name (standard Xero format)
        if '_-_' in name_without_ext:
            company_part = name_without_ext.split('_-_')[0]
            return company_part.replace('_', ' ').strip()

        # Pattern 2: COMPANY-VAT... (VAT format)
        vat_match = re.match(r'^(.+?)-(?:VAT|vat)', name_without_ext)
        if vat_match:
            return vat_match.group(1).strip().replace('-', ' ').replace('_', ' ')

        # Pattern 3: Just use the first part before any dash or underscore pattern
        parts = re.split(r'[-_]{2,}|_-_|-_|_-', name_without_ext)
        if parts:
            return parts[0].replace('_', ' ').strip()

        return name_without_ext.replace('_', ' ').strip()

    async def _execute_click_and_download(self, step: dict) -> str | None:
        selectors = step.get('selectors', [])
        timeout = step.get('timeout', 30000)
        save_to = step.get('save_to', 'downloads/')

        await self._emit_log("info", f"📥 Initiating download...")

        element = None
        for selector in selectors:
            try:
                loc = self._page.locator(selector)
                if await loc.first.is_visible(timeout=3000):
                    element = loc.first
                    await self._emit_log("info", f"   Found element: {selector}")
                    break
            except Exception:
                continue

        if not element:
            raise StepFailedError(f"No element found to click: {selectors}")

        try:
            async with self._page.expect_download(timeout=timeout) as download_info:
                await element.click()
                await self._emit_log("info", f"   Clicked, waiting for download...")

            download = await download_info.value
            original_filename = download.suggested_filename
            await self._emit_log("info", f"   📄 Original file: {original_filename}")

            # Wait for the download to actually complete
            await self._emit_log("info", f"   ⏳ Waiting for download to complete...")
            temp_path = await download.path()

            # Check if download failed
            failure = await download.failure()
            if failure:
                raise StepFailedError(f"Download failed: {failure}")

            if not temp_path:
                raise StepFailedError("Download completed but no file path returned")

            # Wait for file to be fully written (race condition fix)
            temp_size = 0
            for attempt in range(10):
                await asyncio.sleep(0.5)
                if Path(temp_path).exists():
                    temp_size = Path(temp_path).stat().st_size
                    if temp_size > 0:
                        break
                await self._emit_log("info", f"   ⏳ Waiting for file write... (attempt {attempt + 1})")

            await self._emit_log("info", f"   📦 Temp file size: {temp_size} bytes")

            if temp_size == 0:
                raise StepFailedError("Download completed but temp file is 0 bytes - possible session expiry or server error")

            client_name = self.state.variables.get('selected_client', '')
            company_name = self.state.variables.get('company_name', client_name)

            if not company_name:
                company_name = self._extract_company_from_filename(original_filename)

            if company_name:
                await self._store_variable('company_name', company_name)

            workflow_name = self.workflow.get('name', '')
            file_ext = Path(original_filename).suffix

            new_filename, client_folder, subfolder = self._format_download_filename(
                workflow_name, company_name, file_ext
            )

            save_path = Path(save_to) / client_folder / subfolder
            save_path.mkdir(parents=True, exist_ok=True)

            file_path = save_path / new_filename

            await self._emit_log("info", f"   ⏳ Copying to: {file_path}")
            await download.save_as(str(file_path))

            final_size = file_path.stat().st_size
            await self._emit_log("info", f"   ✅ Download saved ({final_size} bytes)")

            if final_size == 0:
                raise StepFailedError("Download completed but file is 0 bytes")

            await self._store_variable('downloaded_file', str(file_path))
            await self._emit_log("info", f"   🏢 Client: {company_name}")
            await self._emit_log("info", f"   📂 Folder: {client_folder}/{subfolder}")
            await self._emit_log("info", f"   💾 Saved as: {new_filename}")
            await self._emit_log("info", f"   ✅ Download complete")
            self.report.log_download(new_filename, str(file_path))
            return None
        except asyncio.TimeoutError:
            await self._emit_log("error", f"   ❌ Download timeout - no download started within {timeout}ms")
            if not step.get('optional'):
                raise StepFailedError(f"Download timeout: no download started")
            return step.get('on_error')
        except Exception as e:
            await self._emit_log("error", f"   ❌ Download failed: {str(e)}")
            if not step.get('optional'):
                raise StepFailedError(f"Click and download failed: {str(e)}")
            return step.get('on_error')

    async def _execute_step(self, step: dict) -> str | None:
        action = step.get('action')
        step_id = step.get('id')
        description = step.get('description', '')
        self.state.current_step = step_id

        if description:
            await self._emit_log("info", f"")
            await self._emit_log("info", f"▶️  {description}")

        handlers = {
            'goto': self._execute_goto,
            'fill': self._execute_fill,
            'press_key': self._execute_press_key,
            'click': self._execute_click,
            'ensure_checked': self._execute_ensure_checked,
            'batch_ensure_checked': self._execute_batch_ensure_checked,
            'deselect_all_columns': self._execute_deselect_all_columns,
            'select_columns': self._execute_select_columns,
            'check_url': self._execute_check_url,
            'wait_for_url': self._execute_wait_for_url,
            'wait_for_selector': self._execute_wait_for_selector,
            'wait_for_download': self._execute_wait_for_download,
            'capture_state': self._execute_capture_state,
            'scrape': self._execute_scrape,
            'manual_intervention': self._execute_manual_intervention,
            'read_input': self._execute_read_input,
            'read_text': self._execute_read_text,
            'loop_elements': self._execute_loop_elements,
            'loop_vat_returns': self._execute_loop_vat_returns,
            'click_and_download': self._execute_click_and_download,
            'execute_script': self._execute_script,
            'validate_filters': self._execute_validate_filters,
        }

        handler = handlers.get(action)
        if not handler:
            await self._emit_log("error", f"❌ Unknown action: {action}")
            return None

        try:
            next_step = await handler(step)
            self.state.completed_steps.append(step_id)
            self.report.log_step(step_id, action, description, "success")
            return next_step
        except StepFailedError:
            self.report.log_step(step_id, action, description, "error")
            self.report.log_error(step_id, str(step_id), fatal=True)
            raise
        except Exception as e:
            await self._emit_log("error", f"❌ Step failed: {str(e)}")
            self.state.errors.append({'step': step_id, 'error': str(e)})
            self.report.log_step(step_id, action, description, "error")
            self.report.log_error(step_id, str(e))
            return step.get('on_error')

    async def run(self, headless: bool = False, browser_data_dir: str = './browser_data',
                  context: BrowserContext = None, page: Page = None) -> WorkflowState:
        workflow_name = self.workflow.get('name', self.workflow_path.stem)
        workflow_description = self.workflow.get('description', '')
        client_name = self.state.variables.get('selected_client', '')

        self.report.start_workflow(workflow_name, client_name)

        await self._emit_log("info", "")
        await self._emit_log("info", "╔" + "═" * 58 + "╗")
        await self._emit_log("info", f"║  🚀 Starting Workflow: {workflow_name}")
        if workflow_description:
            await self._emit_log("info", f"║  📝 {workflow_description[:50]}")
        await self._emit_log("info", "╚" + "═" * 58 + "╝")
        await self._emit_log("info", "")

        own_context = context is None

        if own_context:
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=browser_data_dir,
                headless=headless,
            )
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        else:
            self._context = context
            self._page = page

        steps = self.workflow.get('steps', [])
        current_index = 0
        final_status = "completed"

        try:
            while current_index < len(steps):
                step = steps[current_index]
                next_step_id = await self._execute_step(step)

                if next_step_id:
                    next_index = self._get_step_index(next_step_id)
                    if next_index >= 0:
                        current_index = next_index
                        continue

                current_index += 1

            await self._emit_log("info", "")
            await self._emit_log("info", "╔" + "═" * 58 + "╗")
            await self._emit_log("success", f"║  ✅ Workflow Complete: {workflow_name}")
            await self._emit_log("info", f"║  📊 Steps completed: {len(self.state.completed_steps)}")
            await self._emit_log("info", "╚" + "═" * 58 + "╝")
        except StepFailedError as e:
            final_status = "failed"
            await self._emit_log("info", "")
            await self._emit_log("info", "╔" + "═" * 58 + "╗")
            await self._emit_log("error", f"║  ❌ Workflow Failed: {workflow_name}")
            await self._emit_log("error", f"║  💥 {str(e)[:50]}")
            await self._emit_log("info", "╚" + "═" * 58 + "╝")
            self.state.errors.append({'step': self.state.current_step, 'error': str(e), 'fatal': True})

        self.report.end_workflow(final_status, dict(self.state.variables))
        return self.state

    async def close(self):
        if self._context:
            await self._context.close()
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()

    @property
    def context(self) -> BrowserContext:
        return self._context

    @property
    def page(self) -> Page:
        return self._page


async def run_workflow(workflow_path: Path, headless: bool = False) -> WorkflowState:
    engine = WorkflowEngine(workflow_path)
    state = await engine.run(headless=headless)
    await engine.close()
    return state


async def run_workflow_chain(workflow_paths: list[Path], headless: bool = False,
                             browser_data_dir: str = './browser_data') -> list[WorkflowState]:
    """Run multiple workflows in sequence using the same browser session."""
    from playwright.async_api import async_playwright

    results = []

    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=browser_data_dir,
        headless=headless,
    )
    page = context.pages[0] if context.pages else await context.new_page()

    try:
        for workflow_path in workflow_paths:
            engine = WorkflowEngine(workflow_path)
            state = await engine.run(context=context, page=page)
            results.append(state)
    finally:
        await context.close()
        await playwright.stop()

    return results
