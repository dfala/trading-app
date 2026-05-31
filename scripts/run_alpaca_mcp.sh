#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ALPACA_MCP_ENV_FILE:-"$ROOT_DIR/.env"}"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export UV_CACHE_DIR="${UV_CACHE_DIR:-"$ROOT_DIR/.uv-cache"}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-"$ROOT_DIR/.uv-tools"}"

fail() {
  printf 'Alpaca MCP setup error: %s\n' "$1" >&2
  exit 1
}

if [ ! -f "$ENV_FILE" ]; then
  fail "missing env file at $ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

is_placeholder() {
  case "${1:-}" in
    "" | "..." | "replace-with-your-paper-api-key" | \
      "replace-with-your-paper-secret-key" | "replace-with-paper-api-key" | \
      "replace-with-paper-secret-key")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if is_placeholder "${ALPACA_API_KEY:-}"; then
  fail "ALPACA_API_KEY is missing or still a placeholder"
fi

if is_placeholder "${ALPACA_SECRET_KEY:-}"; then
  fail "ALPACA_SECRET_KEY is missing or still a placeholder"
fi

case "${ALPACA_LIVE_TRADING_ENABLED:-false}" in
  true | TRUE | True | 1 | yes | YES | on | ON)
    fail "ALPACA_LIVE_TRADING_ENABLED must stay false for MCP paper setup"
    ;;
esac

for endpoint_name in ALPACA_API_BASE_URL APCA_API_BASE_URL ALPACA_BASE_URL; do
  endpoint_value="${!endpoint_name:-}"
  case "$endpoint_value" in
    *api.alpaca.markets*)
      case "$endpoint_value" in
        *paper-api.alpaca.markets*) ;;
        *) fail "$endpoint_name points at a live Alpaca endpoint" ;;
      esac
      ;;
  esac
done

export ALPACA_PAPER_TRADE=true
export DEBUG="${DEBUG:-false}"
export ALPACA_TOOLSETS="${ALPACA_TOOLSETS:-account,assets,stock-data,news}"

case ",$ALPACA_TOOLSETS," in
  *",trading,"* | *",crypto-data,"* | *",options-data,"*)
    fail "ALPACA_TOOLSETS must not include trading, crypto-data, or options-data"
    ;;
esac

if ! command -v uvx >/dev/null 2>&1; then
  fail "uvx is not installed. Install uv first, then restart your MCP client."
fi

exec uvx alpaca-mcp-server "$@"
