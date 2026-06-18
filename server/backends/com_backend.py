"""
COM/ActiveX Backend  (Windows only)
====================================
Uses the LabVIEW.Application COM server to control LabVIEW.
Full feature set: run/abort VIs, get/set controls, VI Scripting, mass compile.

Requirements:
  pip install pywin32
  python -m pywin32_postinstall -install

Compatible with:
  LabVIEW 2015+, Community Edition, Full, Professional
  Windows 10/11, 64-bit Python matching LabVIEW bitness
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ControlResult, LabVIEWBackend, RunResult, TestResult, VIInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATE_MAP = {0: "idle", 1: "running", 2: "synchronous_call", 3: "top_level_call"}

_TYPE_MAP = {
    "numeric": "Numeric Control",
    "boolean": "Boolean",
    "string":  "String Control",
    "array":   "Array",
}


class COMBackend(LabVIEWBackend):
    """Controls LabVIEW via the Windows COM/ActiveX interface."""

    def __init__(self) -> None:
        self._app: Any = None

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "com"

    @property
    def supports_control_io(self) -> bool:
        return True

    @property
    def supports_vi_scripting(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        try:
            import win32com.client  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # COM application singleton
    # ------------------------------------------------------------------

    def _lv(self) -> Any:
        if self._app is not None:
            return self._app
        try:
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "pywin32 not installed. Run: pip install pywin32  "
                "then: python -m pywin32_postinstall -install"
            ) from exc
        try:
            self._app = win32com.client.Dispatch("LabVIEW.Application")
        except Exception as exc:
            raise RuntimeError(
                f"Could not connect to LabVIEW via COM: {exc}. "
                "Make sure LabVIEW is installed (not just Runtime)."
            ) from exc
        return self._app

    def _vi(self, vi_path: str) -> Any:
        path = str(Path(vi_path).resolve())
        if not os.path.exists(path):
            raise FileNotFoundError(f"VI not found: {path}")
        return self._lv().GetVIReference(path)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        return f"LabVIEW {self._lv().Version} (COM backend)"

    # ------------------------------------------------------------------
    # VI Management
    # ------------------------------------------------------------------

    def get_vi_info(self, vi_path: str) -> VIInfo:
        vi = self._vi(vi_path)
        return VIInfo(
            name=vi.Name,
            path=vi_path,
            execution_state=_STATE_MAP.get(vi.ExecutionState, "unknown"),
            description=getattr(vi, "Description", ""),
        )

    def save_vi(self, vi_path: str, save_as: Optional[str] = None) -> bool:
        vi = self._vi(vi_path)
        if save_as:
            vi.SaveAs(save_as)
        else:
            vi.Save()
        return True

    def mass_compile(self, directory: str) -> str:
        self._lv().MassCompile(directory)
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
        vi = self._vi(vi_path)
        if inputs:
            for ctrl, val in inputs.items():
                vi.SetControlValue(ctrl, val)
        vi.Run(wait_until_done)
        return RunResult(
            success=True,
            vi_path=vi_path,
            execution_state=_STATE_MAP.get(vi.ExecutionState, "unknown"),
        )

    def abort_vi(self, vi_path: str) -> bool:
        self._vi(vi_path).Abort()
        return True

    # ------------------------------------------------------------------
    # Control I/O
    # ------------------------------------------------------------------

    def get_control_value(self, vi_path: str, control_name: str) -> ControlResult:
        vi = self._vi(vi_path)
        value = vi.GetControlValue(control_name)
        return ControlResult(vi_path=vi_path, control_name=control_name, value=value)

    def set_control_value(self, vi_path: str, control_name: str, value: Any) -> bool:
        self._vi(vi_path).SetControlValue(control_name, value)
        return True

    # ------------------------------------------------------------------
    # VI Scripting
    # ------------------------------------------------------------------

    def generate_vi(
        self,
        vi_path: str,
        description: str = "",
        controls: Optional[List[Dict[str, Any]]] = None,
        indicators: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        lv = self._lv()
        vi = lv.NewVI()
        if description:
            vi.Description = description

        ctrl_count = 0
        ind_count = 0
        scripting_ok = False
        fp_ref = None

        try:
            fp_ref = vi.FPOpen()
            scripting_ok = True
        except Exception:
            pass  # VI Scripting license not present – still save blank VI

        if fp_ref is not None:
            x, y = 10, 10
            for item in (controls or []):
                try:
                    fp_ref.PlaceNewObject(
                        f"Ring & Enum Controls:Numeric Controls:"
                        f"{_TYPE_MAP.get(str(item.get('type', 'numeric')).lower(), 'Numeric Control')}",
                        x, y,
                    )
                    y += 50
                    ctrl_count += 1
                except Exception:
                    ctrl_count += 1

            x = 220
            for item in (indicators or []):
                try:
                    fp_ref.PlaceNewObject(
                        f"Ring & Enum Controls:Numeric Controls:"
                        f"{_TYPE_MAP.get(str(item.get('type', 'numeric')).lower(), 'Numeric Control').replace('Control', 'Indicator')}",
                        x, y,
                    )
                    y += 50
                    ind_count += 1
                except Exception:
                    ind_count += 1

        Path(vi_path).parent.mkdir(parents=True, exist_ok=True)
        vi.SaveAs(vi_path)

        return {
            "success": True,
            "path": vi_path,
            "controls_added": ctrl_count,
            "indicators_added": ind_count,
            "scripting_available": scripting_ok,
            "note": "" if scripting_ok else (
                "VI Scripting front-panel access unavailable; blank VI saved. "
                "Enable via Tools → Options → VI Server → VI Scripting "
                "(requires LabVIEW Full/Professional)."
            ),
        }

    # ------------------------------------------------------------------
    # Test helper (used by server.py directly)
    # ------------------------------------------------------------------

    def run_test_vi(
        self,
        vi_path: str,
        test_name: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        result_indicator: str = "Test Result",
        error_indicator: str = "Error Out",
    ) -> TestResult:
        vi = self._vi(vi_path)
        if inputs:
            for ctrl, val in inputs.items():
                vi.SetControlValue(ctrl, val)
        vi.Run(True)

        result = TestResult(
            test_name=test_name or Path(vi_path).stem,
            vi_path=vi_path,
            passed=None,
        )

        try:
            result.passed = bool(vi.GetControlValue(result_indicator))
        except Exception:
            result.note = f"Indicator '{result_indicator}' not found."

        try:
            err = vi.GetControlValue(error_indicator)
            if isinstance(err, dict):
                result.error_code = int(err.get("code", 0))
                result.error_message = str(err.get("message", ""))
            elif hasattr(err, "code"):
                result.error_code = int(err.code)
                result.error_message = str(getattr(err, "source", ""))
        except Exception:
            pass

        return result
