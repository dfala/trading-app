from __future__ import annotations

import json
from pathlib import Path


def test_alpaca_mcp_launcher_is_paper_only_and_tool_restricted() -> None:
    script = Path("scripts/run_alpaca_mcp.sh")
    text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "ALPACA_PAPER_TRADE=true" in text
    assert "ALPACA_TOOLSETS" in text
    assert "account,assets,stock-data,news" in text
    assert "UV_CACHE_DIR" in text
    assert "UV_TOOL_DIR" in text
    assert "trading, crypto-data, or options-data" in text
    assert 'uvx alpaca-mcp-server "$@"' in text
    assert "ALPACA_LIVE_TRADING_ENABLED must stay false" in text
    assert "live Alpaca endpoint" in text


def test_vscode_mcp_config_uses_launcher_without_secrets() -> None:
    config_path = Path(".vscode/mcp.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    server = payload["mcp"]["servers"]["alpaca-paper-research"]
    rendered = json.dumps(payload)

    assert server["type"] == "stdio"
    assert server["command"].endswith("scripts/run_alpaca_mcp.sh")
    assert "ALPACA_API_KEY" not in rendered
    assert "ALPACA_SECRET_KEY" not in rendered


def test_alpaca_mcp_setup_doc_preserves_runtime_boundary() -> None:
    text = Path("ALPACA_MCP_SETUP.md").read_text(encoding="utf-8")

    assert "not part of the always-on trading runtime" in text
    assert "No MCP trading tools" in text
    assert "No crypto tools" in text
    assert "No options tools" in text
    assert "UV_CACHE_DIR=.uv-cache" in text
    assert "UV_TOOL_DIR=.uv-tools" in text
    assert ".vscode/mcp.json" in text
