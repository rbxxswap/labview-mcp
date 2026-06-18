"""
Backend factory and auto-detection for the LabVIEW MCP Server.

Priority order (AUTO mode):
  1. COM   – Windows-only, richest feature set, no extra setup
  2. CLI   – Cross-platform, needs LabVIEW 2018+, limited I/O
  3. HTTP  – Cross-platform, needs Web Service configured in project
  4. File  – Universal fallback, needs MCP_Bridge.vi running in LabVIEW

Configure via environment variables:
  LABVIEW_BACKEND = auto | com | cli | http | file
"""

from __future__ import annotations

import os

from .base import LabVIEWBackend
from .cli_backend import CLIBackend
from .com_backend import COMBackend
from .file_backend import FileBackend
from .http_backend import HTTPBackend

__all__ = [
    "LabVIEWBackend",
    "COMBackend",
    "CLIBackend",
    "HTTPBackend",
    "FileBackend",
    "get_backend",
]


def get_backend(backend_type: str = "auto") -> LabVIEWBackend:
    """
    Return the appropriate LabVIEW backend.

    Args:
        backend_type: "auto" | "com" | "cli" | "http" | "file"
                      Defaults to the LABVIEW_BACKEND env var, then "auto".

    Raises:
        RuntimeError: If the requested backend is unavailable.
    """
    choice = (backend_type or os.environ.get("LABVIEW_BACKEND", "auto")).lower().strip()

    if choice == "com":
        b = COMBackend()
        if not b.is_available:
            raise RuntimeError(
                "COM backend requested but pywin32 is not installed or "
                "this is not a Windows environment."
            )
        return b

    if choice == "cli":
        b = CLIBackend()
        if not b.is_available:
            raise RuntimeError(
                "CLI backend requested but LabVIEWCLI executable was not found. "
                "Set LABVIEW_CLI_PATH or install LabVIEW 2018+."
            )
        return b

    if choice == "http":
        b = HTTPBackend()
        if not b.is_available:
            raise RuntimeError(
                "HTTP backend requested but httpx is not installed. "
                "Run: pip install httpx"
            )
        return b

    if choice == "file":
        b = FileBackend()
        if not b.is_available:
            raise RuntimeError(
                "File Bridge backend requested but bridge directory is not accessible. "
                "Set LABVIEW_BRIDGE_DIR to a writable directory and start MCP_Bridge.vi."
            )
        return b

    if choice == "auto":
        # Try each in priority order; return first that is available
        candidates = [COMBackend(), CLIBackend(), HTTPBackend(), FileBackend()]
        for candidate in candidates:
            if candidate.is_available:
                return candidate
        raise RuntimeError(
            "No LabVIEW backend is available. "
            "Install LabVIEW and at least one of: pywin32 (COM), "
            "LabVIEW 2018+ (CLI), httpx (HTTP), or configure LABVIEW_BRIDGE_DIR (File)."
        )

    raise ValueError(
        f"Unknown backend type '{choice}'. "
        "Valid values: auto, com, cli, http, file"
    )
