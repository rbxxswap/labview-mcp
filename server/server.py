#!/usr/bin/env python3
"""
LabVIEW MCP Server  –  Multi-Backend Edition
=============================================
Lets Claude (and any MCP client) control LabVIEW automatically via the
best available interface:

  Priority  Backend      Platforms            Notes
  ──────────────────────────────────────────────────────────────
  1         COM          Windows              Full features, auto-detected
  2         CLI          Win / Mac / Linux    Run + compile; I/O via File Bridge
  3         HTTP         Win / Mac / Linux    LabVIEW Web Services (REST)
  4         File Bridge  Universal            JSON polling; needs MCP_Bridge.vi

Override selection: set  LABVIEW_BACKEND = auto | com | cli | http | file

Transport: stdio (local, single-session)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backends import get_backend
from backends.base import LabVIEWBackend
from backends.cli_backend import CLIBackend

# ---------------------------------------------------------------------------
# Logging  –  stderr only (stdout is reserved for stdio MCP transport)
# ---------------------------------------------------------------------------
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[labview_mcp] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("labview_mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHARACTER_LIMIT   = 30_000
TDMS_SAMPLE_LIMIT = 2_000

# ---------------------------------------------------------------------------
# Backend singleton  –  resolved lazily on first tool call
# ---------------------------------------------------------------------------
_backend: Optional[LabVIEWBackend] = None


def _lv() -> LabVIEWBackend:
    global _backend
    if _backend is None:
        _backend = get_backend()
        log.info("Using backend: %s", _backend.name)
    return _backend


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class ResponseFormat(str):
    MARKDOWN = "markdown"
    JSON = "json"


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True,
                              extra="forbid")


def _j(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def _trunc(text: str) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    return text[:CHARACTER_LIMIT] + f"\n…[{len(text)-CHARACTER_LIMIT} chars omitted]"


def _err(exc: Exception) -> str:
    return f"Error ({type(exc).__name__}): {exc}"


# ===========================================================================
# TOOL: labview_get_status
# ===========================================================================

@mcp.tool(
    name="labview_get_status",
    annotations={"title": "LabVIEW Connection Status",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_get_status() -> str:
    """
    Check the LabVIEW connection and return the active backend and version.

    Returns:
        str: JSON {"connected": bool, "backend": str, "version": str,
                   "supports_control_io": bool, "supports_vi_scripting": bool}

    Examples:
        - Use when: verifying LabVIEW is reachable before running VIs
    """
    try:
        b = _lv()
        return _j({
            "connected": True,
            "backend": b.name,
            "version": b.get_version(),
            "supports_control_io": b.supports_control_io,
            "supports_vi_scripting": b.supports_vi_scripting,
        })
    except Exception as exc:
        return _j({"connected": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_list_vis
# ===========================================================================

class ListVIsInput(_Base):
    directory: str = Field(..., description="Absolute path to the directory to search.")
    recursive: bool = Field(default=False, description="Search sub-directories.")
    response_format: str = Field(default="markdown",
                                 description="'markdown' or 'json'.")

    @field_validator("directory")
    @classmethod
    def dir_exists(cls, v: str) -> str:
        if not os.path.isdir(v):
            raise ValueError(f"Directory does not exist: {v}")
        return v


@mcp.tool(
    name="labview_list_vis",
    annotations={"title": "List VI Files",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_list_vis(params: ListVIsInput) -> str:
    """
    List all .vi files found in a directory.

    Args:
        params (ListVIsInput):
            - directory (str): Absolute path to search.
            - recursive (bool): Include sub-directories. Default False.
            - response_format ('markdown'|'json'): Output format.

    Returns:
        str: JSON {"directory": str, "count": int, "vis": [str,...]}
             or Markdown table.

    Examples:
        - Use when: "Show me all VIs in C:/Projects"
    """
    try:
        pattern = "**/*.vi" if params.recursive else "*.vi"
        vis = sorted(str(p) for p in Path(params.directory).glob(pattern))
        payload = {"directory": params.directory, "count": len(vis), "vis": vis}

        if params.response_format == "json":
            return _trunc(_j(payload))

        lines = [f"# VIs in `{params.directory}`",
                 f"Found **{len(vis)}** VI(s)\n"]
        lines += [f"- {v}" for v in vis]
        return _trunc("\n".join(lines))
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_get_vi_info
# ===========================================================================

class VIPathInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the VI file.")


@mcp.tool(
    name="labview_get_vi_info",
    annotations={"title": "Get VI Metadata",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_get_vi_info(params: VIPathInput) -> str:
    """
    Retrieve metadata for a VI: name, description, execution state.

    Args:
        params (VIPathInput): vi_path (str)

    Returns:
        str: JSON {"name", "path", "execution_state", "description",
                   "backend"}

    Examples:
        - Use when: "What is the execution state of Acquire.vi?"
    """
    try:
        info = _lv().get_vi_info(params.vi_path)
        return _j({**info.__dict__, "backend": _lv().name})
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_run_vi
# ===========================================================================

class RunVIInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the VI.")
    inputs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Control values to set before running. "
                    "Example: {\"Sample Rate\": 1000, \"Channel\": \"Dev1/ai0\"}"
    )
    wait_until_done: bool = Field(
        default=True,
        description="Block until VI finishes (default True). "
                    "False starts VI in background."
    )


@mcp.tool(
    name="labview_run_vi",
    annotations={"title": "Run a VI",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True}
)
async def labview_run_vi(params: RunVIInput) -> str:
    """
    Run a LabVIEW VI, optionally setting input controls first.

    Available in all backends (COM, CLI, HTTP, File Bridge).

    Args:
        params (RunVIInput):
            - vi_path (str): Absolute path to the VI.
            - inputs (Optional[dict]): Control values to set before running.
            - wait_until_done (bool): Block until VI finishes. Default True.

    Returns:
        str: JSON {"success": bool, "vi_path": str, "execution_state": str,
                   "backend": str}

    Examples:
        - "Run C:/Projects/Acquire.vi with Sample Rate=1000"
        - "Execute GenerateSignal.vi with Frequency=50 and Amplitude=2"
    """
    try:
        result = _lv().run_vi(params.vi_path, params.inputs, params.wait_until_done)
        return _j({**result.__dict__, "backend": _lv().name})
    except Exception as exc:
        return _j({"success": False, "vi_path": params.vi_path, "error": str(exc)})


# ===========================================================================
# TOOL: labview_abort_vi
# ===========================================================================

@mcp.tool(
    name="labview_abort_vi",
    annotations={"title": "Abort a Running VI",
                 "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False}
)
async def labview_abort_vi(params: VIPathInput) -> str:
    """
    Abort a currently running VI. (COM and File Bridge backends only.)

    Args:
        params (VIPathInput): vi_path (str)

    Returns:
        str: JSON {"success": bool, "message": str}
    """
    try:
        _lv().abort_vi(params.vi_path)
        return _j({"success": True, "message": f"Aborted: {params.vi_path}"})
    except NotImplementedError as exc:
        return _j({"success": False, "error": str(exc)})
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_get_control_value
# ===========================================================================

class ControlAccessInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the VI.")
    control_name: str = Field(..., description="Exact front-panel control/indicator label.",
                              min_length=1)


@mcp.tool(
    name="labview_get_control_value",
    annotations={"title": "Read VI Control/Indicator",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_get_control_value(params: ControlAccessInput) -> str:
    """
    Read the current value of a front-panel control or indicator.
    (COM, HTTP, and File Bridge backends only.)

    Args:
        params (ControlAccessInput):
            - vi_path (str): Absolute path to the VI.
            - control_name (str): Exact control label (case-sensitive).

    Returns:
        str: JSON {"vi_path": str, "control_name": str, "value": any}

    Examples:
        - "Read 'Temperature' from SensorRead.vi after running it"
    """
    try:
        b = _lv()
        if not b.supports_control_io:
            return _j({
                "error": (
                    f"Backend '{b.name}' does not support direct control I/O. "
                    "Use the COM or HTTP backend, or deploy the File Bridge VI."
                )
            })
        result = b.get_control_value(params.vi_path, params.control_name)
        if result.error:
            return _j({"error": result.error})
        return _j({"vi_path": result.vi_path, "control_name": result.control_name,
                   "value": result.value})
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_set_control_value
# ===========================================================================

class SetControlInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the VI.")
    control_name: str = Field(..., description="Exact front-panel control label.", min_length=1)
    value: Any = Field(..., description="Value to write (number, string, bool, list…).")


@mcp.tool(
    name="labview_set_control_value",
    annotations={"title": "Write VI Control Value",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_set_control_value(params: SetControlInput) -> str:
    """
    Write a value to a front-panel control. (COM, HTTP, File Bridge.)

    Args:
        params (SetControlInput):
            - vi_path (str), control_name (str), value (any)

    Returns:
        str: JSON {"success": bool, "control_name": str, "value": any}
    """
    try:
        b = _lv()
        if not b.supports_control_io:
            return _j({"error": f"Backend '{b.name}' does not support control I/O."})
        b.set_control_value(params.vi_path, params.control_name, params.value)
        return _j({"success": True, "control_name": params.control_name,
                   "value": params.value})
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_run_test_vi
# ===========================================================================

class RunTestVIInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the test VI.")
    test_name: str = Field(default="", description="Label used in reports.")
    inputs: Optional[Dict[str, Any]] = Field(default=None)
    result_indicator: str = Field(default="Test Result",
                                  description="Boolean pass/fail indicator name.")
    error_indicator: str = Field(default="Error Out",
                                 description="LabVIEW error cluster indicator name.")


@mcp.tool(
    name="labview_run_test_vi",
    annotations={"title": "Run a Test VI",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True}
)
async def labview_run_test_vi(params: RunTestVIInput) -> str:
    """
    Run a single LabVIEW test VI and collect a standardised pass/fail result.

    Convention: VI has a Boolean indicator 'Test Result' (True = pass)
    and an error cluster 'Error Out'. Override names via parameters.

    Args:
        params (RunTestVIInput):
            - vi_path (str), test_name (str), inputs (dict),
              result_indicator (str), error_indicator (str)

    Returns:
        str: JSON {"test_name", "passed": bool|null, "error_code", "error_message"}

    Examples:
        - "Run VoltageTest.vi and tell me if it passed"
    """
    try:
        b = _lv()
        # COM backend has a native run_test_vi; others use generic run + get_control
        if hasattr(b, "run_test_vi"):
            result = b.run_test_vi(  # type: ignore[attr-defined]
                params.vi_path, params.test_name, params.inputs,
                params.result_indicator, params.error_indicator,
            )
            return _j(result.__dict__)

        # Generic path
        run = b.run_vi(params.vi_path, params.inputs, wait_until_done=True)
        if not run.success:
            return _j({"test_name": params.test_name or Path(params.vi_path).stem,
                       "passed": False, "error_message": run.error})

        passed: Optional[bool] = None
        error_code = 0
        error_msg = ""
        note = ""

        if b.supports_control_io:
            try:
                r = b.get_control_value(params.vi_path, params.result_indicator)
                passed = bool(r.value)
            except Exception:
                note = f"Indicator '{params.result_indicator}' not found."
            try:
                e = b.get_control_value(params.vi_path, params.error_indicator)
                if isinstance(e.value, dict):
                    error_code = int(e.value.get("code", 0))
                    error_msg  = str(e.value.get("message", ""))
            except Exception:
                pass
        else:
            note = (
                f"Backend '{b.name}' cannot read individual controls. "
                "Result is indeterminate unless the VI indicates failure via exit code."
            )

        return _j({
            "test_name": params.test_name or Path(params.vi_path).stem,
            "vi_path": params.vi_path,
            "passed": passed,
            "error_code": error_code,
            "error_message": error_msg,
            "note": note,
        })
    except Exception as exc:
        return _j({"test_name": params.test_name, "passed": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_run_test_suite
# ===========================================================================

class RunTestSuiteInput(_Base):
    directory: str = Field(..., description="Directory containing test VIs.")
    recursive: bool = Field(default=False)
    name_filter: str = Field(
        default="Test_",
        description="Only run VIs whose filename starts with this prefix. '' = all VIs."
    )
    result_indicator: str = Field(default="Test Result")
    error_indicator:  str = Field(default="Error Out")

    @field_validator("directory")
    @classmethod
    def dir_exists(cls, v: str) -> str:
        if not os.path.isdir(v):
            raise ValueError(f"Directory does not exist: {v}")
        return v


@mcp.tool(
    name="labview_run_test_suite",
    annotations={"title": "Run Full Test Suite",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True}
)
async def labview_run_test_suite(params: RunTestSuiteInput) -> str:
    """
    Discover and run all test VIs in a directory, returning a Markdown report.

    Args:
        params (RunTestSuiteInput):
            - directory (str), recursive (bool), name_filter (str),
              result_indicator (str), error_indicator (str)

    Returns:
        str: Markdown summary with pass/fail table and totals.

    Examples:
        - "Run the full test suite in C:/Projects/Tests/"
    """
    try:
        pattern = "**/*.vi" if params.recursive else "*.vi"
        vis = sorted(
            str(p) for p in Path(params.directory).glob(pattern)
            if not params.name_filter or p.stem.startswith(params.name_filter)
        )
        if not vis:
            return f"No VIs matching `{params.name_filter}*.vi` found in `{params.directory}`."

        b = _lv()
        results = []

        for vi_path in vis:
            entry: Dict[str, Any] = {
                "test_name": Path(vi_path).stem,
                "vi_path": vi_path,
                "passed": None,
                "error_message": "",
            }
            try:
                if hasattr(b, "run_test_vi"):
                    r = b.run_test_vi(  # type: ignore[attr-defined]
                        vi_path, entry["test_name"], None,
                        params.result_indicator, params.error_indicator,
                    )
                    entry["passed"]        = r.passed
                    entry["error_message"] = r.error_message
                else:
                    run = b.run_vi(vi_path, wait_until_done=True)
                    if not run.success:
                        entry["passed"]        = False
                        entry["error_message"] = run.error
                    elif b.supports_control_io:
                        try:
                            cr = b.get_control_value(vi_path, params.result_indicator)
                            entry["passed"] = bool(cr.value)
                        except Exception:
                            pass
                        try:
                            er = b.get_control_value(vi_path, params.error_indicator)
                            if isinstance(er.value, dict):
                                entry["error_message"] = str(er.value.get("message", ""))
                        except Exception:
                            pass
            except Exception as exc:
                entry["passed"]        = False
                entry["error_message"] = str(exc)

            results.append(entry)

        total   = len(results)
        passed  = sum(1 for r in results if r["passed"] is True)
        failed  = sum(1 for r in results if r["passed"] is False)
        indet   = total - passed - failed

        lines = [
            f"# Test Suite – `{params.directory}`",
            f"Backend: **{b.name}**  |  "
            f"Total: **{total}**  |  ✅ {passed}  ❌ {failed}  ⚠️ {indet}",
            "",
            "| Test | Result | Error |",
            "| ---- | ------ | ----- |",
        ]
        for r in results:
            icon = "✅" if r["passed"] else ("❌" if r["passed"] is False else "⚠️")
            lines.append(f"| {r['test_name']} | {icon} | {r['error_message'] or '—'} |")

        return _trunc("\n".join(lines))
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_create_vi_from_template
# ===========================================================================

class CreateVIInput(_Base):
    template_path: str = Field(..., description="Existing VI to use as template.")
    output_path:   str = Field(..., description="Destination path for the new VI.")
    description:   str = Field(default="", description="Description to embed in the VI.")


@mcp.tool(
    name="labview_create_vi_from_template",
    annotations={"title": "Create VI from Template",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_create_vi_from_template(params: CreateVIInput) -> str:
    """
    Copy a template VI to a new path. Available on all backends (file copy).
    Optionally embeds a description via LabVIEW COM if available.

    Args:
        params (CreateVIInput): template_path, output_path, description

    Returns:
        str: JSON {"success": bool, "path": str}
    """
    try:
        src = Path(params.template_path)
        dst = Path(params.output_path)
        if not src.exists():
            return _j({"success": False, "error": f"Template not found: {src}"})
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))

        if params.description:
            try:
                b = _lv()
                if hasattr(b, "_vi"):      # COM backend has direct VI reference
                    vi = b._vi(str(dst))   # type: ignore[attr-defined]
                    vi.Description = params.description
                    vi.Save()
            except Exception:
                pass  # best-effort

        return _j({"success": True, "path": str(dst)})
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_save_vi
# ===========================================================================

class SaveVIInput(_Base):
    vi_path: str = Field(..., description="Absolute path to the VI.")
    save_as: Optional[str] = Field(default=None,
                                   description="New path for SaveAs. Empty = save in-place.")


@mcp.tool(
    name="labview_save_vi",
    annotations={"title": "Save a VI",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_save_vi(params: SaveVIInput) -> str:
    """
    Save a VI in-place or to a new path. (COM and File Bridge backends.)

    Args:
        params (SaveVIInput): vi_path, save_as (optional)

    Returns:
        str: JSON {"success": bool, "saved_to": str}
    """
    try:
        _lv().save_vi(params.vi_path, params.save_as)
        return _j({"success": True, "saved_to": params.save_as or params.vi_path})
    except NotImplementedError as exc:
        return _j({"success": False, "error": str(exc)})
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_mass_compile
# ===========================================================================

class MassCompileInput(_Base):
    directory: str = Field(..., description="Directory whose VIs should be compiled.")

    @field_validator("directory")
    @classmethod
    def dir_exists(cls, v: str) -> str:
        if not os.path.isdir(v):
            raise ValueError(f"Directory does not exist: {v}")
        return v


@mcp.tool(
    name="labview_mass_compile",
    annotations={"title": "Mass Compile VIs",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_mass_compile(params: MassCompileInput) -> str:
    """
    Trigger LabVIEW's Mass Compile on a directory. (COM and CLI backends.)

    Args:
        params (MassCompileInput): directory

    Returns:
        str: JSON {"success": bool, "message": str}
    """
    try:
        msg = _lv().mass_compile(params.directory)
        return _j({"success": True, "message": msg})
    except NotImplementedError as exc:
        return _j({"success": False, "error": str(exc)})
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_build_spec  (CLI-only extra)
# ===========================================================================

class BuildSpecInput(_Base):
    project_path:    str = Field(..., description="Absolute path to the .lvproj file.")
    build_spec_name: str = Field(..., description="Name of the build specification in the project.")
    timeout:         int = Field(default=300, ge=30, le=1800,
                                 description="Max seconds to wait for build completion.")


@mcp.tool(
    name="labview_build_spec",
    annotations={"title": "Execute LabVIEW Build Spec",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def labview_build_spec(params: BuildSpecInput) -> str:
    """
    Execute a LabVIEW build specification (e.g. create an EXE or installer).
    Available on CLI backend only (LabVIEW 2018+).

    Args:
        params (BuildSpecInput):
            - project_path (str): .lvproj file path.
            - build_spec_name (str): Name of the build spec (e.g. "My Application").
            - timeout (int): Max wait time in seconds (default 300).

    Returns:
        str: JSON {"success": bool, "build_spec_name": str, "stdout": str}

    Examples:
        - "Build the 'Release EXE' spec in C:/Projects/MyApp.lvproj"
    """
    try:
        b = _lv()
        if not isinstance(b, CLIBackend):
            return _j({
                "success": False,
                "error": (
                    "Build specs can only be executed via the CLI backend. "
                    f"Current backend: {b.name}. Set LABVIEW_BACKEND=cli."
                )
            })
        result = b.execute_build_spec(
            params.project_path, params.build_spec_name, params.timeout
        )
        return _j(result)
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_generate_vi_script
# ===========================================================================

class GenerateVIInput(_Base):
    vi_path: str = Field(..., description="Output path for the new VI.")
    description: str = Field(default="")
    controls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Controls to add: [{\"name\": str, \"type\": \"numeric|boolean|string|array\", "
            "\"default\": any}]"
        )
    )
    indicators: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Indicators to add: [{\"name\": str, \"type\": str}]"
    )


@mcp.tool(
    name="labview_generate_vi_script",
    annotations={"title": "Generate VI via Scripting",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_generate_vi_script(params: GenerateVIInput) -> str:
    """
    Create a new VI programmatically using LabVIEW VI Scripting.
    Requires LabVIEW Full/Professional (COM backend).
    Community Edition: VI Scripting is supported but must be enabled in settings.

    Args:
        params (GenerateVIInput):
            - vi_path (str): Output path.
            - description (str): VI documentation.
            - controls (list): [{name, type, default}].
            - indicators (list): [{name, type}].

    Returns:
        str: JSON {"success": bool, "path": str, "controls_added": int,
                   "indicators_added": int, "scripting_available": bool}

    Examples:
        - "Create a VI with a 'Frequency' numeric control and 'Waveform' output"
    """
    try:
        b = _lv()
        if not b.supports_vi_scripting:
            return _j({
                "success": False,
                "error": (
                    f"Backend '{b.name}' does not support VI Scripting. "
                    "Use the COM backend (Windows)."
                )
            })
        result = b.generate_vi(
            params.vi_path, params.description, params.controls, params.indicators
        )
        return _j(result)
    except Exception as exc:
        return _j({"success": False, "error": str(exc)})


# ===========================================================================
# TOOL: labview_read_tdms
# ===========================================================================

class ReadTDMSInput(_Base):
    file_path: str = Field(..., description="Absolute path to the TDMS file.")
    channel_group: Optional[str] = Field(
        default=None,
        description="Group name to read. Omit to get file structure overview."
    )
    channel: Optional[str] = Field(
        default=None,
        description="Channel name within group. Omit to list all channels in group."
    )
    max_samples: int = Field(
        default=TDMS_SAMPLE_LIMIT,
        description=f"Max data samples to return (default {TDMS_SAMPLE_LIMIT}).",
        ge=1, le=100_000
    )
    response_format: str = Field(default="json", description="'json' or 'markdown'.")


@mcp.tool(
    name="labview_read_tdms",
    annotations={"title": "Read TDMS Data File",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_read_tdms(params: ReadTDMSInput) -> str:
    """
    Read data from a LabVIEW TDMS file. Works on any platform, no LabVIEW needed.

    Navigate in 3 steps:
      1. Omit group → file overview (all groups + channels)
      2. group only → channel list with previews
      3. group + channel → full data (up to max_samples)

    Args:
        params (ReadTDMSInput):
            - file_path (str), channel_group (str|None), channel (str|None),
              max_samples (int), response_format ('json'|'markdown')

    Returns:
        str: JSON or Markdown with TDMS structure / channel data.

    Examples:
        - "What channels does measurement.tdms contain?"
        - "Read 'Voltage' from group 'DAQ' in C:/Data/run01.tdms"
    """
    try:
        import nptdms  # type: ignore
    except ImportError:
        return "Error: nptdms not installed. Run: pip install nptdms"

    fp = str(params.file_path)
    if not os.path.exists(fp):
        return f"Error: TDMS file not found: {fp}"

    try:
        with nptdms.TdmsFile.open(fp) as tdms:
            # Level 0: file overview
            if params.channel_group is None:
                groups = {g.name: [c.name for c in g.channels()] for g in tdms.groups()}
                return _trunc(_j({
                    "file": fp,
                    "properties": {k: str(v) for k, v in tdms.properties.items()},
                    "groups": groups,
                }))

            group = tdms[params.channel_group]

            # Level 1: group overview
            if params.channel is None:
                ch_info: Dict[str, Any] = {}
                for ch in group.channels():
                    data = ch[:]
                    ch_info[ch.name] = {
                        "length": len(data),
                        "dtype": str(data.dtype) if hasattr(data, "dtype") else "?",
                        "preview": list(data[:10].tolist() if hasattr(data, "tolist")
                                        else data[:10]),
                    }
                return _trunc(_j({"group": params.channel_group, "channels": ch_info}))

            # Level 2: channel data
            ch   = group[params.channel]
            data = ch[:]
            raw  = (data[:params.max_samples].tolist()
                    if hasattr(data, "tolist")
                    else list(data[:params.max_samples]))

            payload = {
                "group": params.channel_group,
                "channel": params.channel,
                "total_samples": len(data),
                "returned_samples": len(raw),
                "truncated": len(data) > params.max_samples,
                "properties": {k: str(v) for k, v in ch.properties.items()},
                "data": raw,
            }

            if params.response_format == "markdown":
                stats = ""
                try:
                    nums  = [float(x) for x in raw]
                    stats = (f"\n\n**Min** {min(nums):.4g}  "
                             f"**Max** {max(nums):.4g}  "
                             f"**Mean** {sum(nums)/len(nums):.4g}")
                except Exception:
                    pass
                return _trunc(
                    f"## {params.channel_group} / {params.channel}\n"
                    f"Samples: {len(data)}  (showing {len(raw)}){stats}\n\n"
                    f"```\n{raw[:100]}\n```"
                )
            return _trunc(_j(payload))
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_backend_info
# ===========================================================================

@mcp.tool(
    name="labview_backend_info",
    annotations={"title": "LabVIEW Backend Capabilities",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_backend_info() -> str:
    """
    Return a summary of all backends, their availability, and feature support.
    Useful for diagnosing which LabVIEW interface is active and what it can do.

    Returns:
        str: Markdown table of all backends with availability and feature matrix.

    Examples:
        - "What LabVIEW backends are available on this machine?"
    """
    from backends.cli_backend  import CLIBackend   as _CLI
    from backends.com_backend  import COMBackend   as _COM
    from backends.file_backend import FileBackend  as _File
    from backends.http_backend import HTTPBackend  as _HTTP

    active = _lv() if _backend else None

    rows = []
    for cls in [_COM, _CLI, _HTTP, _File]:
        b = cls()
        is_active = active is not None and type(active) is cls
        rows.append({
            "backend":        b.name,
            "available":      b.is_available,
            "active":         is_active,
            "control_io":     b.supports_control_io,
            "vi_scripting":   b.supports_vi_scripting,
        })

    lines = [
        "# LabVIEW MCP Backend Status",
        "",
        "| Backend | Available | Active | Control I/O | VI Scripting |",
        "| ------- | --------- | ------ | ----------- | ------------ |",
    ]
    for r in rows:
        def icon(v: bool) -> str:
            return "✅" if v else "❌"
        lines.append(
            f"| **{r['backend']}** | {icon(r['available'])} | "
            f"{'◀ **active**' if r['active'] else '—'} | "
            f"{icon(r['control_io'])} | {icon(r['vi_scripting'])} |"
        )

    lines += [
        "",
        "**Override**: set `LABVIEW_BACKEND=com|cli|http|file|auto`",
    ]
    return "\n".join(lines)


# ===========================================================================
# TOOL: labview_probe_vi_catalog
# ===========================================================================

@mcp.tool(
    name="labview_probe_vi_catalog",
    annotations={"title": "Probe LabVIEW VI Catalog",
                 "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def labview_probe_vi_catalog() -> str:
    """
    Scan the built-in VI path catalog and report which library VIs exist on
    this LabVIEW installation. Use this before labview_build_block_diagram
    to verify which nodes are available and what paths they resolved to.
    Only available with the COM backend (Windows + VI Scripting).

    Returns:
        str: JSON mapping logical VI names to resolved paths (or "NOT FOUND").

    Examples:
        - "Which VISA VIs are available in my LabVIEW installation?"
    """
    b = _lv()
    if not hasattr(b, "probe_vi_catalog"):
        return _j({"error": "Only available with the COM backend."})
    try:
        return _j(b.probe_vi_catalog())
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# TOOL: labview_build_block_diagram
# ===========================================================================

class BDNodeInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(..., description=(
        "Local identifier used to reference this node in wire specs."
    ))
    path: str = Field(..., description=(
        "Logical catalog name (e.g. 'VISA Write'), a '<vilib>/...' path, "
        "or an absolute path to a VI. For structures use the class name."
    ))
    path_aliases: Optional[List[str]] = Field(
        default=None,
        description="Extra path variants to try if 'path' is not found."
    )
    is_structure: bool = Field(
        default=False,
        description="True for While Loop, For Loop, Case Structure, etc."
    )
    x: Optional[int] = Field(default=None, description="X position.")
    y: Optional[int] = Field(default=None, description="Y position.")
    width:  Optional[int] = Field(default=None, description="Width  (structures only).")
    height: Optional[int] = Field(default=None, description="Height (structures only).")


class BDWireInput(BaseModel):
    src: str = Field(..., description=(
        "'node_id.terminal_name'  OR  'ctrl:ControlName' / 'ind:IndicatorName'."
    ))
    dst: str = Field(..., description="Same format as src.")


class BuildBDInput(_Base):
    vi_path: str = Field(..., description=(
        "Absolute path to the VI whose block diagram should be modified. "
        "The VI must already exist (create it first with labview_generate_vi_script)."
    ))
    nodes: List[BDNodeInput] = Field(
        ..., description="Ordered list of nodes to place on the block diagram."
    )
    wires: Optional[List[BDWireInput]] = Field(
        default=None, description="Connections between node terminals."
    )
    script_only: bool = Field(
        default=False,
        description=(
            "If true, only return the Python builder script without live execution. "
            "Useful when VI Scripting is not yet enabled."
        )
    )


@mcp.tool(
    name="labview_build_block_diagram",
    annotations={"title": "Build LabVIEW Block Diagram",
                 "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def labview_build_block_diagram(params: BuildBDInput) -> str:
    """
    Place function/subVI nodes and wires on a VI's block diagram using
    LabVIEW VI Scripting via the COM backend.

    Path resolution is version-aware: logical names like 'VISA Write' are
    looked up in a built-in catalog with fallback paths for LabVIEW 2015-2024.
    Run labview_probe_vi_catalog first to see what resolves on this install.

    Always returns a standalone Python builder script ('script' key) that
    performs the same operations — run it manually if live COM execution fails.

    Requirements:
        COM backend (Windows), VI Scripting enabled:
        Tools -> Options -> VI Server -> VI Scripting

    Args:
        params (BuildBDInput):
            - vi_path: path to existing VI
            - nodes: list of {id, path, [x, y, width, height, is_structure]}
            - wires: list of {src, dst} using 'node_id.terminal' notation
            - script_only: skip live execution, only return Python script

    Returns:
        str: JSON with placed nodes, wire results, live_execution flag,
             and always a 'script' key with the standalone Python script.

    Examples:
        - "Add VISA Write and VISA Read nodes to C:/Projects/Comm.vi"
        - "Build the block diagram for my serial communication VI"
        - "Place a While Loop with VISA nodes for Consult protocol"
    """
    b = _lv()
    if not hasattr(b, "build_block_diagram"):
        return _j({
            "error": "labview_build_block_diagram requires the COM backend.",
            "hint": "Set LABVIEW_BACKEND=com and ensure pywin32 is installed."
        })
    try:
        nodes_raw = [n.model_dump(exclude_none=True) for n in params.nodes]
        wires_raw = [w.model_dump() for w in params.wires] if params.wires else []
        result = b.build_block_diagram(
            vi_path=params.vi_path,
            nodes=nodes_raw,
            wires=wires_raw,
            generate_script_only=params.script_only,
        )
        return _trunc(_j(result))
    except Exception as exc:
        return _err(exc)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    mcp.run()
