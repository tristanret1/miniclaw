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
_context = None    # playwright BrowserContext (persistent)
_playwright = None # playwright instance

# Persistent profile directory — cookies/sessions survive restarts
from bot.config import PROJECT_ROOT
BROWSER_DATA_DIR = PROJECT_ROOT / "workspace" / "browser_data"


async def _ensure_browser():
    """Lazy-init Playwright with persistent context (preserves login sessions)."""
    global _playwright, _context, _page

    if _page and not _page.is_closed():
        return _page

    from playwright.async_api import async_playwright

    if not _playwright:
        _playwright = await async_playwright().start()

    if not _context:
        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,  # headed mode so Xvfb/VNC can see it
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
            args=[
                "--no-sandbox",
                "--disable-gpu",
            ],
        )
        log.info("browser: persistent context opened (data=%s)", BROWSER_DATA_DIR)

    if not _page or _page.is_closed():
        _page = _context.pages[0] if _context.pages else await _context.new_page()
        log.info("browser: page ready")

    return _page


_LOGIN_KEYWORDS = [
    "login", "log in", "sign in", "signin", "signup", "sign up",
    "authenticate", "oauth", "authorize", "sso",
    "登录", "登陆", "注册",
]


def _detect_login_page(url: str, title: str) -> bool:
    """Check if the current page looks like a login/auth page."""
    check = (url + " " + title).lower()
    return any(kw in check for kw in _LOGIN_KEYWORDS)


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
        title = await page.title()
        screenshot = await _take_screenshot()
        result = {
            "type": "screenshot",
            "title": title,
            "url": page.url,
            "screenshot_base64": screenshot,
        }
        if _detect_login_page(page.url, title):
            result["login_required"] = True
            result["hint"] = (
                "This page requires login. Use 'wait_for_user' action to pause and let "
                "the user log in manually (via the browser window or noVNC). "
                "Do NOT attempt to fill in credentials yourself."
            )
        return result

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

    elif action == "wait":
        seconds = int(kwargs.get("seconds", 3))
        seconds = min(seconds, 30)
        await asyncio.sleep(seconds)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url if (page := await _ensure_browser()) else "",
            "screenshot_base64": screenshot,
        }

    elif action == "wait_for_user":
        # Pause and let user interact with the browser manually (e.g. login).
        # Polls every 5s for up to 120s, checking if the page URL changes
        # (indicating the user completed login and got redirected).
        timeout = min(int(kwargs.get("timeout", 120)), 300)
        page = await _ensure_browser()
        original_url = page.url
        log.info("browser: waiting for user action (url=%s, timeout=%ds)", original_url, timeout)

        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(5)
            elapsed += 5
            current_url = page.url
            current_title = await page.title()
            # User navigated away from login page = probably logged in
            if current_url != original_url and not _detect_login_page(current_url, current_title):
                log.info("browser: user action detected, page changed to %s", current_url)
                screenshot = await _take_screenshot()
                return {
                    "type": "screenshot",
                    "title": current_title,
                    "url": current_url,
                    "screenshot_base64": screenshot,
                    "user_action": "login_completed",
                }

        # Timeout — take screenshot of whatever state we're in
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "title": await page.title(),
            "url": page.url,
            "screenshot_base64": screenshot,
            "user_action": "timeout",
            "hint": "User did not complete action within timeout. You can try again or proceed.",
        }

    elif action == "close":
        await close_browser()
        return "Browser closed. Login sessions are preserved."

    elif action == "vnc_url":
        from bot.tools.browser_server import get_novnc_url
        url = get_novnc_url()
        return url if url else "noVNC not available (not on server or not started)"

    else:
        return f"Error: unknown action '{action}'. Available: navigate, click, type, press, scroll, screenshot, get_text, wait, back, close, vnc_url"


async def close_browser():
    """Close the browser. Persistent data (cookies/sessions) is preserved on disk."""
    global _page, _context, _playwright
    _page = None
    if _context:
        await _context.close()
    _context = None
    if _playwright:
        await _playwright.stop()
    _playwright = None
    log.info("browser closed (data preserved at %s)", BROWSER_DATA_DIR)


# ── Tool schema ──────────────────────────────────────────────────────────────

BROWSER_TOOL = {
    "name": "browser",
    "description": (
        "Interactive web browser. Navigate websites, click elements, type text, scroll, "
        "and take screenshots. Use this to browse X/Twitter, Reddit, news sites, or any URL. "
        "Each action returns a screenshot so you can see the current page state. "
        "IMPORTANT: If a page requires login (login_required=true in response), "
        "use 'wait_for_user' to pause and let the user log in manually. "
        "NEVER attempt to fill in login credentials yourself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "click", "type", "press",
                    "scroll", "screenshot", "get_text",
                    "wait", "wait_for_user", "back", "close", "vnc_url",
                ],
                "description": "The browser action to perform. Use 'wait_for_user' when login is needed — pauses up to 120s for user to log in manually.",
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
            "seconds": {
                "type": "number",
                "description": "Seconds to wait (for 'wait' action, max 30).",
            },
            "timeout": {
                "type": "number",
                "description": "Max seconds to wait for user action (for 'wait_for_user', default 120, max 300).",
            },
        },
        "required": ["action"],
    },
}
