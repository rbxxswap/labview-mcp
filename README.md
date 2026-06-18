# LabVIEW MCP Plugin

Lets Claude control LabVIEW automatically — run VIs, read/write controls, execute tests,
generate code, build executables, and read TDMS measurement data.

Works with **LabVIEW Community Edition** and all paid editions on **Windows, macOS, and Linux**.

---

## One-time setup (required)

Python 3.10+ must be installed. Then run **one** of the following depending on your OS and preferred backend:

### Windows (recommended: COM backend)
```bat
setup\install.bat
```
This installs all Python dependencies including pywin32 for COM.

Or manually:
```bash
pip install "mcp[cli]>=1.3.0" pydantic nptdms pywin32 httpx --break-system-packages
python -m pywin32_postinstall -install
```

### macOS / Linux (CLI backend)
```bash
pip install "mcp[cli]>=1.3.0" pydantic nptdms --break-system-packages
# LabVIEW 2018+ must be installed
```

After installing, **restart Claude Desktop**.

---

## How it works

Claude uses 16 MCP tools to control LabVIEW. The server picks the best available interface automatically:

| Backend | Platforms | What it needs |
|---|---|---|
| **COM** | Windows only | pywin32 + LabVIEW installed |
| **CLI** | Win/Mac/Linux | LabVIEW 2018+ `LabVIEWCLI` binary |
| **HTTP** | Any | LabVIEW Web Service configured in project |
| **File Bridge** | Any | `MCP_Bridge.vi` running in LabVIEW |

Override auto-selection: `LABVIEW_BACKEND=com|cli|http|file`

---

## Example prompts

```
Check LabVIEW connection status.

Which backend is active and what features does it support?

List all VIs in C:/Projects/MyProject.

Run C:/Projects/Acquire.vi with Sample Rate=1000 and Channels="Dev1/ai0:3".

Read the 'Temperature' indicator from SensorRead.vi.

Run all test VIs starting with 'Test_' in C:/Projects/Tests/ and give me the results.

Build the 'Release EXE' spec from C:/Projects/MyApp.lvproj.

Read the 'Voltage' channel from group 'DAQ' in C:/Data/run01.tdms.

Create a new VI at C:/Projects/PID_Controller.vi with controls Kp (1.0), Ki (0.1), Kd (0.01)
and an indicator 'Control Output'.
```

---

## File Bridge setup (optional, for control I/O without COM)

The File Bridge lets any backend read/write controls via JSON files shared with LabVIEW.

```bash
# Generate bridge VI or print implementation instructions:
python server/bridge_vi_generator.py --instructions-only

# On Windows with LabVIEW open (creates blank VI):
python server/bridge_vi_generator.py --output C:/Projects/MCP_Bridge.vi
```

Open `MCP_Bridge.vi` in LabVIEW and leave it running.

---

## LabVIEW Web Services setup (HTTP backend)

1. In LabVIEW: right-click project → **New → Web Service** — name it `MCPService`
2. Add your VIs to the web service
3. **Tools → Web Server → Configuration → Enable**
4. Right-click the web service → **Deploy**
5. Set `LABVIEW_BACKEND=http` (or let auto-detect find it)

---

## Environment variables

See `skills/labview/references/environment-variables.md` for the full list.
Key variables: `LABVIEW_BACKEND`, `LABVIEW_CLI_PATH`, `LABVIEW_HTTP_HOST`,
`LABVIEW_HTTP_PORT`, `LABVIEW_BRIDGE_DIR`.

---

## Community Edition

LabVIEW Community Edition fully supports this plugin:
- ✅ COM/ActiveX (Windows)
- ✅ LabVIEW CLI (LabVIEW 2020 CE)
- ✅ VI Scripting — enable via **Tools → Options → VI Server → VI Scripting**
- ✅ Web Services
- ✅ TDMS read

---

## Troubleshooting

See `skills/labview/references/troubleshooting.md`.
