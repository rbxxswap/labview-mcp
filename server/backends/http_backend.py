"""
LabVIEW HTTP Web Service Backend  (Windows / macOS / Linux)
============================================================
Calls LabVIEW VIs that have been published as HTTP Web Services.

Setup in LabVIEW:
  1. Create a "Web Service" item in your LabVIEW project.
  2. Add VIs to the service. Each VI becomes an HTTP endpoint.
  3. Enable the web server: Tools → Web Server → Configuration → Enable
  4. Deploy the project.
  5. Default base URL: http://localhost:8080/LabVIEW/WebService/<ServiceName>/<VIName>

Request format (JSON):
  POST /LabVIEW/WebService/<Service>/<VI>
  Content-Type: application/json
  {
    "controls": {"Control Name": value, ...},
    "outputs":  ["Indicator Name", ...]
  }

Response format:
  {
    "outputs": {"Indicator Name": value, ...}
  }

Compatible with:
  LabVIEW 2009+, Community Edition
  Windows, macOS, Linux (any machine that can reach the LabVIEW host)

Configuration via environment variables:
  LABVIEW_HTTP_HOST    = localhost    (default)
  LABVIEW_HTTP_PORT    = 8080         (default)
  LABVIEW_HTTP_SERVICE = MCPService   (default service name, override per tool)
  LABVIEW_HTTP_TOKEN   = <token>      (optional Bearer token)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ControlResult, LabVIEWBackend, RunResult, TestResult, VIInfo

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_HOST    = "localhost"
_DEFAULT_PORT    = 8080
_DEFAULT_SERVICE = "MCPService"
_TIMEOUT         = 60.0   # seconds


class HTTPBackend(LabVIEWBackend):
    """
    Communicates with LabVIEW via its built-in HTTP Web Service interface.
    Cross-platform; requires httpx (async-capable HTTP client).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        service: Optional[str] = None,
        token: Optional[str] = None,
    ) -> None:
        self._host    = host    or os.environ.get("LABVIEW_HTTP_HOST",    _DEFAULT_HOST)
        self._port    = port    or int(os.environ.get("LABVIEW_HTTP_PORT", _DEFAULT_PORT))
        self._service = service or os.environ.get("LABVIEW_HTTP_SERVICE", _DEFAULT_SERVICE)
        self._token   = token   or os.environ.get("LABVIEW_HTTP_TOKEN",   "")

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "http"

    @property
    def supports_control_io(self) -> bool:
        return True

    @property
    def supports_vi_scripting(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        try:
            import httpx  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_url(self, service: Optional[str] = None) -> str:
        svc = service or self._service
        return f"http://{self._host}:{self._port}/LabVIEW/WebService/{svc}"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _vi_name(self, vi_path: str) -> str:
        """Extract the VI stem name for use in the URL."""
        return Path(vi_path).stem

    def _post(
        self,
        vi_name: str,
        controls: Optional[Dict[str, Any]] = None,
        outputs: Optional[List[str]] = None,
        service: Optional[str] = None,
    ) -> Dict[str, Any]:
        import httpx
        url = f"{self._base_url(service)}/{vi_name}"
        payload: Dict[str, Any] = {}
        if controls:
            payload["controls"] = controls
        if outputs:
            payload["outputs"] = outputs

        resp = httpx.post(url, json=payload, headers=self._headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> Dict[str, Any]:
        import httpx
        url = f"http://{self._host}:{self._port}{path}"
        resp = httpx.get(url, headers=self._headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        try:
            data = self._get("/LabVIEW/WebService")
            version = data.get("version", "unknown")
            return f"LabVIEW {version} (HTTP backend, {self._base_url()})"
        except Exception as exc:
            return (
                f"HTTP backend configured ({self._base_url()}) – "
                f"version probe failed: {exc}"
            )

    # ------------------------------------------------------------------
    # VI Management
    # ------------------------------------------------------------------

    def get_vi_info(self, vi_path: str) -> VIInfo:
        # Not directly available via Web Service; return what we know
        vi_name = self._vi_name(vi_path)
        return VIInfo(
            name=vi_name,
            path=vi_path,
            execution_state="unknown",
            description=f"(Remote VI at {self._base_url()}/{vi_name})",
        )

    def save_vi(self, vi_path: str, save_as: Optional[str] = None) -> bool:
        raise NotImplementedError(
            "Saving VIs remotely is not supported by the HTTP backend."
        )

    def mass_compile(self, directory: str) -> str:
        raise NotImplementedError(
            "Mass compile is not supported by the HTTP backend. Use the COM or CLI backend."
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_vi(
        self,
        vi_path: str,
        inputs: Optional[Dict[str, Any]] = None,
        wait_until_done: bool = True,
    ) -> RunResult:
        vi_name = self._vi_name(vi_path)
        try:
            self._post(vi_name, controls=inputs)
            return RunResult(success=True, vi_path=vi_path, execution_state="idle")
        except Exception as exc:
            return RunResult(success=False, vi_path=vi_path, error=str(exc))

    def abort_vi(self, vi_path: str) -> bool:
        raise NotImplementedError(
            "Aborting VIs remotely is not supported by the HTTP backend."
        )

    # ------------------------------------------------------------------
    # Control I/O
    # ------------------------------------------------------------------

    def get_control_value(self, vi_path: str, control_name: str) -> ControlResult:
        vi_name = self._vi_name(vi_path)
        try:
            data = self._post(vi_name, outputs=[control_name])
            outputs = data.get("outputs", {})
            value = outputs.get(control_name)
            return ControlResult(vi_path=vi_path, control_name=control_name, value=value)
        except Exception as exc:
            return ControlResult(vi_path=vi_path, control_name=control_name, error=str(exc))

    def set_control_value(self, vi_path: str, control_name: str, value: Any) -> bool:
        vi_name = self._vi_name(vi_path)
        self._post(vi_name, controls={control_name: value})
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
            "VI Scripting is not supported by the HTTP backend. Use the COM backend."
        )

    # ------------------------------------------------------------------
    # Run VI and collect outputs in one call (HTTP-optimised)
    # ------------------------------------------------------------------

    def run_vi_with_outputs(
        self,
        vi_path: str,
        controls: Optional[Dict[str, Any]] = None,
        output_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a VI via HTTP and return specified indicator values in one request.
        More efficient than separate run + get_control_value calls.
        """
        vi_name = self._vi_name(vi_path)
        try:
            data = self._post(vi_name, controls=controls, outputs=output_names)
            return {
                "success": True,
                "vi_path": vi_path,
                "outputs": data.get("outputs", {}),
            }
        except Exception as exc:
            return {"success": False, "vi_path": vi_path, "error": str(exc)}
