# Environment Variables

Configure the LabVIEW MCP server via these environment variables.
Set them in your shell, in the MCP server config, or in a `.env` file.

## Backend Selection

| Variable | Default | Values | Description |
|---|---|---|---|
| `LABVIEW_BACKEND` | `auto` | `auto` `com` `cli` `http` `file` | Which backend to use. `auto` tries COM → CLI → HTTP → File in order. |

## CLI Backend

| Variable | Default | Description |
|---|---|---|
| `LABVIEW_CLI_PATH` | auto-detect | Full path to `LabVIEWCLI.exe` or `labviewcli` binary. Set when the auto-detection fails or you have multiple LabVIEW versions. |
| `LABVIEW_BRIDGE_VI_PATH` | _(empty)_ | Path to `MCP_Bridge.vi`. When set, the CLI backend uses the File Bridge for control I/O. |

Auto-detected CLI paths (Windows): `C:\Program Files\National Instruments\LabVIEW 20xx\LabVIEWCLI.exe` for years 2018–2024.

## HTTP Backend

| Variable | Default | Description |
|---|---|---|
| `LABVIEW_HTTP_HOST` | `localhost` | LabVIEW web server host. Change for remote LabVIEW instances. |
| `LABVIEW_HTTP_PORT` | `8080` | LabVIEW web server port. Configurable in LabVIEW: Tools → Web Server → Configuration. |
| `LABVIEW_HTTP_SERVICE` | `MCPService` | Web service name, as defined in the LabVIEW project. |
| `LABVIEW_HTTP_TOKEN` | _(empty)_ | Bearer token for HTTP auth, if the web server requires authentication. |

## File Bridge Backend

| Variable | Default | Description |
|---|---|---|
| `LABVIEW_BRIDGE_DIR` | `%TEMP%\labview_mcp_bridge` | Directory shared between MCP server and MCP_Bridge.vi for JSON job files. Must be accessible by both processes. |
| `LABVIEW_BRIDGE_TIMEOUT` | `60` | Seconds to wait for bridge VI to respond before raising `TimeoutError`. |

## Example: Force COM backend (Windows)
```
LABVIEW_BACKEND=com
```

## Example: HTTP backend with custom host/port
```
LABVIEW_BACKEND=http
LABVIEW_HTTP_HOST=192.168.1.100
LABVIEW_HTTP_PORT=8090
LABVIEW_HTTP_SERVICE=LabVIEWService
```

## Example: File Bridge with custom directory
```
LABVIEW_BACKEND=file
LABVIEW_BRIDGE_DIR=C:\Shared\mcp_bridge
LABVIEW_BRIDGE_TIMEOUT=120
```

## Setting variables in the MCP config

Add them to the `env` section in `.mcp.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "labview": {
      "command": "python",
      "args": ["...server.py"],
      "env": {
        "LABVIEW_BACKEND": "http",
        "LABVIEW_HTTP_HOST": "myserver.local",
        "LABVIEW_HTTP_PORT": "8080"
      }
    }
  }
}
```
