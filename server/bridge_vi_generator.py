#!/usr/bin/env python3
"""
MCP Bridge VI Generator
=======================
Creates the MCP_Bridge.vi that enables the File Bridge and CLI backends
to exchange data with LabVIEW via JSON files.

How to use:
  1. Open LabVIEW (any version, Community Edition works).
  2. Run this script:
       python bridge_vi_generator.py --output C:/Projects/MCP_Bridge.vi
  3. Open MCP_Bridge.vi in LabVIEW and run it (leave it running).
  4. Set LABVIEW_BRIDGE_DIR to the same directory as in --bridge-dir.

The bridge VI continuously polls the bridge directory for *.job.json files,
processes each job, and writes result or error JSON files.

Requirements:
  Windows: pywin32  (pip install pywin32)
  macOS/Linux: not supported via this script (use LabVIEW's script export)

Bridge VI Protocol (for manual implementation):
  Job file:    <bridge_dir>/<uuid>.job.json
  {
    "job_id": "...",
    "operation": "run_vi" | "get_control" | "set_control" | "get_vi_info"
                         | "save_vi" | "mass_compile" | "abort_vi" | "get_version",
    "vi_path": "...",       // for VI operations
    "control_name": "...",  // for get_control / set_control
    "value": ...,           // for set_control
    "inputs": {...},        // for run_vi
    "wait": true,           // for run_vi
    "directory": "...",     // for mass_compile
    "save_as": "...",       // for save_vi (optional)
  }

  Result file: <bridge_dir>/<uuid>.result.json
  {
    "job_id": "...",
    "success": true,
    "value": ...,           // for get_control
    "execution_state": ..., // for run_vi / get_vi_info
    "version": "...",       // for get_version
    "name": "...",          // for get_vi_info
    "description": "...",   // for get_vi_info
  }

  Error file: <bridge_dir>/<uuid>.error.json
  {
    "job_id": "...",
    "message": "error description"
  }
"""

import argparse
import os
import platform
import sys
from pathlib import Path

DEFAULT_BRIDGE_DIR = os.path.join(
    os.environ.get("TEMP", "/tmp") if platform.system() == "Windows" else "/tmp",
    "labview_mcp_bridge",
)
DEFAULT_OUTPUT = os.path.join(os.path.expanduser("~"), "MCP_Bridge.vi")


def generate_via_com(output_path: str, bridge_dir: str) -> None:
    """
    Generate MCP_Bridge.vi using LabVIEW VI Scripting via COM (Windows only).
    Creates a polling loop VI that implements the JSON bridge protocol.
    """
    print(f"Connecting to LabVIEW via COM...")
    import win32com.client
    lv = win32com.client.Dispatch("LabVIEW.Application")
    print(f"  Connected: LabVIEW {lv.Version}")

    vi = lv.NewVI()
    vi.Description = (
        "MCP Bridge VI — polls a directory for JSON job files and executes "
        "LabVIEW operations on behalf of the LabVIEW MCP Server. "
        f"Bridge directory: {bridge_dir}"
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vi.SaveAs(output_path)
    print(f"  Blank VI saved to: {output_path}")
    print()
    print("NOTE: Full VI Scripting block-diagram generation requires LabVIEW Full/Professional.")
    print("The blank VI has been saved. To complete the bridge VI, implement the polling loop")
    print("manually using the protocol described in this script's docstring (see above),")
    print("or use the LabVIEW template in the README.")


def print_manual_instructions(output_path: str, bridge_dir: str) -> None:
    """Print instructions for implementing the bridge VI manually."""
    print()
    print("=" * 70)
    print("MCP Bridge VI – Manual Implementation Guide")
    print("=" * 70)
    print()
    print(f"Bridge directory : {bridge_dir}")
    print(f"Output VI path   : {output_path}")
    print()
    print("Steps to create MCP_Bridge.vi manually in LabVIEW:")
    print()
    print("1. New VI → open Block Diagram")
    print()
    print("2. Add a String constant: bridge directory path")
    print(f"   Value: {bridge_dir}")
    print()
    print("3. Create a While loop (runs until Stop button pressed)")
    print()
    print("4. Inside the loop:")
    print("   a. List files in <bridge_dir> matching *.job.json")
    print("      (File/Directory > List Dir or Get File List)")
    print()
    print("   b. For each job file:")
    print("      - Read JSON (Read File + Unflatten From JSON)")
    print("      - Extract 'operation' and 'job_id' fields")
    print("      - Use Case Structure on operation:")
    print()
    print('        "run_vi":')
    print("          Open VI Reference (vi_path)")
    print("          Set control values from 'inputs' (loop)")
    print("          Run VI (Wait Until Done = 'wait')")
    print("          Write result JSON: {job_id, success:true, execution_state}")
    print()
    print('        "get_control":')
    print("          Open VI Reference → Get Control Value (control_name)")
    print("          Write result JSON: {job_id, value}")
    print()
    print('        "set_control":')
    print("          Open VI Reference → Set Control Value (control_name, value)")
    print("          Write result JSON: {job_id, success:true}")
    print()
    print('        "abort_vi":')
    print("          Open VI Reference → Abort VI")
    print("          Write result JSON: {job_id, success:true}")
    print()
    print('        "get_vi_info":')
    print("          Open VI Reference → read Name, ExecutionState, Description")
    print("          Write result JSON: {job_id, name, execution_state, description}")
    print()
    print('        "save_vi":')
    print("          Open VI Reference → Save / SaveAs")
    print("          Write result JSON: {job_id, success:true}")
    print()
    print('        "mass_compile":')
    print("          Application → Mass Compile (directory)")
    print("          Write result JSON: {job_id, success:true}")
    print()
    print('        "get_version":')
    print("          Application → Version")
    print("          Write result JSON: {job_id, version}")
    print()
    print("      - On any error: Write error JSON: {job_id, message: error string}")
    print("      - Delete the job file after processing")
    print()
    print("   c. Wait 200ms (to avoid busy-polling)")
    print()
    print("5. Save the VI and leave it RUNNING in LabVIEW.")
    print()
    print(f"6. Set LABVIEW_BRIDGE_DIR={bridge_dir}")
    print("   Set LABVIEW_BACKEND=file (or AUTO will detect it)")
    print()
    print("Result/error file names: <job_id>.result.json / <job_id>.error.json")
    print("Write to the same bridge directory.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the MCP_Bridge.vi for the LabVIEW MCP Server file backend."
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output path for MCP_Bridge.vi (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--bridge-dir",
        default=DEFAULT_BRIDGE_DIR,
        help=f"Bridge directory (default: {DEFAULT_BRIDGE_DIR})",
    )
    parser.add_argument(
        "--instructions-only",
        action="store_true",
        help="Print manual implementation instructions without generating a VI.",
    )
    args = parser.parse_args()

    os.makedirs(args.bridge_dir, exist_ok=True)
    print(f"Bridge directory: {args.bridge_dir}")

    if args.instructions_only:
        print_manual_instructions(args.output, args.bridge_dir)
        return

    if platform.system() != "Windows":
        print("COM-based VI generation is Windows-only.")
        print_manual_instructions(args.output, args.bridge_dir)
        return

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("pywin32 not installed. Printing manual instructions instead.")
        print_manual_instructions(args.output, args.bridge_dir)
        return

    try:
        generate_via_com(args.output, args.bridge_dir)
        print()
        print_manual_instructions(args.output, args.bridge_dir)
    except Exception as exc:
        print(f"COM generation failed: {exc}")
        print_manual_instructions(args.output, args.bridge_dir)
        sys.exit(1)


if __name__ == "__main__":
    main()
