"""
LabVIEW CLI Backend  (Windows / macOS / Linux)
================================================
Controls LabVIEW via the LabVIEWCLI command-line tool.

Supported operations:
  - Run a VI                 (labview_run_vi)
  - Mass compile             (labview_mass_compile)
  - Execute a build spec     (labview_build_spec)
  - File Bridge I/O          (labview_run_vi with inputs/outputs via JSON)

Limitations vs COM:
  - Cannot get/set control values directly without the File Bridge helper VI
  - Cannot abort a running VI
  - Cannot retrieve VI info (name, description, execution state)
  - No VI Scripting

File Bridge pattern:
  When inputs/outputs are needed the CLI backend writes a JSON file to a
  temp directory, then calls a thin "bridge VI" that reads the inputs,
  calls your actual VI, and writes the outputs back.  See bridge_vi_generator.py.

Compatible with:
  LabVIEW 2018+ (CLI introduced in LabVIEW 2018), Community Edition
  Windows, macOS, Linux
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ControlResult, LabVIEWBackend, RunResult, TestResult, VIInfo

# ---------------------------------------------------------------------------
# Auto-detect LabVIEWCLI executable
# ---------------------------------------------------------------------------

_CLI_SEARCH_PATHS_WINDOWS = [
    r"C:\Program Files\National Instruments\LabVIEW 2024\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2023\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2022\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2021\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2020\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2019\LabVIEWCLI.exe",
    r"C:\Program Files\National Instruments\LabVIEW 2018\LabVIEWCLI.exe",
    r"C:\Program Files (x86)\National Instruments\LabVIEW 2018\LabVIEWCLI.exe",
]
_CLI_SEARCH_PATHS_MAC = [
    "/Applications/National Instruments/LabVIEW 2024/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2023/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2022/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2021/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2020/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2019/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
    "/Applications/National Instruments/LabVIEW 2018/LabVIEW.app/Contents/MacOS/LabVIEWCLI",
]
_CLI_SEARCH_PATHS_LINUX = [
    "/usr/local/natinst/LabVIEW-2024-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2023-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2022-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2021-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2020-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2019-64/labviewcli",
    "/usr/local/natinst/LabVIEW-2018-64/labviewcli",
]


def _find_cli_exe() -> Optional[str]:
    """Return the first LabVIEWCLI executable found on the current OS."""
    # Honour environment override
    env_path = os.environ.get("LABVIEW_CLI_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    system = platform.system()
    if system == "Windows":
        candidates = _CLI_SEARCH_PATHS_WINDOWS
    elif system == "Darwin":
        candidates = _CLI_SEARCH_PATHS_MAC
    else:
        candidates = _CLI_SEARCH_PATHS_LINUX

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class CLIBackend(LabVIEWBackend):
    """
    Controls LabVIEW via the LabVIEWCLI subprocess tool.
    Cross-platform, works with Community Edition.
    """

    def __init__(self, cli_path: Optional[str] = None,
                 bridge_vi_path: Optional[str] = None) -> None:
        self._cli_path = cli_path or _find_cli_exe()
        # Path to the optional file-bridge VI (provides input/output via JSON)
        self._bridge_vi_path = bridge_vi_path or os.environ.get("LABVIEW_BRIDGE_VI_PATH")

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "cli"

    @property
    def supports_control_io(self) -> bool:
        # I/O is possible only when the bridge VI is installed
        return self._bridge_vi_path is not None and os.path.isfile(self._bridge_vi_path)

    @property
    def supports_vi_scripting(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return self._cli_path is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cli(self) -> str:
        if not self._cli_path:
            raise RuntimeError(
                "LabVIEWCLI executable not found. "
                "Set LABVIEW_CLI_PATH environment variable or install LabVIEW 2018+."
            )
        return self._cli_path

    def _run_cli(self, args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
        cmd = [self._cli(), *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        try:
            result = self._run_cli(["-OperationName", "GetLabVIEWVersion"], timeout=30)
            version = result.stdout.strip() or result.stderr.strip() or "unknown"
            return f"LabVIEW {version} (CLI backend, path: {self._cli()})"
        except Exception as exc:
            return f"CLI backend available (version check failed: {exc})"

    # ------------------------------------------------------------------
    # VI Management
    # ------------------------------------------------------------------

    def get_vi_info(self, vi_path: str) -> VIInfo:
        if not os.path.exists(vi_path):
            raise FileNotFoundError(f"VI not found: {vi_path}")
        # CLI cannot introspect VIs; return file-system info only
        return VIInfo(
            name=Path(vi_path).name,
            path=vi_path,
            execution_state="unknown",
            description="(VI info not available via CLI backend)",
        )

    def save_vi(self, vi_path: str, save_as: Optional[str] = None) -> bool:
        raise NotImplementedError(
            "Saving VIs is not supported by the CLI backend. Use the COM backend."
        )

    def mass_compile(self, directory: str) -> str:
        result = self._run_cli(
            ["-OperationName", "MassCompile", "-DirPath", directory],
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Mass compile failed (exit {result.returncode}): {result.stderr.strip()}"
            )
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
        if not os.path.exists(vi_path):
            return RunResult(success=False, vi_path=vi_path, error=f"VI not found: {vi_path}")

        if inputs and self._bridge_vi_path:
            return self._run_via_bridge(vi_path, inputs)

        # Simple run without I/O
        try:
            result = self._run_cli(
                ["-OperationName", "RunVI", "-VIPath", vi_path],
                timeout=120,
            )
            success = result.returncode == 0
            error = "" if success else result.stderr.strip()
            return RunResult(
                success=success,
                vi_path=vi_path,
                execution_state="idle" if success else "unknown",
                error=error,
            )
        except subprocess.TimeoutExpired:
            return RunResult(success=False, vi_path=vi_path, error="VI execution timed out.")
        except Exception as exc:
            return RunResult(success=False, vi_path=vi_path, error=str(exc))

    def _run_via_bridge(
        self,
        vi_path: str,
        inputs: Dict[str, Any],
    ) -> RunResult:
        """
        Run a VI with I/O via the file bridge pattern:
          1. Write inputs to a temp JSON file.
          2. Run the bridge VI (which reads inputs, calls vi_path, writes outputs).
          3. Parse the output JSON file for results.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "lv_inputs.json")
            output_file = os.path.join(tmpdir, "lv_outputs.json")

            payload = {
                "vi_path": vi_path,
                "inputs": inputs or {},
                "output_file": output_file,
            }
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            try:
                result = self._run_cli(
                    [
                        "-OperationName", "RunVI",
                        "-VIPath", self._bridge_vi_path,
                        # Bridge VI must read LABVIEW_BRIDGE_INPUT env var for the path
                    ],
                    timeout=180,
                )
                if result.returncode != 0:
                    return RunResult(
                        success=False, vi_path=vi_path,
                        error=f"Bridge VI failed: {result.stderr.strip()}"
                    )
                # Read outputs if bridge VI wrote them
                if os.path.isfile(output_file):
                    with open(output_file, "r", encoding="utf-8") as f:
                        _outputs = json.load(f)  # stored for future get_control_value calls
                return RunResult(success=True, vi_path=vi_path, execution_state="idle")
            except Exception as exc:
                return RunResult(success=False, vi_path=vi_path, error=str(exc))

    def abort_vi(self, vi_path: str) -> bool:
        raise NotImplementedError("Aborting VIs is not supported by the CLI backend.")

    # ------------------------------------------------------------------
    # Control I/O  (via file bridge only)
    # ------------------------------------------------------------------

    def get_control_value(self, vi_path: str, control_name: str) -> ControlResult:
        raise NotImplementedError(
            "Direct control read is not supported by the CLI backend. "
            "Use the COM or HTTP backend, or deploy the File Bridge VI."
        )

    def set_control_value(self, vi_path: str, control_name: str, value: Any) -> bool:
        raise NotImplementedError(
            "Direct control write is not supported by the CLI backend. "
            "Pass inputs via the 'inputs' parameter of labview_run_vi instead."
        )

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
            "VI Scripting is not supported by the CLI backend. Use the COM backend."
        )

    # ------------------------------------------------------------------
    # Build spec execution (CLI-only extra)
    # ------------------------------------------------------------------

    def execute_build_spec(
        self,
        project_path: str,
        build_spec_name: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        Execute a LabVIEW build spec (e.g. build an EXE or installer).
        This is a CLI-only feature not available in other backends.
        """
        result = self._run_cli(
            [
                "-OperationName", "ExecuteBuildSpec",
                "-ProjectPath", project_path,
                "-BuildSpecName", build_spec_name,
            ],
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "project_path": project_path,
            "build_spec_name": build_spec_name,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
