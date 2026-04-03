"""Browser display server — Xvfb + x11vnc + noVNC + ngrok tunnel.

Manages the virtual display stack so the browser tool has a screen to render on,
and operators can watch in real-time via a noVNC web page.
"""

import asyncio
import os
import signal
import subprocess

from bot.logger import get_logger

log = get_logger("browser")

DISPLAY = ":99"
VNC_PORT = 5999
NOVNC_PORT = 6080

_xvfb_proc: subprocess.Popen | None = None
_vnc_proc: subprocess.Popen | None = None
_novnc_proc: subprocess.Popen | None = None
_ngrok_proc: subprocess.Popen | None = None
_novnc_url: str = ""


def _is_linux() -> bool:
    import platform
    return platform.system() == "Linux"


async def start_browser_server() -> str:
    """Start the display stack: Xvfb → x11vnc → noVNC → ngrok.

    Returns the public noVNC URL (ngrok), or empty string if not available.
    """
    global _xvfb_proc, _vnc_proc, _novnc_proc, _ngrok_proc, _novnc_url

    if not _is_linux():
        log.info("browser server: skipping on non-Linux (Xvfb not needed)")
        return ""

    # 1. Xvfb — virtual framebuffer
    if not _xvfb_proc:
        _xvfb_proc = subprocess.Popen(
            ["Xvfb", DISPLAY, "-screen", "0", "1280x720x24", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = DISPLAY
        await asyncio.sleep(0.5)
        log.info("Xvfb started on %s (pid=%d)", DISPLAY, _xvfb_proc.pid)

    # 2. x11vnc — expose Xvfb as VNC
    if not _vnc_proc:
        _vnc_proc = subprocess.Popen(
            [
                "x11vnc",
                "-display", DISPLAY,
                "-rfbport", str(VNC_PORT),
                "-nopw",         # no password (secured by ngrok)
                "-forever",      # don't exit after first client disconnects
                "-shared",       # allow multiple viewers
                "-noxdamage",
                "-q",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(0.5)
        log.info("x11vnc started on port %d (pid=%d)", VNC_PORT, _vnc_proc.pid)

    # 3. noVNC — web-based VNC viewer
    novnc_path = "/opt/novnc"
    if not _novnc_proc and os.path.isdir(novnc_path):
        _novnc_proc = subprocess.Popen(
            [
                "websockify",
                "--web", novnc_path,
                str(NOVNC_PORT),
                f"localhost:{VNC_PORT}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(0.5)
        log.info("noVNC started on port %d (pid=%d)", NOVNC_PORT, _novnc_proc.pid)
    elif not os.path.isdir(novnc_path):
        log.warning("noVNC not installed at %s — run scripts/install_browser.sh", novnc_path)

    # 4. ngrok tunnel for noVNC
    if not _ngrok_proc and _novnc_proc:
        try:
            _ngrok_proc = subprocess.Popen(
                ["ngrok", "http", str(NOVNC_PORT), "--log=stdout", "--log-level=warn"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(3)

            # Query ngrok API for public URL
            import json
            import urllib.request
            try:
                resp = urllib.request.urlopen("http://localhost:4041/api/tunnels", timeout=3)
                tunnels = json.loads(resp.read())["tunnels"]
                _novnc_url = next(
                    (t["public_url"] for t in tunnels if t["public_url"].startswith("https")),
                    "",
                )
            except Exception:
                # Try port 4040 (if SMS tunnel already uses 4040, ngrok may use 4041)
                try:
                    resp = urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3)
                    tunnels = json.loads(resp.read())["tunnels"]
                    for t in tunnels:
                        if str(NOVNC_PORT) in t.get("config", {}).get("addr", ""):
                            _novnc_url = t["public_url"]
                            break
                except Exception:
                    pass

            if _novnc_url:
                log.info("noVNC accessible at: %s", _novnc_url)
            else:
                log.warning("ngrok started but could not detect noVNC tunnel URL")
        except FileNotFoundError:
            log.warning("ngrok not found — noVNC only accessible locally at http://localhost:%d", NOVNC_PORT)

    return _novnc_url


def stop_browser_server() -> None:
    """Stop all display server processes."""
    global _xvfb_proc, _vnc_proc, _novnc_proc, _ngrok_proc, _novnc_url

    for name, proc in [
        ("ngrok-vnc", _ngrok_proc),
        ("noVNC", _novnc_proc),
        ("x11vnc", _vnc_proc),
        ("Xvfb", _xvfb_proc),
    ]:
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.info("stopped %s (pid=%d)", name, proc.pid)

    _xvfb_proc = _vnc_proc = _novnc_proc = _ngrok_proc = None
    _novnc_url = ""


def get_novnc_url() -> str:
    """Return the current noVNC public URL."""
    return _novnc_url
