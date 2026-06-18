---
description: |
  LabVIEW automation — create, run, test, and manage VIs; read/write controls and indicators;
  build executables; generate VI scripting code; read TDMS data files.
  Trigger when the user mentions: LabVIEW, VI, .vi, TDMS, NI, National Instruments,
  "run my test", "create a VI", "read measurement data", "generate LabVIEW code",
  "build my application", "mass compile", "web service", "front panel", "block diagram".
---

# LabVIEW Automation Skill

Use the `labview` MCP tools (provided by the labview-mcp plugin) to control LabVIEW
programmatically. This skill covers all 16 available tools across four backends.

## Getting Started

Always begin with `labview_backend_info` to see which backends are available, or
`labview_get_status` for a quick connection check. This tells you which features
are usable in the current environment.

## Tool Reference

### Status & Diagnostics
- **`labview_get_status`** — Check connection, LabVIEW version, and active backend.
- **`labview_backend_info`** — Show feature matrix for all four backends (COM, CLI, HTTP, File).

### VI Discovery
- **`labview_list_vis`** — List all `.vi` files in a directory. Accepts `directory` and optional `recursive` flag.
- **`labview_get_vi_info`** — Get name, description, and execution state of a VI by path.

### VI Execution
- **`labview_run_vi`** — Run a VI. Pass `vi_path` and optional `inputs` dict (control names → values).
  For blocking execution pass `wait=true`. Use `timeout_seconds` to limit wait time.
- **`labview_abort_vi`** — Stop a running VI. Requires COM or File backend.
- **`labview_get_control_value`** — Read a front-panel control or indicator by name.
- **`labview_set_control_value`** — Write a value to a front-panel control.

### Testing
- **`labview_run_test_vi`** — Run a single test VI. Reads the Boolean "Test Result" indicator
  and the "Error Out" cluster. Returns `passed`, `message`, and `error_info`.
- **`labview_run_test_suite`** — Run all VIs matching a name prefix in a directory.
  Collects individual results and returns a pass/fail summary.

### VI Management
- **`labview_create_vi_from_template`** — Copy a template VI to a new path (filesystem-based,
  works without LabVIEW connection).
- **`labview_save_vi`** — Save a VI. Pass `save_as` to save to a new path (SaveAs).
- **`labview_mass_compile`** — Compile all VIs in a directory tree. Requires COM or CLI backend.
- **`labview_build_spec`** — Execute a build specification (EXE, installer, etc.) from a `.lvproj`.
  Requires CLI backend. Arguments: `project_path`, `build_spec_name`, `target` (optional).
- **`labview_generate_vi_script`** — Create a new VI with specified controls and indicators
  using LabVIEW VI Scripting. Requires COM backend with VI Scripting enabled.
  VI Scripting: Tools → Options → VI Server → VI Scripting (enable checkbox).

### Data
- **`labview_read_tdms`** — Read a TDMS file without needing LabVIEW.
  Modes: `structure` (overview), `channels` (list groups/channels), `data` (read samples).
  Accepts `group`, `channel`, `max_samples` parameters.

## Backend Priority & Feature Matrix

The server selects the best available backend automatically (COM → CLI → HTTP → File).

| Feature | COM | CLI | HTTP | File |
|---------|-----|-----|------|------|
| Run VI | ✅ | ✅ | ✅ | ✅ |
| Get/Set Control | ✅ | ⚠️* | ✅ | ✅ |
| VI Scripting | ✅ | ❌ | ❌ | ❌ |
| Abort VI | ✅ | ❌ | ❌ | ✅ |
| Mass Compile | ✅ | ✅ | ❌ | ✅ |
| Build Spec | ❌ | ✅ | ❌ | ❌ |
| TDMS Read | ✅ | ✅ | ✅ | ✅ |

*CLI+Control requires File Bridge VI running.

## Typical Workflows

### Run a VI with inputs
```
labview_run_vi(
  vi_path="C:/Projects/Acquire.vi",
  inputs={"Sample Rate": 1000, "Channels": "Dev1/ai0:3"},
  wait=True
)
```

### Run a test suite
```
labview_run_test_suite(
  directory="C:/Projects/Tests/",
  vi_name_prefix="Test_"
)
```

### Generate a new VI
```
labview_generate_vi_script(
  vi_path="C:/Projects/PID_Controller.vi",
  controls=[
    {"name": "Kp", "type": "numeric", "default": 1.0},
    {"name": "Ki", "type": "numeric", "default": 0.1}
  ],
  indicators=[
    {"name": "Control Output", "type": "numeric"}
  ]
)
```

### Read TDMS measurement data
```
labview_read_tdms(
  file_path="C:/Data/run01.tdms",
  mode="data",
  group="DAQ",
  channel="Voltage",
  max_samples=500
)
```

### Build an executable
```
labview_build_spec(
  project_path="C:/Projects/MyApp.lvproj",
  build_spec_name="Release EXE"
)
```

## Environment Variables

Configure backend and connection settings via environment variables.
See `references/environment-variables.md` for the full list.

## Troubleshooting

See `references/troubleshooting.md` for common error messages and fixes.
