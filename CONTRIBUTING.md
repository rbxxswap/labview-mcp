# Contributing to labview-mcp

Thank you for your interest in improving this plugin!

## Ways to contribute

- **Report bugs** — open a [GitHub issue](../../issues) with your LabVIEW version, OS, and error message
- **Share your setup** — worked with a specific LabVIEW version or backend? Let us know in [Discussions](../../discussions)
- **Fix bugs / add features** — open a pull request (see below)
- **Improve documentation** — typos, clearer wording, missing steps are all welcome

## Development setup

```bash
git clone https://github.com/rbxxswap/labview-mcp
cd labview-mcp
pip install "mcp[cli]>=1.3.0" pydantic nptdms httpx --break-system-packages
# Windows: also run
pip install pywin32 --break-system-packages && python -m pywin32_postinstall -install
```

Run the server manually to test:
```bash
python server/server.py
```

Check syntax before committing:
```bash
python -m py_compile server/server.py server/bridge_vi_generator.py server/backends/*.py
```

## Project structure

```
server/
  server.py              # MCP server, all 16 tools
  bridge_vi_generator.py # File Bridge VI helper
  backends/
    base.py              # Abstract base class + dataclasses
    com_backend.py       # Windows COM / ActiveX
    cli_backend.py       # LabVIEW CLI (2018+)
    http_backend.py      # LabVIEW Web Services
    file_backend.py      # JSON file bridge
    __init__.py          # Backend factory / auto-detection
skills/labview/
  SKILL.md               # Skill definition (triggers, tool reference)
  references/            # Environment variables, troubleshooting
setup/
  install.bat            # Windows one-click installer
  install.sh             # macOS / Linux installer
```

## Adding a new backend

1. Create `server/backends/yourname_backend.py` — subclass `LabVIEWBackend` from `base.py`
2. Implement all abstract methods (raise `NotImplementedError` for unsupported ones with a helpful message)
3. Add it to the priority list in `backends/__init__.py`
4. Document required env vars in `skills/labview/references/environment-variables.md`
5. Add a row to the feature matrix in README

## Pull request checklist

- [ ] Syntax check passes (`python -m py_compile`)
- [ ] New env vars documented in `environment-variables.md`
- [ ] README updated if behaviour changes
- [ ] Tested with at least one LabVIEW version (state which one in the PR)

## Code style

- Python 3.10+, type hints on all function signatures
- Dataclasses for structured return values (see `base.py`)
- Raise `NotImplementedError` (not return None) for unsupported backend methods
- Keep each backend self-contained — no cross-backend imports
