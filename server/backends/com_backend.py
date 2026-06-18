"""
COM/ActiveX Backend  (Windows only)
====================================
Uses the LabVIEW.Application COM server to control LabVIEW.
Full feature set: run/abort VIs, get/set controls, VI Scripting, mass compile,
and block diagram construction (labview 2013+).

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
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ControlResult, LabVIEWBackend, RunResult, TestResult, VIInfo


# ---------------------------------------------------------------------------
# Front-panel type map
# ---------------------------------------------------------------------------

_STATE_MAP = {0: "idle", 1: "running", 2: "synchronous_call", 3: "top_level_call"}

_TYPE_MAP = {
    "numeric": "Numeric Control",
    "boolean": "Boolean",
    "string":  "String Control",
    "array":   "Array",
}

# ---------------------------------------------------------------------------
# Version-aware VI path catalog
#
# Each logical name maps to an ordered list of candidate paths.
# <vilib> is a LabVIEW macro resolved at runtime to the vi.lib directory.
# Paths are tried in order; the first one that exists on disk is used.
#
# Paths that changed across LabVIEW versions are listed newest-first so that
# the most common current installation succeeds on the first try.
# ---------------------------------------------------------------------------

VI_CATALOG: Dict[str, List[str]] = {
    # ── VISA Serial ────────────────────────────────────────────────────────
    "VISA Configure Serial Port": [
        "<vilib>/instr/visa.llb/VISA Configure Serial Port (Instr).vi",
        "<vilib>/instr/visa.llb/VISA Configure Serial Port.vi",
    ],
    "VISA Write": [
        "<vilib>/instr/visa.llb/VISA Write.vi",
    ],
    "VISA Read": [
        "<vilib>/instr/visa.llb/VISA Read.vi",
    ],
    "VISA Read with Options": [
        "<vilib>/instr/visa.llb/VISA Read with Options.vi",
        "<vilib>/instr/visa.llb/VISA Read.vi",      # fallback
    ],
    "VISA Close": [
        "<vilib>/instr/visa.llb/VISA Close.vi",
    ],
    "VISA Open": [
        "<vilib>/instr/visa.llb/VISA Open.vi",
    ],
    "VISA Set Attribute": [
        "<vilib>/instr/visa.llb/VISA Set Attribute.vi",
    ],
    "VISA Clear": [
        "<vilib>/instr/visa.llb/VISA Clear.vi",
    ],
    # ── Timing ─────────────────────────────────────────────────────────────
    "Wait (ms)": [
        "<vilib>/Utility/timers.llb/Wait (ms).vi",
        "<vilib>/timing/Wait.vi",
    ],
    "Tick Count (ms)": [
        "<vilib>/Utility/timers.llb/Tick Count (ms).vi",
    ],
    "Wait Until Next ms Multiple": [
        "<vilib>/Utility/timers.llb/Wait Until Next ms Multiple.vi",
    ],
    # ── String / Array conversion ───────────────────────────────────────────
    "String To Byte Array": [
        "<vilib>/Utility/error.llb/String To Byte Array.vi",
        "<vilib>/Utility/string/String To Byte Array.vi",
    ],
    "Byte Array To String": [
        "<vilib>/Utility/error.llb/Byte Array To String.vi",
        "<vilib>/Utility/string/Byte Array To String.vi",
    ],
    "Bytes At Serial Port": [
        "<vilib>/instr/visa.llb/Bytes At Serial Port.vi",
    ],
    # ── Error handling ──────────────────────────────────────────────────────
    "Simple Error Handler": [
        "<vilib>/Utility/error.llb/Simple Error Handler.vi",
    ],
    "General Error Handler": [
        "<vilib>/Utility/error.llb/General Error Handler.vi",
    ],
    "Merge Errors": [
        "<vilib>/Utility/error.llb/Merge Errors.vi",
    ],
    # ── Dialog / User Interface ─────────────────────────────────────────────
    "One Button Dialog": [
        "<vilib>/Utility/SysHelp.llb/One Button Dialog.vi",
    ],
    # ── File I/O ────────────────────────────────────────────────────────────
    "Open/Create/Replace File": [
        "<vilib>/File/FileOpenDlg.vi",
    ],
    "Write To Text File": [
        "<vilib>/File/Write Text File.vi",
        "<vilib>/Utility/writefile.vi",
    ],
}

# ---------------------------------------------------------------------------
# Block diagram: structures and built-in primitives
#
# These are LabVIEW class names for GObjectInsert (not file paths).
# Names are stable across LabVIEW versions.
# ---------------------------------------------------------------------------

BD_STRUCTURE_CLASSES = {
    "While Loop",
    "For Loop",
    "Case Structure",
    "Sequence Structure",
    "Event Structure",
    "Timed Loop",
}

BD_FUNCTION_CLASSES = {
    "Add", "Subtract", "Multiply", "Divide",
    "Greater", "Less", "Equal", "Not Equal",
    "And", "Or", "Not",
    "Increment", "Decrement",
    "Bundle", "Unbundle",
    "Build Array", "Array Size", "Index Array",
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
    # Version-aware path resolution
    # ------------------------------------------------------------------

    def get_vilib_path(self) -> str:
        """
        Return the vi.lib directory for this LabVIEW installation.
        Uses ApplicationDirectory, which LabVIEW exposes via COM.
        """
        lv = self._lv()
        app_dir = str(lv.ApplicationDirectory).rstrip("\\/")
        vilib = os.path.join(app_dir, "vi.lib")
        if os.path.isdir(vilib):
            return vilib
        # Some NI installations use a separate vi.lib under ProgramData
        alt = os.path.join(
            os.environ.get("ProgramData", "C:\\ProgramData"),
            "National Instruments", "LabVIEW", "vi.lib",
        )
        if os.path.isdir(alt):
            return alt
        raise RuntimeError(
            f"vi.lib not found. Tried:\n  {vilib}\n  {alt}\n"
            "Set LABVIEW_VILIB to override."
        )

    def resolve_vi_path(self, path: str) -> str:
        """
        Resolve <vilib> macro and forward slashes to an absolute path.
        Raises FileNotFoundError if the file does not exist.
        """
        # Allow env override for <vilib>
        if "<vilib>" in path:
            vilib_root = os.environ.get("LABVIEW_VILIB") or self.get_vilib_path()
            path = path.replace("<vilib>", vilib_root).replace("/", os.sep)
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"VI not found: {path}")

    def find_vi(self, candidates: List[str]) -> str:
        """
        Try each path variant in order; return the first that exists.
        Raises FileNotFoundError with a diagnostic listing all tried paths.
        """
        tried = []
        for cand in candidates:
            try:
                return self.resolve_vi_path(cand)
            except FileNotFoundError as exc:
                tried.append(str(exc))
        raise FileNotFoundError(
            f"VI not found in any of {len(candidates)} locations:\n"
            + "\n".join(f"  • {t}" for t in tried)
        )

    def find_vi_by_name(self, logical_name: str) -> str:
        """
        Look up a logical VI name in the catalog and find the best match.
        Returns the resolved absolute path.
        """
        if logical_name not in VI_CATALOG:
            raise KeyError(
                f"'{logical_name}' is not in the VI catalog. "
                f"Available entries: {sorted(VI_CATALOG)}"
            )
        return self.find_vi(VI_CATALOG[logical_name])

    def probe_vi_catalog(self) -> Dict[str, Any]:
        """
        Scan the VI catalog and report which VIs exist on this installation.
        Useful for diagnostics before building block diagrams.
        """
        results: Dict[str, Any] = {}
        try:
            vilib = self.get_vilib_path()
        except RuntimeError as exc:
            return {"error": str(exc)}
        for name, candidates in VI_CATALOG.items():
            found = None
            for cand in candidates:
                try:
                    found = self.resolve_vi_path(cand)
                    break
                except FileNotFoundError:
                    continue
            results[name] = found or "NOT FOUND"
        results["_vilib"] = vilib
        results["_lv_version"] = self.get_version()
        return results

    # ------------------------------------------------------------------
    # Block diagram scripting helpers
    # ------------------------------------------------------------------

    def _get_bd(self, vi: Any) -> Any:
        """
        Safely retrieve the block diagram reference.
        Raises RuntimeError with actionable message if unavailable.
        """
        try:
            bd = vi.BlockDiagram
            if bd is not None:
                return bd
        except Exception:
            pass
        raise RuntimeError(
            "Block diagram access is not available.\n"
            "Requirements:\n"
            "  • LabVIEW 2013 or newer\n"
            "  • VI Scripting enabled: Tools → Options → VI Server → VI Scripting\n"
            "  • LabVIEW Full or Professional (Community Edition also works after enabling)"
        )

    def _insert_gobj(self, bd: Any, class_or_path: str, x: int, y: int,
                     width: int = 0, height: int = 0) -> Any:
        """
        Place an object on the block diagram.
        Tries multiple method names for cross-version compatibility.
        """
        methods_to_try = ["GObjectInsert", "setItem", "PlaceNode", "InsertObject"]
        last_exc: Exception = RuntimeError("No placement method found")
        for method_name in methods_to_try:
            method = getattr(bd, method_name, None)
            if method is None:
                continue
            try:
                if width and height:
                    return method(class_or_path, x, y, x + width, y + height)
                else:
                    return method(class_or_path, x, y)
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(
            f"Could not place '{class_or_path}' on block diagram "
            f"(tried: {methods_to_try}): {last_exc}"
        )

    def _wire_terminals(self, bd: Any, src_node: Any, src_term: str,
                        dst_node: Any, dst_term: str) -> None:
        """Wire two terminals together on the block diagram."""
        try:
            src_t = src_node.Terminals[src_term]
            dst_t = dst_node.Terminals[dst_term]
        except Exception as exc:
            raise RuntimeError(
                f"Terminal lookup failed ({src_term!r} → {dst_term!r}): {exc}\n"
                "Terminal names are case-sensitive and must match connector pane labels."
            ) from exc
        try:
            bd.Wire(src_t, dst_t)
        except Exception as exc:
            raise RuntimeError(
                f"Wiring failed ({src_term!r} → {dst_term!r}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Block diagram builder
    # ------------------------------------------------------------------

    def build_block_diagram(
        self,
        vi_path: str,
        nodes: List[Dict[str, Any]],
        wires: Optional[List[Dict[str, Any]]] = None,
        generate_script_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Place nodes and wires on an existing VI's block diagram.
        Always returns a standalone Python script in the 'script' key.
        """
        result: Dict[str, Any] = {
            "vi_path": vi_path,
            "nodes_requested": len(nodes),
            "wires_requested": len(wires or []),
            "placed": [],
            "failed": [],
            "wired": [],
            "wire_errors": [],
            "live_execution": False,
            "script": "",
        }

        # Resolve all paths first
        resolved: Dict[str, str] = {}
        for node in nodes:
            nid = node["id"]
            raw_path = node.get("path", "")
            aliases = node.get("path_aliases") or []

            if node.get("is_structure") or raw_path in BD_STRUCTURE_CLASSES:
                resolved[nid] = raw_path
                result["placed"].append({"id": nid, "resolved": raw_path, "type": "structure"})
                continue

            if raw_path in VI_CATALOG:
                all_candidates = VI_CATALOG[raw_path] + list(aliases)
            else:
                all_candidates = ([raw_path] + list(aliases)) if raw_path else list(aliases)

            if not all_candidates:
                result["failed"].append({"id": nid, "error": "no path provided"})
                continue

            try:
                rpath = self.find_vi(all_candidates)
                resolved[nid] = rpath
                result["placed"].append({"id": nid, "resolved": rpath, "type": "subvi"})
            except FileNotFoundError as exc:
                result["failed"].append({"id": nid, "error": str(exc)})

        result["script"] = self._generate_bd_script(vi_path, nodes, wires or [], resolved)

        if generate_script_only:
            return result

        if result["failed"]:
            result["live_execution"] = False
            result["note"] = (
                f"{len(result['failed'])} node(s) could not be resolved. "
                "Fix paths or run the generated script manually."
            )
            return result

        try:
            vi = self._vi(vi_path)
            bd = self._get_bd(vi)
        except Exception as exc:
            result["live_execution"] = False
            result["bd_error"] = str(exc)
            return result

        node_refs: Dict[str, Any] = {}
        auto_x, auto_y = 50, 50
        placed_ok = 0

        for node in nodes:
            nid = node["id"]
            if nid not in resolved:
                continue
            rpath = resolved[nid]
            x = node.get("x") or auto_x
            y = node.get("y") or auto_y
            w = node.get("width") or 0
            h = node.get("height") or 0
            auto_x += (w or 80) + 20
            if auto_x > 600:
                auto_x = 50
                auto_y += 80
            try:
                ref = self._insert_gobj(bd, rpath, x, y, w, h)
                node_refs[nid] = ref
                placed_ok += 1
            except Exception as exc:
                result["failed"].append({"id": nid, "error": f"placement: {exc}"})

        result["live_execution"] = placed_ok > 0

        for wire in (wires or []):
            src_str = wire["src"]
            dst_str = wire["dst"]
            try:
                src_ref, src_term = self._resolve_wire_ep(src_str, node_refs, vi)
                dst_ref, dst_term = self._resolve_wire_ep(dst_str, node_refs, vi)
                self._wire_terminals(bd, src_ref, src_term, dst_ref, dst_term)
                result["wired"].append(f"{src_str} → {dst_str}")
            except Exception as exc:
                result["wire_errors"].append({"wire": f"{src_str}→{dst_str}", "error": str(exc)})

        if placed_ok > 0:
            try:
                vi.Save()
            except Exception as exc:
                result["save_warning"] = str(exc)

        return result

    def _resolve_wire_ep(self, spec: str, node_refs: Dict[str, Any], vi: Any):
        if "." in spec and not spec.startswith(("ctrl:", "ind:")):
            node_id, term = spec.split(".", 1)
            if node_id not in node_refs:
                raise KeyError(f"Node '{node_id}' not placed.")
            return node_refs[node_id], term
        if spec.startswith(("ctrl:", "ind:")):
            label = spec.split(":", 1)[1]
            fp = vi.FPOpen()
            ctrl = fp.Controls[label]
            return ctrl, "Terminal"
        raise ValueError(f"Cannot parse wire endpoint '{spec}'.")

    def _generate_bd_script(
        self,
        vi_path: str,
        nodes: List[Dict[str, Any]],
        wires: List[Dict[str, Any]],
        resolved: Dict[str, str],
    ) -> str:
        lines = [
            '"""',
            "Auto-generated LabVIEW block diagram builder.",
            "Requirements: pywin32, LabVIEW open, VI Scripting enabled.",
            f"Target VI: {vi_path}",
            '"""',
            "import win32com.client",
            "lv = win32com.client.Dispatch('LabVIEW.Application')",
            f"vi = lv.GetVIReference(r{vi_path!r})",
            "bd = vi.BlockDiagram",
            "nodes = {}",
            "",
        ]
        auto_x = 50
        for node in nodes:
            nid = node["id"]
            rpath = resolved.get(nid, node.get("path", "???"))
            x = node.get("x") or auto_x
            y = node.get("y") or 50
            w = node.get("width") or 0
            h = node.get("height") or 0
            auto_x += (w or 80) + 20
            if node.get("is_structure") or rpath in BD_STRUCTURE_CLASSES:
                lines.append(
                    f"nodes[{nid!r}] = bd.GObjectInsert({rpath!r}, "
                    f"{x}, {y}, {x + max(w, 200)}, {y + max(h, 150)})"
                )
            else:
                lines.append(
                    f"nodes[{nid!r}] = bd.GObjectInsert(r{rpath!r}, {x}, {y})"
                )
            lines.append(f"print('placed: {nid}')")
        if wires:
            lines.append("")
            for wire in wires:
                s, d = wire["src"], wire["dst"]
                if "." in s:
                    sn, st = s.split(".", 1)
                    se = f"nodes[{sn!r}].Terminals[{st!r}]"
                else:
                    se = f"# endpoint: {s}"
                if "." in d:
                    dn, dt = d.split(".", 1)
                    de = f"nodes[{dn!r}].Terminals[{dt!r}]"
                else:
                    de = f"# endpoint: {d}"
                lines.append(f"bd.Wire({se}, {de})")
        lines += ["", "vi.Save()", "print('Done.')"]
        return "\n".join(lines)

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

    def run_vi(self, vi_path: str, inputs=None, wait_until_done: bool = True) -> RunResult:
        vi = self._vi(vi_path)
        if inputs:
            for ctrl, val in inputs.items():
                vi.SetControlValue(ctrl, val)
        vi.Run(wait_until_done)
        return RunResult(
            success=True, vi_path=vi_path,
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
    # VI Scripting – front panel generation
    # ------------------------------------------------------------------

    def generate_vi(self, vi_path: str, description: str = "",
                    controls=None, indicators=None) -> Dict[str, Any]:
        lv = self._lv()
        vi = lv.NewVI()
        if description:
            vi.Description = description
        ctrl_count = ind_count = 0
        scripting_ok = False
        fp_ref = None
        try:
            fp_ref = vi.FPOpen()
            scripting_ok = True
        except Exception:
            pass
        if fp_ref is not None:
            x, y = 10, 10
            for item in (controls or []):
                try:
                    fp_ref.PlaceNewObject(
                        f"Ring & Enum Controls:Numeric Controls:"
                        f"{_TYPE_MAP.get(str(item.get('type','numeric')).lower(),'Numeric Control')}",
                        x, y)
                    y += 50
                    ctrl_count += 1
                except Exception:
                    ctrl_count += 1
            x = 220
            for item in (indicators or []):
                try:
                    fp_ref.PlaceNewObject(
                        f"Ring & Enum Controls:Numeric Controls:"
                        f"{_TYPE_MAP.get(str(item.get('type','numeric')).lower(),'Numeric Control').replace('Control','Indicator')}",
                        x, y)
                    y += 50
                    ind_count += 1
                except Exception:
                    ind_count += 1
        Path(vi_path).parent.mkdir(parents=True, exist_ok=True)
        vi.SaveAs(vi_path)
        return {
            "success": True, "path": vi_path,
            "controls_added": ctrl_count, "indicators_added": ind_count,
            "scripting_available": scripting_ok,
            "note": "" if scripting_ok else (
                "VI Scripting unavailable; blank VI saved. "
                "Enable: Tools → Options → VI Server → VI Scripting."
            ),
        }

    # ------------------------------------------------------------------
    # Test helper
    # ------------------------------------------------------------------

    def run_test_vi(self, vi_path: str, test_name: str = "", inputs=None,
                    result_indicator: str = "Test Result",
                    error_indicator: str = "Error Out") -> TestResult:
        vi = self._vi(vi_path)
        if inputs:
            for ctrl, val in inputs.items():
                vi.SetControlValue(ctrl, val)
        vi.Run(True)
        result = TestResult(test_name=test_name or Path(vi_path).stem,
                            vi_path=vi_path, passed=None)
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
ing – front panel generation
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
