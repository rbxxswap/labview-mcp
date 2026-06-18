# Troubleshooting

## "No LabVIEW backend is available"

The server cannot find any usable interface. Fix at least one:

| Backend | Fix |
|---|---|
| COM (Windows) | `pip install pywin32 --break-system-packages` then `python -m pywin32_postinstall -install` |
| CLI | Install LabVIEW 2018+ or set `LABVIEW_CLI_PATH` to the LabVIEWCLI binary |
| HTTP | `pip install httpx --break-system-packages` and configure a LabVIEW Web Service |
| File | Set `LABVIEW_BRIDGE_DIR` and start `MCP_Bridge.vi` in LabVIEW |

## "Could not connect to LabVIEW via COM"

- Run `python -m pywin32_postinstall -install` after installing pywin32
- Use 64-bit Python when LabVIEW is 64-bit (most LabVIEW 2017+ on Windows)
- Make sure LabVIEW is installed (not just NI Package Manager)
- If using Community Edition: it fully supports COM — same fix applies

## "LabVIEWCLI executable not found"

- Set `LABVIEW_CLI_PATH` to the full path of `LabVIEWCLI.exe` (Windows) or `labviewcli` (Mac/Linux)
- CLI is only available with LabVIEW 2018+
- Check `C:\Program Files\National Instruments\LabVIEW 2020\LabVIEWCLI.exe`

## Control names not found

- Control/indicator names are case-sensitive and must match the front-panel label exactly
- Run `labview_get_vi_info` first to see the VI's control list
- Strip leading/trailing spaces from control names

## HTTP backend returns 404

- Verify the service name matches exactly: `LABVIEW_HTTP_SERVICE` must equal the Web Service name in the project
- Check the VI is deployed: right-click the Web Service → Deploy
- Test manually: `curl http://localhost:8080/LabVIEW/WebService/<ServiceName>/<VIName>`
- Ensure the LabVIEW web server is running: Tools → Web Server → Start

## File Bridge times out

- Make sure `MCP_Bridge.vi` is running in LabVIEW (click Run, keep running)
- `LABVIEW_BRIDGE_DIR` must point to the same directory seen by both the MCP server and LabVIEW
- On Windows: use backslash or forward slash consistently — both work
- Increase timeout: `LABVIEW_BRIDGE_TIMEOUT=120`

## VI Scripting not available

- VI Scripting requires LabVIEW Full or Professional edition (Community Edition also supports it)
- Enable it: Tools → Options → VI Server → VI Scripting → check "Enable VI Scripting"
- Restart LabVIEW after enabling

## Python version mismatch

- Use Python 3.10 or newer
- Python must be the same bitness as LabVIEW (both 64-bit is recommended)
- If you have multiple Python versions: specify the full path in `.mcp.json` instead of just `python`

## Server does not appear in Claude

- Restart Claude Desktop after installing the plugin or editing config
- Check the plugin is installed: Settings → Capabilities → Plugins
- Check server logs: Claude Desktop → Help → Open Logs
