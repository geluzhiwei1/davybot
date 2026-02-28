# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser Automation Tools using Playwright

This module provides browser automation capabilities using Playwright's synchronous API.
Requires playwright to be installed: pip install playwright
"""

import contextlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

# Import Playwright sync API (required dependency)
# ✅ Fast fail: 明确检查Playwright依赖，提供清晰的错误消息
try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
except ImportError as e:
    raise ImportError(
        "Browser automation tools require Playwright to be installed. "
        "Please install it with:\n"
        "  pip install playwright\n"
        "  playwright install\n"
        "See https://playwright.dev/python/docs/intro for more details."
    ) from e

# Singleton browser instance (shared across all tool calls)
_browser = None
_context = None
_page = None
_playwright = None


def _get_browser_page():
    """Get or create the global browser and page instances."""
    global _browser, _context, _page, _playwright

    if _page is None:
        _playwright = sync_playwright().start()
        try:
            # Try to use system Chrome
            _browser = _playwright.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
        except Exception:
            # Fallback to chromium if Chrome is not available
            _browser = _playwright.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )

        _context = _browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        _page = _context.new_page()

    return _page


def close_browser():
    """Close the global browser instance."""
    global _browser, _context, _page, _playwright

    if _page:
        with contextlib.suppress(BaseException):
            _page.close()
        _page = None

    if _context:
        with contextlib.suppress(BaseException):
            _context.close()
        _context = None

    if _browser:
        with contextlib.suppress(BaseException):
            _browser.close()
        _browser = None

    if _playwright:
        with contextlib.suppress(BaseException):
            _playwright.stop()
        _playwright = None


# Browser Action Tool
class BrowserActionInput(BaseModel):
    """Input for BrowserActionTool."""

    action: str = Field(
        ...,
        description="Browser action to perform (e.g., 'click', 'navigate', 'fill', 'screenshot', 'evaluate').",
    )
    selector: str | None = Field(
        None,
        description="CSS selector or XPath for element targeting.",
    )
    value: str | None = Field(None, description="Value to input (for fill/evaluate actions).")
    url: str | None = Field(None, description="URL to navigate to (for navigate action).")
    wait_for: str | None = Field(None, description="Text or element to wait for (CSS selector).")
    timeout: int | None = Field(30000, description="Timeout in milliseconds.")
    screenshot_path: str | None = Field(
        None,
        description="Path to save screenshot (for screenshot action).",
    )


class BrowserActionTool(CustomBaseTool):
    """Tool for automating browser interactions using Playwright with local Chrome."""

    name: str = "browser_action"
    description: str = """Automates browser interactions using Playwright with local Chrome browser.

    Supported actions:
    - navigate: Navigate to a URL (requires 'url' parameter)
    - click: Click an element (requires 'selector' parameter)
    - fill: Fill an input field (requires 'selector' and 'value' parameters)
    - screenshot: Take a screenshot (optional 'screenshot_path' parameter)
    - evaluate: Execute JavaScript (requires 'value' as JS code)
    - wait: Wait for an element (requires 'wait_for' as CSS selector)
    - get_text: Get text content of an element (requires 'selector')
    - get_url: Get current page URL

    Examples:
    - browser_action(action="navigate", url="https://www.baidu.com")
    - browser_action(action="fill", selector="#kw", value="search query")
    - browser_action(action="click", selector="#su")
    - browser_action(action="screenshot", screenshot_path="tmp/screenshot.png")
    """
    args_schema: type[BaseModel] = BrowserActionInput

    @safe_tool_operation(
        "browser_action",
        fallback_value='{"action": "error", "status": "error", "message": "Failed to execute browser action"}',
    )
    def _run(
        self,
        action: str,
        selector: str | None = None,
        value: str | None = None,
        url: str | None = None,
        wait_for: str | None = None,
        timeout: int = 30000,
        screenshot_path: str | None = None,
    ) -> str:
        """Perform browser action using Playwright."""
        result = {"action": action, "status": "success"}

        try:
            page = _get_browser_page()

            if action == "navigate":
                if not url:
                    raise ValueError("URL is required for navigate action")
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                result["url"] = page.url
                result["title"] = page.title()
                result["message"] = f"Navigated to {url}"

            elif action == "click":
                if not selector:
                    raise ValueError("Selector is required for click action")
                page.click(selector, timeout=timeout)
                result["selector"] = selector
                result["message"] = f"Clicked element '{selector}'"

            elif action == "fill":
                if not selector or value is None:
                    raise ValueError("Selector and value are required for fill action")
                page.fill(selector, value, timeout=timeout)
                result["selector"] = selector
                result["value"] = value
                result["message"] = f"Filled '{value}' into '{selector}'"

            elif action == "screenshot":
                path = screenshot_path or "tmp/screenshot.png"
                # Ensure directory exists
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=path)
                result["screenshot_path"] = path
                result["message"] = f"Screenshot saved to {path}"

            elif action == "evaluate":
                if value is None:
                    raise ValueError(
                        "JavaScript code is required for evaluate action (use 'value' parameter)",
                    )
                eval_result = page.evaluate(value)
                result["result"] = str(eval_result)
                result["message"] = "JavaScript executed successfully"

            elif action == "wait":
                if not wait_for:
                    raise ValueError("CSS selector is required for wait action")
                page.wait_for_selector(wait_for, timeout=timeout)
                result["selector"] = wait_for
                result["message"] = f"Waited for element '{wait_for}'"

            elif action == "get_text":
                if not selector:
                    raise ValueError("Selector is required for get_text action")
                text = page.text_content(selector)
                result["selector"] = selector
                result["text"] = text
                result["message"] = f"Retrieved text from '{selector}'"

            elif action == "get_url":
                result["url"] = page.url
                result["title"] = page.title()
                result["message"] = f"Current URL: {page.url}"

            else:
                result["status"] = "error"
                result["message"] = f"Unknown action: {action}"

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Action failed: {e!s}"

        return json.dumps(result, indent=2, ensure_ascii=False)


# Enhanced Browser Actions with more specific tools
class NavigatePageInput(BaseModel):
    """Input for NavigatePageTool."""

    url: str = Field(..., description="URL to navigate to.")
    timeout: int | None = Field(30000, description="Timeout in milliseconds.")


class NavigatePageTool(CustomBaseTool):
    """Tool for navigating to a URL."""

    name: str = "navigate_page"
    description: str = "Navigates the browser to a specified URL using Playwright with local Chrome."
    args_schema: type[BaseModel] = NavigatePageInput

    def _run(self, url: str, timeout: int = 30000) -> str:
        """Navigate to URL."""
        browser_tool = BrowserActionTool()
        return browser_tool._run(action="navigate", url=url, timeout=timeout)


class ClickElementInput(BaseModel):
    """Input for ClickElementTool."""

    selector: str = Field(..., description="CSS selector or XPath for element to click.")
    timeout: int | None = Field(30000, description="Timeout in milliseconds.")


class ClickElementTool(CustomBaseTool):
    """Tool for clicking elements on the page."""

    name: str = "click_element"
    description: str = "Clicks on an element specified by CSS selector or XPath using Playwright."
    args_schema: type[BaseModel] = ClickElementInput

    def _run(self, selector: str, timeout: int = 30000) -> str:
        """Click element."""
        browser_tool = BrowserActionTool()
        return browser_tool._run(action="click", selector=selector, timeout=timeout)


class TypeTextInput(BaseModel):
    """Input for TypeTextTool."""

    selector: str = Field(..., description="CSS selector or XPath for input element.")
    text: str = Field(..., description="Text to type into the element.")
    timeout: int | None = Field(30000, description="Timeout in milliseconds.")


class TypeTextTool(CustomBaseTool):
    """Tool for typing text into input elements."""

    name: str = "type_text"
    description: str = "Types text into an input field using Playwright."
    args_schema: type[BaseModel] = TypeTextInput

    def _run(self, selector: str, text: str, timeout: int = 30000) -> str:
        """Type text into element."""
        browser_tool = BrowserActionTool()
        return browser_tool._run(action="fill", selector=selector, value=text, timeout=timeout)


class TakeScreenshotInput(BaseModel):
    """Input for TakeScreenshotTool."""

    path: str | None = Field(None, description="Path to save screenshot.")
    full_page: bool = Field(False, description="Whether to capture the full page.")


class TakeScreenshotTool(CustomBaseTool):
    """Tool for taking screenshots."""

    name: str = "take_screenshot"
    description: str = "Takes a screenshot of the current page using Playwright."
    args_schema: type[BaseModel] = TakeScreenshotInput

    def _run(self, path: str | None = None, _full_page: bool = False) -> str:
        """Take screenshot."""
        browser_tool = BrowserActionTool()
        return browser_tool._run(action="screenshot", screenshot_path=path)


# Export cleanup function for manual cleanup if needed
def close_global_browser():
    """Close the global browser instance. Call this when done with all browser operations."""
    close_browser()
