"""browser tool — 基于 Playwright 的交互式浏览器工具。

功能：导航、点击、输入、滚动、截图、结构化文本提取。
默认返回结构化文本（省 token）；仅在需要视觉布局时返回截图。
内置 stealth 模式，绕过常见的自动化检测。
"""

import asyncio
import base64
import json
import os
from typing import Any

from bot.logger import get_logger

log = get_logger("browser")

_page = None       # 当前活跃的 Playwright Page
_context = None    # 持久化 BrowserContext（保留 cookie / session）
_playwright = None # Playwright 实例

# 持久化用户数据目录 — cookie / localStorage 在重启后仍然保留
from bot.config import PROJECT_ROOT
BROWSER_DATA_DIR = PROJECT_ROOT / "workspace" / "browser_data"

# ── Stealth 反检测 ──────────────────────────────────────────────────────────
# 通过 Chrome 启动参数 + 注入 JS 来隐藏 Playwright 的自动化特征，
# 避免被 Cloudflare、Akamai 等 WAF 和网站反爬机制识别。

_STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",   # 隐藏 navigator.webdriver
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",                               # 隐藏 "Chrome is being controlled" 横幅
]

_STEALTH_JS = """
// 隐藏 webdriver 标志 — 多数反爬第一步就检测这个
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 伪造 plugins 数组 — 真实浏览器至少有几个插件，空数组是明显的自动化特征
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// 伪造语言列表 — 与 locale 配置一致
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en-US', 'en'],
});

// 伪造 window.chrome 对象 — 真实 Chrome 浏览器都有这个属性
if (window.chrome === undefined) {
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
}

// 伪造 Permissions API — 避免被通过权限查询方式检测
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


async def _apply_stealth(page):
    """向页面注入 stealth 脚本（用于单页面场景）。"""
    await page.add_init_script(_STEALTH_JS)


async def _ensure_browser():
    """懒初始化 Playwright 持久化浏览器上下文。

    特性：
    - 持久化 context：cookie / session 跨重启保留
    - Stealth 模式：自动注入反检测脚本
    - Headed 模式：配合 Xvfb/noVNC 可远程查看浏览器画面
    """
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
            headless=False,                    # headed 模式，配合 VNC 使用
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
            user_agent=(                       # 伪造真实 Chrome UA
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            args=_STEALTH_ARGS,
        )
        # 对 context 下所有新开页面自动注入 stealth JS
        await _context.add_init_script(_STEALTH_JS)
        log.info("browser: persistent context opened with stealth (data=%s)", BROWSER_DATA_DIR)

    if not _page or _page.is_closed():
        # 优先复用已有 tab，避免重复打开空白页
        _page = _context.pages[0] if _context.pages else await _context.new_page()
        log.info("browser: page ready")

    return _page


# ── crawl4ai 后端（可选） ───────────────────────────────────────────────────
# 设置环境变量 BROWSER_BACKEND=crawl4ai 可切换到 crawl4ai 做内容提取。
# crawl4ai 是无状态的，适合纯抓取场景；不支持交互操作（click/type 等）。

def _use_crawl4ai() -> bool:
    """检查是否启用 crawl4ai 后端。"""
    return os.getenv("BROWSER_BACKEND", "").strip().lower() == "crawl4ai"


async def _crawl4ai_fetch(url: str, include_screenshot: bool = False) -> dict:
    """通过 crawl4ai 抓取页面，返回标准化的结果字典。

    crawl4ai 的 API 在不同版本间有差异（类名、字段名），
    这里做了兼容处理，尽量支持新旧版本。
    """
    try:
        import importlib
        # 尝试从顶层模块导入（新版 API）
        bu = importlib.import_module("crawl4ai")
        AsyncWebCrawler = getattr(bu, "AsyncWebCrawler", None)
        BrowserConfig = getattr(bu, "BrowserConfig", None)
        CrawlerRunConfig = getattr(bu, "CrawlerRunConfig", None)
        if AsyncWebCrawler is None:
            # 旧版可能放在子模块下
            bu_agent = importlib.import_module("crawl4ai.crawler")
            AsyncWebCrawler = getattr(bu_agent, "AsyncWebCrawler")
            bu_browser = importlib.import_module("crawl4ai.browser")
            BrowserConfig = getattr(bu_browser, "BrowserConfig")
            CrawlerRunConfig = getattr(bu, "CrawlerRunConfig", None) or getattr(bu_agent, "CrawlerRunConfig", None)
    except Exception:
        return {"type": "error", "error": "crawl4ai not installed. Set BROWSER_BACKEND= and use Playwright, or install crawl4ai."}

    # headed 模式，方便通过 VNC 观察
    bcfg = BrowserConfig(headless=False, user_data_dir=str(BROWSER_DATA_DIR)) if BrowserConfig else None
    run_cfg = CrawlerRunConfig(screenshot=include_screenshot) if CrawlerRunConfig else None

    try:
        # 兼容两种用法：context manager vs 普通实例
        if hasattr(AsyncWebCrawler, "__aenter__"):
            async with AsyncWebCrawler(config=bcfg) as crawler:
                result = await crawler.arun(url=url, config=run_cfg)
        else:
            crawler = AsyncWebCrawler(config=bcfg)
            result = await crawler.arun(url=url, config=run_cfg)

        # 跨版本字段标准化
        title = getattr(result, "title", None) or getattr(result, "page_title", "") or ""
        final_url = getattr(result, "url", None) or getattr(result, "final_url", url) or url
        text = (
            getattr(result, "cleaned_html", None)
            or getattr(result, "markdown", None)
            or getattr(result, "content", None)
            or ""
        )
        if isinstance(text, bytes):
            try:
                text = text.decode("utf-8", errors="ignore")
            except Exception:
                text = ""

        out = {"type": "text", "title": title, "url": final_url, "text": text}

        if include_screenshot:
            shot = getattr(result, "screenshot", None)
            if shot:
                if isinstance(shot, bytes):
                    out["screenshot_base64"] = base64.b64encode(shot).decode()
                elif isinstance(shot, str):  # 部分版本直接返回 base64 字符串
                    out["screenshot_base64"] = shot
        return out
    except Exception as e:
        return {"type": "error", "error": f"crawl4ai fetch failed: {e}"}


# 登录页面检测关键词（中英文）
_LOGIN_KEYWORDS = [
    "login", "log in", "sign in", "signin", "signup", "sign up",
    "authenticate", "oauth", "authorize", "sso",
    "登录", "登陆", "注册",
]


def _detect_login_page(url: str, title: str) -> bool:
    """根据 URL 和标题中的关键词判断是否为登录页。"""
    check = (url + " " + title).lower()
    return any(kw in check for kw in _LOGIN_KEYWORDS)


async def _take_screenshot() -> str:
    """截取当前页面，返回 base64 编码的 PNG 字符串。"""
    page = await _ensure_browser()
    data = await page.screenshot(type="png")
    return base64.b64encode(data).decode()


# ── 结构化文本提取（省 token 的核心） ──────────────────────────────────────
#
# 传统方式：每次操作都截图发给 LLM → 一张 1280x720 截图 ≈ 1600 tokens。
# 新方式：在浏览器端用 JS 提取结构化文本 → 同等信息量只需 ~1000-3000 tokens。
#
# 额外好处：纯文本的历史记录前缀稳定，有利于 Claude 的 prompt cache 命中。
# 截图因为每次像素不同，会导致 cache miss，整段历史每轮都重新计费。

_EXTRACT_JS = """
() => {
    // 第一步：标记噪声元素（导航栏、页脚、广告、弹窗等）
    // 这些元素通常不包含有用内容，去掉可以大幅减少输出
    const noise = document.querySelectorAll(
        'script, style, noscript, iframe, svg, nav, footer, header, '
        + '[role="navigation"], [role="banner"], [role="contentinfo"], '
        + '.ad, .ads, .advertisement, .sidebar, .cookie-banner, '
        + '#cookie-consent, .popup, .modal'
    );
    const removed = new Set();
    noise.forEach(el => { removed.add(el); });

    // 可见性检查 — 跳过 display:none / visibility:hidden / opacity:0 的元素
    function isVisible(el) {
        if (removed.has(el)) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden'
            && style.opacity !== '0';
    }

    // 第二步：提取可见链接（供 LLM 判断可点击的交互元素）
    const links = [];
    document.querySelectorAll('a[href]').forEach((a, i) => {
        if (!isVisible(a)) return;
        const text = a.innerText.trim().slice(0, 80);
        if (text) links.push({i, text, href: a.href});
    });

    // 第三步：提取表单元素（input / textarea / select / button）
    const inputs = [];
    document.querySelectorAll('input, textarea, select, button').forEach((el, i) => {
        if (!isVisible(el)) return;
        const tag = el.tagName.toLowerCase();
        const type = el.type || tag;
        const name = el.name || el.id || el.placeholder || el.ariaLabel || '';
        const val = el.value || '';
        const label = el.labels?.[0]?.innerText?.trim() || '';
        inputs.push({i, tag, type, name: name.slice(0, 50), label: label.slice(0, 50), value: val.slice(0, 50)});
    });

    // 第四步：提取主体文本内容
    // 优先从语义化容器（main / article）提取，回退到 body
    const main = document.querySelector('main, article, [role="main"], .content, #content')
        || document.body;

    // 递归提取文本，将 HTML 结构转换为类 Markdown 格式
    function extractText(node, depth) {
        if (depth > 10 || removed.has(node)) return '';
        if (node.nodeType === Node.TEXT_NODE) return node.textContent.trim();
        if (!isVisible(node)) return '';

        const tag = node.tagName?.toLowerCase() || '';
        const parts = [];

        // 标题 → Markdown 风格 (# / ## / ### ...)
        if (/^h[1-6]$/.test(tag)) {
            const level = parseInt(tag[1]);
            const text = node.innerText.trim();
            if (text) parts.push('#'.repeat(level) + ' ' + text);
            return parts.join('');
        }

        for (const child of node.childNodes) {
            const t = extractText(child, depth + 1);
            if (t) parts.push(t);
        }

        // 块级元素用换行分隔，行内元素用空格
        let joined = parts.join(tag === 'div' || tag === 'p' || tag === 'li' || tag === 'tr' ? '\\n' : ' ');

        // 列表项 → Markdown 风格 (- item)
        if (tag === 'li') joined = '- ' + joined;

        return joined;
    }

    let text = extractText(main, 0);
    // 合并多余空白
    text = text.replace(/[ \\t]+/g, ' ').replace(/\\n{3,}/g, '\\n\\n').trim();

    return JSON.stringify({
        title: document.title,
        url: location.href,
        text: text.slice(0, 12000),     // 限制最大长度，避免超长页面爆 token
        links: links.slice(0, 30),      // 最多 30 个链接
        inputs: inputs.slice(0, 20),    // 最多 20 个表单元素
    });
}
"""


async def _extract_page_content(page) -> dict:
    """从当前页面提取结构化文本内容。

    返回格式化的文本，包含：标题、正文、表单元素、链接列表。
    相比截图可节省约 10 倍 token，且对 prompt cache 更友好。
    """
    try:
        raw = await page.evaluate(_EXTRACT_JS)
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        # JS 提取失败时回退到 innerText（不含结构信息，但至少有内容）
        log.warning("structured extraction failed, falling back: %s", e)
        text = await page.inner_text("body")
        data = {
            "title": await page.title(),
            "url": page.url,
            "text": text[:12000],
            "links": [],
            "inputs": [],
        }

    # 组装为人类可读 + LLM 友好的文本格式
    parts = [f"Title: {data.get('title', '')}", f"URL: {data.get('url', '')}"]

    text = data.get("text", "")
    if text:
        parts.append(f"\n--- Page Content ---\n{text}")

    # 表单元素（帮助 LLM 决定下一步交互动作）
    inputs = data.get("inputs", [])
    if inputs:
        input_lines = []
        for inp in inputs:
            desc = f"[{inp['type']}]"
            if inp.get("label"):
                desc += f" {inp['label']}"
            elif inp.get("name"):
                desc += f" name={inp['name']}"
            if inp.get("value"):
                desc += f" value=\"{inp['value']}\""
            input_lines.append(f"  {desc}")
        parts.append("\n--- Interactive Elements ---\n" + "\n".join(input_lines))

    # 链接列表（带索引，方便 LLM 引用）
    links = data.get("links", [])
    if links:
        link_lines = [f"  [{l['i']}] {l['text']} → {l['href']}" for l in links[:20]]
        parts.append("\n--- Links ---\n" + "\n".join(link_lines))

    return {
        "type": "text",
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "text": "\n".join(parts),
    }


# ── 工具动作入口 ────────────────────────────────────────────────────────────
#
# 所有动作默认返回结构化文本；设置 include_screenshot=True 或使用 "screenshot"
# 动作才会返回截图。这样设计是因为：
#   1. 文本比截图省 ~10 倍 token
#   2. 文本历史不会破坏 prompt cache（截图的 base64 每次不同 → cache miss）

async def run_browser(action: str, **kwargs) -> str | dict:
    """执行浏览器动作，返回结构化文本或截图 dict。"""

    include_screenshot = kwargs.get("include_screenshot", False)

    if action == "navigate":
        # 导航到指定 URL
        url = kwargs.get("url", "")
        if not url:
            return "Error: url is required"

        # crawl4ai 后端路径（无状态抓取）
        if _use_crawl4ai():
            res = await _crawl4ai_fetch(url, include_screenshot=include_screenshot)
            if res.get("type") == "error":
                return res["error"]
            if include_screenshot:
                return {
                    "type": "screenshot",
                    "title": res.get("title", ""),
                    "url": res.get("url", url),
                    "screenshot_base64": res.get("screenshot_base64", ""),
                }
            text = res.get("text", "")
            if len(text) > 12000:
                text = text[:12000] + "\n...(truncated)"
            return {"type": "text", "title": res.get("title", ""), "url": res.get("url", url), "text": text}

        # Playwright 路径
        page = await _ensure_browser()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            return f"Error navigating to {url}: {e}"
        title = await page.title()

        # 检测到登录页时强制返回截图 — 用户需要看到页面才能手动登录
        if _detect_login_page(page.url, title):
            screenshot = await _take_screenshot()
            return {
                "type": "screenshot",
                "title": title,
                "url": page.url,
                "screenshot_base64": screenshot,
                "login_required": True,
                "hint": (
                    "This page requires login. Use 'wait_for_user' action to pause and let "
                    "the user log in manually (via the browser window or noVNC). "
                    "Do NOT attempt to fill in credentials yourself."
                ),
            }

        # 默认返回结构化文本
        if include_screenshot:
            screenshot = await _take_screenshot()
            return {"type": "screenshot", "title": title, "url": page.url, "screenshot_base64": screenshot}
        return await _extract_page_content(page)

    elif action == "click":
        # 点击元素 — 支持 CSS selector 或 (x, y) 坐标两种方式
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
        await asyncio.sleep(0.5)  # 等待页面渲染稳定
        if include_screenshot:
            screenshot = await _take_screenshot()
            return {"type": "screenshot", "url": page.url, "screenshot_base64": screenshot}
        return await _extract_page_content(page)

    elif action == "type":
        # 输入文本 — 有 selector 时用 fill()（直接赋值），否则用 keyboard.type()（逐字输入）
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
        if include_screenshot:
            screenshot = await _take_screenshot()
            return {"type": "screenshot", "url": page.url, "screenshot_base64": screenshot}
        return await _extract_page_content(page)

    elif action == "press":
        # 按下键盘按键（Enter / Tab / Escape 等）
        key = kwargs.get("key", "Enter")
        page = await _ensure_browser()
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)
        if include_screenshot:
            screenshot = await _take_screenshot()
            return {"type": "screenshot", "url": page.url, "screenshot_base64": screenshot}
        return await _extract_page_content(page)

    elif action == "scroll":
        # 页面滚动 — 用鼠标滚轮模拟，支持指定方向和像素量
        direction = kwargs.get("direction", "down")
        amount = int(kwargs.get("amount", 500))
        page = await _ensure_browser()
        delta = amount if direction == "down" else -amount
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(0.5)
        if include_screenshot:
            screenshot = await _take_screenshot()
            return {"type": "screenshot", "url": page.url, "screenshot_base64": screenshot}
        return await _extract_page_content(page)

    elif action == "screenshot":
        # 显式截图动作 — 总是返回图片（不受 include_screenshot 参数影响）
        url = kwargs.get("url", "")
        if _use_crawl4ai() and url:
            res = await _crawl4ai_fetch(url, include_screenshot=True)
            if res.get("type") == "error":
                return res["error"]
            return {
                "type": "screenshot",
                "title": res.get("title", ""),
                "url": res.get("url", url),
                "screenshot_base64": res.get("screenshot_base64", ""),
            }
        page = await _ensure_browser()
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "title": await page.title(),
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "get_text":
        # 纯文本提取 — 类似 navigate 但不导航，只提取当前页面内容
        url = kwargs.get("url", "")
        if _use_crawl4ai() and url:
            res = await _crawl4ai_fetch(url, include_screenshot=False)
            if res.get("type") == "error":
                return res["error"]
            text = res.get("text", "")
            if len(text) > 12000:
                text = text[:12000] + "\n...(truncated)"
            return {
                "type": "text",
                "title": res.get("title", ""),
                "url": res.get("url", url),
                "text": text,
            }
        page = await _ensure_browser()
        return await _extract_page_content(page)

    elif action == "back":
        # 浏览器后退
        page = await _ensure_browser()
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
        screenshot = await _take_screenshot()
        return {
            "type": "screenshot",
            "url": page.url,
            "screenshot_base64": screenshot,
        }

    elif action == "wait":
        # 等待指定秒数（上限 30s），然后截图返回当前状态
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
        # 等待用户手动操作（典型场景：登录）。
        # 每 5 秒轮询一次页面 URL，如果发生跳转且不再是登录页，视为操作完成。
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
            # URL 变化且不再是登录页 → 用户应该已经登录成功
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

        # 超时 — 截图返回当前状态，让 LLM 决定下一步
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
        # 返回 noVNC 的 URL，供用户远程查看浏览器画面
        from bot.tools.browser_server import get_novnc_url
        url = get_novnc_url()
        return url if url else "noVNC not available (not on server or not started)"

    else:
        return f"Error: unknown action '{action}'. Available: navigate, click, type, press, scroll, screenshot, get_text, wait, back, close, vnc_url"


async def close_browser():
    """关闭浏览器。持久化数据（cookie / session）保留在磁盘上，下次启动自动恢复。"""
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
        "Interactive web browser with stealth mode. Navigate websites, click elements, type text, scroll, "
        "and extract content. By default returns structured text (title, content, links, form elements) "
        "which is much more token-efficient than screenshots. Use 'screenshot' action or set "
        "include_screenshot=true only when you need to see the visual layout. "
        "Use 'get_text' for content extraction. "
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
                "description": (
                    "The browser action to perform. Most actions return structured text by default. "
                    "Use 'screenshot' to explicitly get a visual capture. "
                    "Use 'wait_for_user' when login is needed."
                ),
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
            "include_screenshot": {
                "type": "boolean",
                "description": (
                    "If true, return a screenshot image instead of structured text. "
                    "Only use when visual layout matters (e.g. checking element positions, "
                    "verifying CSS, seeing images). Default: false."
                ),
            },
        },
        "required": ["action"],
    },
}
