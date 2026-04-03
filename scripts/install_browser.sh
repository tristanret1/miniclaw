#!/bin/bash
# Install system dependencies for browser tool (Xvfb + VNC + noVNC + Chromium)
# Run on Ubuntu/Debian server: sudo bash scripts/install_browser.sh

set -euo pipefail

echo "=== Installing browser tool dependencies ==="

# Xvfb (virtual framebuffer), x11vnc, and misc X11 libs
apt-get update -qq
apt-get install -y -qq \
    xvfb \
    x11vnc \
    xdg-utils \
    fonts-noto-cjk \
    > /dev/null 2>&1
echo "✓ Xvfb + x11vnc + CJK fonts"

# noVNC (web-based VNC client)
if [ ! -d /opt/novnc ]; then
    git clone --depth 1 https://github.com/novnc/noVNC.git /opt/novnc
    ln -sf /opt/novnc/vnc_lite.html /opt/novnc/index.html
    echo "✓ noVNC installed to /opt/novnc"
else
    echo "✓ noVNC already installed"
fi

# websockify (noVNC needs it to bridge WebSocket → VNC)
if ! command -v websockify &>/dev/null; then
    pip3 install -q websockify
    echo "✓ websockify installed"
else
    echo "✓ websockify already installed"
fi

# Playwright browsers (Chromium)
echo "Installing Playwright Chromium..."
if [ -x "venv/bin/python" ]; then
    venv/bin/python -m playwright install chromium --with-deps 2>/dev/null
else
    python3 -m playwright install chromium --with-deps 2>/dev/null
fi
echo "✓ Playwright Chromium"

echo "=== Browser tool dependencies installed ==="
