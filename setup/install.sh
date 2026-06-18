#!/usr/bin/env bash
# LabVIEW MCP Plugin — macOS / Linux Setup Script
# Run once after installing the plugin.

set -e

echo "================================================"
echo " LabVIEW MCP Plugin — Dependency Installer"
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install Python 3.10+ from https://python.org or via your package manager."
    echo "  macOS:  brew install python"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python $PYTHON_VERSION found: $(which python3)"
echo ""

# Core dependencies
echo "Installing core dependencies (mcp, pydantic, nptdms)..."
pip3 install "mcp[cli]>=1.3.0" "pydantic>=2.0.0" "nptdms>=1.5.0" --break-system-packages 2>/dev/null \
    || pip3 install "mcp[cli]>=1.3.0" "pydantic>=2.0.0" "nptdms>=1.5.0"

# HTTP backend
echo ""
echo "Installing HTTP backend (httpx)..."
pip3 install "httpx>=0.27.0" --break-system-packages 2>/dev/null \
    || pip3 install "httpx>=0.27.0"

echo ""
echo "================================================"
echo " Installation complete!"
echo ""
echo " Backend availability:"
echo "   COM:       ❌ (Windows only)"
echo "   CLI:       ✅ if LabVIEW 2018+ is installed"
echo "   HTTP:      ✅ if Web Service configured"
echo "   File:      ✅ if MCP_Bridge.vi is running"
echo ""
echo " Restart Claude Desktop to activate the plugin."
echo "================================================"
