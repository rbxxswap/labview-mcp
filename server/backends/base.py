"""
Abstract base class for all LabVIEW backends.

Every backend must implement these methods. Tools in server.py call the
active backend exclusively through this interface, so backends are
interchangeable at runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VIInfo:
    name: str
    path: str
    execution_state: str          # "idle" | "running" | "synchronous_call" | "top_level_call"
    description: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    success: bool
    vi_path: str
    execution_state: str = "idle"
    error: str = ""


@dataclass
class ControlResult:
    vi_path: str
    control_name: str
    value: Any = None
    error: str = ""


@dataclass
class TestResult:
    test_name: str
    vi_path: str
    passed: Optional[bool]        # None = indeterminate (indicator not found)
    error_code: int = 0
    error_message: str = ""
    note: str = ""


class LabVIEWBackend(ABC):
    """
    Abstract interface for all LabVIEW communication backends.

    Implementations:
      COMBackend   – Windows COM/ActiveX (LabVIEW.Application)
      CLIBackend   – LabVIEW CLI subprocess (cross-platform)
      HTTPBackend  – LabVIEW Web Services REST API (cross-platform)
      FileBackend  – JSON file bridge (universal fallback)
    """

    # -----------------------------------------------------------------------
    # Meta
    # -----------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'com', 'cli', 'http', 'file'."""

    @property
    @abstractmethod
    def supports_control_io(self) -> bool:
        """True if this backend can get/set individual control values."""

    @property
    @abstractmethod
    def supports_vi_scripting(self) -> bool:
        """True if this backend can create VIs programmatically."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """True if the backend can be used in the current environment."""

    # -----------------------------------------------------------------------
    # Connection
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_version(self) -> str:
        """Return a human-readable version/status string."""

    # -----------------------------------------------------------------------
    # VI Management
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_vi_info(self, vi_path: str) -> VIInfo:
        """Return metadata for a VI."""

    @abstractmethod
    def save_vi(self, vi_path: str, save_as: Optional[str] = None) -> bool:
        """Save the VI in-place or to save_as path. Returns True on success."""

    @abstractmethod
    def mass_compile(self, directory: str) -> str:
        """Mass-compile all VIs in directory. Returns status message."""

    # -----------------------------------------------------------------------
    # VI Execution
    # -----------------------------------------------------------------------

    @abstractmethod
    def run_vi(
        self,
        vi_path: str,
        inputs: Optional[Dict[str, Any]] = None,
        wait_until_done: bool = True,
    ) -> RunResult:
        """Run a VI, optionally setting input controls first."""

    @abstractmethod
    def abort_vi(self, vi_path: str) -> bool:
        """Abort a running VI. Returns True on success."""

    # -----------------------------------------------------------------------
    # Control I/O  (only if supports_control_io)
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_control_value(self, vi_path: str, control_name: str) -> ControlResult:
        """Read a front-panel control or indicator value."""

    @abstractmethod
    def set_control_value(self, vi_path: str, control_name: str, value: Any) -> bool:
        """Write a front-panel control value. Returns True on success."""

    # -----------------------------------------------------------------------
    # VI Scripting  (only if supports_vi_scripting)
    # -----------------------------------------------------------------------

    @abstractmethod
    def generate_vi(
        self,
        vi_path: str,
        description: str = "",
        controls: Optional[List[Dict[str, Any]]] = None,
        indicators: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new VI with specified controls/indicators.
        Returns dict: {success, path, controls_added, indicators_added, note}
        """
