"""
File Bridge Backend  (Universal fallback)
==========================================
Communicates with LabVIEW through JSON files in a shared directory.

How it works:
  1. MCP writes an input JSON file to a watched directory.
  2. A "bridge VI" running in LabVIEW polls the directory for new jobs.
  3. The bridge VI reads the input file, calls the target VI, writes the output.
  4. MCP reads the output file and returns results.

This backend requires the MCP_Bridge.vi to be running inside LabVIEW.
Generate it with:  python bridge_vi_generator.py

Compatible with:
  Any LabVIEW version that supports file I/O (2010+), Community Edition
  Windows, macOS, Linux – any platform LabVIEW runs on
  Also works when LabVIEW is on a different machine if bridge_dir is a network share

Configuration via environment variables:
  LABVIEW_BRIDGE_DIR     = path to the shared directory (required)
  LABVIEW_BRIDGE_TIMEOUT = seconds to wait for bridge response (default 60)
"""

from __future__ import annotations

import json
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ControlResult, LabVIEWBackend, RunResult, TestResult, VIInfo

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_BRIDGE_DIR     = os.path.join(
    os.environ.get("TEMP", "/tmp") if platform.system() == "Windows" else "/tmp",
    "labview_mcp_bridge",
)
_DEFAULT_TIMEOUT        = 60   # seconds
_POLL_INTERVAL          = 0.3  # seconds between file checks


class FileBackend(LabVIEWBackend):
    """
    Communicates with LabVIEW via JSON files in a shared bridge directory.
    Universal: works on any OS, any LabVIEW version, Community Edition.
    Requires MCP_Bridge.vi running inside LabVIEW.
    """

    def __init__(
        self,
        bridge_dir: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self._bridge_dir = bridge_dir or os.environ.get(
            "LABVIEW_BRIDGE_DIR", _DEFAULT_BRIDGE_DIR
        )
        self._timeout = timeout or int(
            os.environ.get("LABVIEW_BRIDGE_TIMEOUT", _DEFAULT_TIMEOUT)
        )
        os.makedirs(self._bridge_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "file"

    @property
    def supports_control_io(self) -> bool:
        return True   # via JSON request/response

    @property
    def supports_vi_scripting(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        # Available if the bridge directory exists and is writable
        return os.path.isdir(self._bridge_dir) and os.access(self._bridge_dir, os.W_OK)

    # ------------------------------------------------------------------
    # Internal: job dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, operation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write a job file and wait for the bridge VI to write the response.

        Job file:    <bridge_dir>/<job_id>.job.json
        Result file: <bridge_dir>/<job_id>.result.json
        Error file:  <bridge_dir>/<job_id>.error.json
        """
        job_id    = str(uuid.uuid4())
        job_file  = os.path.join(self._bridge_dir, f"{job_id}.job.json")
        result_file = os.path.join(self._bridge_dir, f"{job_id}.result.json")
        error_file  = os.path.join(self._bridge_dir, f"{job_id}.error.json")

        job = {"job_id": job_id, "operation": operation, **payload}
        with open(job_file, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)

        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            if os.path.isfile(result_file):
                with open(result_file, "r", encoding="utf-8") as f:
                    result = json.load(f)
                try:
                    os.remove(result_file)
                except OSError:
                    pass
                return result
            if os.path.isfile(error_file):
                with open(error_file, "r", encoding="utf-8") as f:
                    err = json.load(f)
                try:
                    os.remove(error_file)
                except OSError:
                    pass
                raise RuntimeError(f"Bridge VI error: {err.get('message', str(err))}")
            time.sleep(_POLL_INTERVAL)

        # Timeout: clean up job file
        try:
            os.remove(job_file)
        except OSError:
            pass
        raise TimeoutError(
            f"Bridge VI did not respond within {self._timeout}s. "
            "Ensure MCP_Bridge.vi is running in LabVIEW."
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        try:
            result = self._dispatch("get_version", {})
            return f"LabVIEW {result.get('version', 'unknown')} (File Bridge backend)"
        except TimeoutError:
            return (
                f"File Bridge backend configured (dir: {self._bridge_dir}) – "
                "bridge VI not responding."
            )

    # ------------------------------------------------------------------
    # VI Management
    # ------------------------------------------------------------------

    def get_vi_info(self, vi_path: str) -> VIInfo:
        result = self._dispatch("get_vi_info", {"vi_path": vi_path})
        return VIInfo(
            name=result.get("name", Path(vi_path).name),
            path=vi_path,
            execution_state=result.get("execution_state", "unknown"),
            description=result.get("description", ""),
        )

    def save_vi(self, vi_path: str, save_as: Optional[str] = None) -> bool:
        self._dispatch("save_vi", {"vi_path": vi_path, "save_as": save_as})
        return True

    def mass_compile(self, directory: str) -> str:
        self._dispatch("mass_compile", {"directory": directory})
        return f"Mass compile completed for: {directory}"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_vi(
        self,
        vi_path: str,
        inputs: Optional[Dict[str, Any]] = None,
        wait_until_done: bool = True,
    ) -> RunResult:
        try:
            result = self._dispatch(
                "run_vi",
                {"vi_path": vi_path, "inputs": inputs or {}, "wait": wait_until_done},
            )
            return RunResult(
                success=result.get("success", True),
                vi_path=vi_path,
                execution_state=result.get("execution_state", "idle"),
            )
        except Exception as exc:
            return RunResult(success=False, vi_path=vi_path, error=str(exc))

    def abort_vi(self, vi_path: str) -> bool:
        self._dispatch("abort_vi", {"vi_path": vi_path})
        return True

    # ------------------------------------------------------------------
    # Control I/O
    # ------------------------------------------------------------------

    def get_control_value(self, vi_path: str, control_name: str) -> ControlResult:
        try:
            result = self._dispatch(
                "get_control",
                {"vi_path": vi_path, "control_name": control_name},
            )
            return ControlResult(
                vi_path=vi_path,
                control_name=control_name,
                value=result.get("value"),
            )
        except Exception as exc:
            return ControlResult(vi_path=vi_path, control_name=control_name, error=str(exc))

    def set_control_value(self, vi_path: str, control_name: str, value: Any) -> bool:
        self._dispatch(
            "set_control",
            {"vi_path": vi_path, "control_name": control_name, "value": value},
        )
        return True

    # ------------------------------------------------------------------
    # VI Scripting  (not supported)
    # ------------------------------------------------------------------

    def generate_vi(
        self,
        vi_path: str,
        description: str = "",
        controls: Optional[List[Dict[str, Any]]] = None,
        indicators: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "VI Scripting is not supported by the File Bridge backend. Use the COM backend."
        )
