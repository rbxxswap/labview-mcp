# LabVIEW MCP Plugin for Claude

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![LabVIEW Community](https://img.shields.io/badge/LabVIEW-Community%20Edition-green.svg)](https://www.ni.com/en/shop/labview/select-edition/labview-community-edition.html)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

**Let Claude control LabVIEW automatically** — run VIs, read/write front-panel controls, execute test suites, generate VI code, build executables, and read TDMS measurement data.

> Works with **LabVIEW Community Edition** (free) and all paid editions.  
> Runs on **Windows, macOS, and Linux**.

---

## What can Claude do with this plugin?

Once installed, you can ask Claude things like:

```
Run C:/Projects/Acquire.vi with Sample Rate=1000 and Channels="Dev1/ai0:3"

Run all test VIs starting with "Test_" in my project and show me the results

Create a new PID Controller VI with Kp, Ki, Kd controls and a Control Output indicator

Build the "Release EXE" spec from C:/Projects/MyApp.lvproj

Read the Voltage channel from the DAQ group in C:/Data/run01.tdms

Check LabVIEW connection status and which backend is active
```

Claude picks the right tools automatically — you describe what you want in plain language.

---

## How it works

The plugin starts a local Python server that connects to LabVIEW through one of four interfaces:

| Backend | Platforms | Needs | Features |
|---------|-----------|-------|----------|
| **COM / ActiveX** | Windows | pywin32 + LabVIEW | Full — controls, scripting, abort |
| **CLI** | Win / Mac / Linux | LabVIEW 2018+ | Run VIs, mass compile, build specs |
| **HTTP Web Service** | Any | Web Service configured | Run VIs, full control I/O |
| **File Bridge** | Any | Bridge VI running in LabVIEW | Full control I/O, any version |

The server selects the best available backend automatically. You can override with `LABVIEW_BACKEND=com|cli|http|file`.

---

## Installation

### Step 1 — Install Python 3.10+

Download from [python.org](https://python.org/downloads/) if not already installed.  
**Windows:** check "Add Python to PATH" during installation.

### Step 2 — Install the plugin

Download `labview-mcp.plugin` from the [latest release](../../releases/latest) and open it in Claude Desktop.

Or install the plugin directly inside Claude Desktop:  
**Settings → Capabilities → Plugins → Install from file**

### Step 3 — Install Python dependencies

**Windows** — run the included script (double-click or from a terminal):
```bat
setup\install.bat
```

**macOS / Linux:**
```bash
pip3 install "mcp[cli]>=1.3.0" pydantic nptdms httpx --break-system-packages
```

**Windows (manual):**
```bash
pip install "mcp[cli]>=1.3.0" pydantic nptdms pywin32 httpx --break-system-packages
python -m pywin32_postinstall -install
```

### Step 4 — Restart Claude Desktop

The plugin starts the LabVIEW server automatically in the background on next launch.

---

## Available Tools (16)

### Status & Diagnostics
| Tool | Description |
|------|-------------|
| `labview_get_status` | Connection status, LabVIEW version, active backend |
| `labview_backend_info` | Feature matrix for all four backends |

### VI Discovery
| Tool | Description |
|------|-------------|
| `labview_list_vis` | List `.vi` files in a directory |
| `labview_get_vi_info` | Name, description, execution state of a VI |

### VI Execution
| Tool | Description |
|------|-------------|
| `labview_run_vi` | Run a VI with optional inputs, optional wait |
| `labview_abort_vi` | Stop a running VI |
| `labview_get_control_value` | Read a front-panel control or indicator |
| `labview_set_control_value` | Write a value to a front-panel control |

### Testing
| Tool | Description |
|------|-------------|
| `labview_run_test_vi` | Run a single test VI, collect pass/fail result |
| `labview_run_test_suite` | Run all test VIs in a directory matching a prefix |

### VI Management
| Tool | Description |
|------|-------------|
| `labview_create_vi_from_template` | Copy a template VI to a new path |
| `labview_save_vi` | Save or Save As |
| `labview_mass_compile` | Compile all VIs in a directory tree |
| `labview_build_spec` | Execute a build spec (EXE, installer) — CLI backend |
| `labview_generate_vi_script` | Create a VI with controls/indicators via VI Scripting — COM backend |

### Data
| Tool | Description |
|------|-------------|
| `labview_read_tdms` | Read TDMS files — no LabVIEW connection needed |

---

## Backend Setup Details

### COM backend (Windows — recommended)

No extra configuration needed beyond the Python dependencies above.  
LabVIEW must be installed and the same bitness as Python (both 64-bit recommended).

VI Scripting (for `labview_generate_vi_script`):  
Enable in LabVIEW: **Tools → Options → VI Server → VI Scripting**

### CLI backend (macOS / Linux / multi-version Windows)

LabVIEW 2018 or newer must be installed. `LabVIEWCLI` is auto-detected.  
Override with: `LABVIEW_CLI_PATH=/path/to/labviewcli`

### HTTP Web Service backend

1. In LabVIEW: right-click project → **New → Web Service** → name it `MCPService`
2. Add your VIs to the web service
3. **Tools → Web Server → Configuration → Enable**
4. Right-click the web service → **Deploy**

Set `LABVIEW_BACKEND=http` (or let auto-detection find it).

### File Bridge backend (any platform, any LabVIEW version)

The File Bridge lets LabVIEW and Claude exchange data through JSON files — no COM, no CLI, no network.

Generate setup instructions:
```bash
python server/bridge_vi_generator.py --instructions-only
```

On Windows with LabVIEW open (creates a blank bridge VI):
```bash
python server/bridge_vi_generator.py --output C:/Projects/MCP_Bridge.vi
```

Open `MCP_Bridge.vi` in LabVIEW, implement the polling loop (instructions printed above), and leave it running.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LABVIEW_BACKEND` | `auto` | `auto` \| `com` \| `cli` \| `http` \| `file` |
| `LABVIEW_CLI_PATH` | auto-detect | Path to `LabVIEWCLI` binary |
| `LABVIEW_HTTP_HOST` | `localhost` | LabVIEW web server host |
| `LABVIEW_HTTP_PORT` | `8080` | LabVIEW web server port |
| `LABVIEW_HTTP_SERVICE` | `MCPService` | Web service name |
| `LABVIEW_HTTP_TOKEN` | _(empty)_ | Bearer token for HTTP auth |
| `LABVIEW_BRIDGE_DIR` | `%TEMP%\labview_mcp_bridge` | File bridge directory |
| `LABVIEW_BRIDGE_TIMEOUT` | `60` | Bridge response timeout in seconds |

Set variables in the MCP config (`env` block in `.mcp.json`) or in your system environment.

---

## LabVIEW Community Edition

All features work with the free Community Edition:

- ✅ COM / ActiveX (Windows)  
- ✅ LabVIEW CLI (LabVIEW 2020 Community Edition)  
- ✅ VI Scripting — enable in Tools → Options → VI Server  
- ✅ Web Services  
- ✅ TDMS read  

---

## Troubleshooting

**`No LabVIEW backend is available`**  
Install at least one: `pywin32` (COM), LabVIEW 2018+ (CLI), `httpx` (HTTP), or start `MCP_Bridge.vi` (File).

**`Could not connect to LabVIEW via COM`**  
Run `python -m pywin32_postinstall -install`.  
Make sure Python and LabVIEW are both 64-bit.

**`LabVIEWCLI executable not found`**  
Set `LABVIEW_CLI_PATH` to the full path of the binary.

**Control names not found**  
Names are case-sensitive. Use `labview_get_vi_info` to list controls first.

**HTTP backend returns 404**  
Verify service name, that the VI is deployed, and the web server is running.

**File Bridge times out**  
Make sure `MCP_Bridge.vi` is running. Check `LABVIEW_BRIDGE_DIR` matches on both sides.

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

- **Bug reports:** open a GitHub issue
- **New backends or features:** open a pull request
- **Tested with a specific LabVIEW version?** Let us know in Discussions

---

## License

MIT — see [LICENSE](LICENSE).
