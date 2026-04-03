"""browser tool — interactive web browsing via Playwright.

The AI can navigate, click, type, scroll, take screenshots, and extract text.
Screenshots are returned as base64-encoded images for Claude's vision.
"""

import asyncio
import base64
from typing import Any

from bot.logger import get_logger

log = get_logger("browser")

_page = None       # playwright Page
_browser = None    # playwright Browser
_playwright = None # playwright instance


async def _ensure_browser():
    """Lazy-init Playwright browser and page."""
    global _playwright, _browser, _page

    if _page and not _page.is_closed():
        return _page

    from playwright.async_api import async_playwright

    if not _playwright:
        _playwright = await async_playwright().start()

    if not _browser or not _browser.is_connected():
        _browser = await _playwright.chromium.launch(
            headless=False,  # headed mode so Xvfb/VNC can see it
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1280,720",
            ],
        )

    if not _page or _page.is_closed():
        context = await _browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
        )
        _page = await context.new_page()
        log.info("browser: new page created")

    return _page


async def _take_screenshot() -> str:
    """Take a screenshot and return as base64 PNG."""
    page = await _ensure_browser()
    data = await page.screenshot(type="png")
    return base64.b64encode(data).decode()


# ── Tool actions ─────────────────────────────────────────────────────────────

async def run_browser(action: str, **kwargs) -> str | dict:
    """Execute a browser action. Returns result string or screenshot dict."""

    if action == "navigate":
        url = kwargs.get("url", "")
        if not url:
            return "Error: url is required"
        page = await _ensure_browser()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            return f"Error navigating to {url}: {e}"
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "title": await page.title(),
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "click":
        x = kwargs.get("x")
        y = kwargs.get("y")
        selector = kwargs.get("selector", "")
        page = await _ensure_browser()
        try:
            if selector:
                await page.click(selector, timeout=5000)
            elif x is not None and y is not None:
                await page.mouse.click(float(x), float(y))
            else:
                return "Error: provide selector or x,y coordinates"
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception as e:
            return f"Error clicking: {e}"
        await asyncio.sleep(0.5)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "type":
        text = kwargs.get("text", "")
        selector = kwargs.get("selector", "")
        page = await _ensure_browser()
        try:
            if selector:
                await page.fill(selector, text, timeout=5000)
            else:
                await page.keyboard.type(text, delay=50)
        except Exception as e:
            return f"Error typing: {e}"
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "press":
        key = kwargs.get("key", "Enter")
        page = await _ensure_browser()
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "scroll":
        direction = kwargs.get("direction", "down")
        amount = int(kwargs.get("amount", 500))
        page = await _ensure_browser()
        delta = amount if direction == "down" else -amount
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(0.5)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "screenshot":
        page = await _ensure_browser()
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "title": await page.title(),
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "get_text":
        page = await _ensure_browser()
        text = await page.inner_text("body")
        # Truncate to avoid huge payloads
        if len(text) > 8000:
            text = text[:8000] + "\n...(truncated)"
        return {
            "type": "text",
            "title": await page.title(),
            "url": page.url,
            "text": text,
        }

    elif action == "back":
        page = await _ensure_browser()
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "close":
        await close_browser()
        return "Browser closed."

    elif action == "vnc_url":
        from bot.tools.browser_server import get_novnc_url
        url = get_novnc_url()
        return url if url else "noVNC not available (not on server or not started)"

    else:
        return f"Error: unknown action '{action}'. Available: navigate, click, type, press, scroll, screenshot, get_text, back, close, vnc_url"


async def close_browser():
    """Close the browser and cleanup."""
    global _page, _browser, _playwright
    if _page and not _page.is_closed():
        await _page.close()
    _page = None
    if _browser and _browser.is_connected():
        await _browser.close()
    _browser = None
    if _playwright:
        await _playwright.stop()
    _playwright = None
    log.info("browser closed")


# ── Tool schema ──────────────────────────────────────────────────────────────

BROWSER_TOOL = {
    "name": "browser",
    "description": (
        "Interactive web browser. Navigate websites, click elements, type text, scroll, "
        "and take screenshots. Use this to browse X/Twitter, Reddit, news sites, or any URL. "
        "Each action returns a screenshot so you can see the current page state. "
        "Use 'vnc_url' action to get the live view URL for debugging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "click", "type", "press",
                    "scroll", "screenshot", "get_text",
                    "back", "close", "vnc_url",
                ],
                "description": "The browser action to perform.",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for 'navigate' action).",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector to click or type into (for 'click'/'type' actions).",
            },
            "x": {
                "type": "number",
                "description": "X coordinate for click (alternative to selector).",
            },
            "y": {
                "type": "number",
                "description": "Y coordinate for click (alternative to selector).",
            },
            "text": {
                "type": "string",
                "description": "Text to type (for 'type' action).",
            },
            "key": {
                "type": "string",
                "description": "Key to press (for 'press' action, e.g. 'Enter', 'Tab').",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "Scroll direction (default: 'down').",
            },
            "amount": {
                "type": "number",
                "description": "Scroll amount in pixels (default: 500).",
            },
        },
        "required": ["action"],
    },
}
