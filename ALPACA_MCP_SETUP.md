# Alpaca MCP Setup

This project may use Alpaca MCP as an optional operator and research assistant.
It is not part of the always-on trading runtime and must not bypass the app's
risk engine, ledger, reconciliation, paper-only boundary, or audit trail.

## Boundary

- Paper only.
- U.S.-listed stocks and ETFs only.
- No MCP trading tools in this phase.
- No crypto tools.
- No options tools.
- No live endpoint overrides.
- Keep Alpaca credentials in the ignored local `.env` file or another local
  secret source, never in tracked config.

## Local Launcher

The local launcher is:

```bash
scripts/run_alpaca_mcp.sh
```

It loads `.env`, verifies the required Alpaca paper keys are present, forces
`ALPACA_PAPER_TRADE=true`, rejects live endpoint overrides, and restricts
`ALPACA_TOOLSETS` to:

```text
account,assets,stock-data,news
```

The launcher intentionally rejects `trading`, `crypto-data`, and `options-data`.

## VS Code MCP Config

The project includes a secret-safe VS Code MCP config at:

```text
.vscode/mcp.json
```

It points to the local launcher and does not contain credential values.

After installing `uv`, restart VS Code so it discovers the MCP server. The
launcher also adds the common `uv` install paths to `PATH`, so direct launcher
tests can work before a full terminal restart.

## uvx Requirement

The Alpaca MCP server is launched through `uvx alpaca-mcp-server`. If `uvx` is
missing, install `uv` first. If your MCP client still cannot find it, restart
the MCP client so it picks up the updated environment.

The launcher sets `UV_CACHE_DIR=.uv-cache` and `UV_TOOL_DIR=.uv-tools` so local
MCP runs do not need to write under user-level cache/tool directories. Both
paths are ignored by git.

## Codex App Note

This file sets up the repo-side launcher and VS Code MCP config. The current
Codex session cannot hot-load a new external MCP server from inside the
workspace. To use Alpaca MCP directly in Codex, add the same launcher command to
the Codex MCP configuration outside this repo and restart Codex.
