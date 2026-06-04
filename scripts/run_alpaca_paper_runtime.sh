#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

usage() {
  cat <<'EOF'
Usage: run_alpaca_paper_runtime.sh [options]

Start the Alpaca paper runtime with a fixed local backend/API port.

Options:
  --env-file PATH        Local env file to source before startup. Default: .env
  --output-dir PATH      Runtime artifact directory. Default: data/runtime
  --dashboard-host HOST  Dashboard bind host. Default: 127.0.0.1
  --dashboard-port PORT  Backend/API port. Default: 8765
  --operator-dashboard-url URL
                         Next.js operator dashboard URL. Default: http://127.0.0.1:3003/
  --feed FEED            Market data feed. Default: IEX
  --starting-cash CASH   Paper epoch starting cash. Default: 100000
  --managed-capital CASH
                         Optional capital slice the model is allowed to size.
  --max-paper-symbol-allocation FRACTION
                         Optional max per-symbol allocation. Use 1 for full sleeve.
  --max-paper-semiconductor-allocation FRACTION
                         Optional max semiconductor-theme allocation.
  --initial-paper-deployment-allocation FRACTION
                         Optional first-order deployment cap. Use none to disable.
  --paper-epoch-started-at RFC3339
                         Ignore broker orders submitted before this timestamp.
  --active-model-key KEY  Paper model key. Default: monthly_sector_momentum:1.0.0
  --shadow-challenger-model-key KEY
                         Optional shadow-only challenger model key.
  --shadow-challenger-model-keys CSV
                         Optional comma-separated shadow-only challenger model keys.
  --strategy-schedule SCHEDULE
                         Paper schedule: daily_close or market_open. Default: daily_close
  --symbols CSV          Optional comma-separated symbol override.
  -h, --help             Show this help.

The script refuses to start if the backend/API port is already occupied. The
LaunchAgent should fail loudly rather than silently moving to a different port.
EOF
}

for ((index = 1; index <= $#; index++)); do
  if [[ "${!index}" == "--env-file" ]]; then
    next=$((index + 1))
    if ((next > $#)); then
      echo "--env-file requires a value" >&2
      exit 64
    fi
    ENV_FILE="${!next}"
  fi
done

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

if [[ "${ENV_FILE}" != /* ]]; then
  ENV_FILE="${ROOT_DIR}/${ENV_FILE}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Required env file not found: ${ENV_FILE}" >&2
  exit 78
fi

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

OUTPUT_DIR="${TRADING_APP_OUTPUT_DIR:-data/runtime}"
DASHBOARD_HOST="${TRADING_APP_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${TRADING_APP_DASHBOARD_PORT:-8765}"
OPERATOR_DASHBOARD_URL="${TRADING_APP_OPERATOR_DASHBOARD_URL:-http://127.0.0.1:3003/}"
FEED="${TRADING_APP_FEED:-IEX}"
STARTING_CASH="${TRADING_APP_STARTING_CASH:-100000}"
MANAGED_CAPITAL="${TRADING_APP_MANAGED_CAPITAL:-}"
MAX_PAPER_SYMBOL_ALLOCATION="${TRADING_APP_MAX_PAPER_SYMBOL_ALLOCATION:-}"
MAX_PAPER_SEMICONDUCTOR_ALLOCATION="${TRADING_APP_MAX_PAPER_SEMICONDUCTOR_ALLOCATION:-}"
INITIAL_PAPER_DEPLOYMENT_ALLOCATION="${TRADING_APP_INITIAL_PAPER_DEPLOYMENT_ALLOCATION:-}"
PAPER_EPOCH_STARTED_AT="${TRADING_APP_PAPER_EPOCH_STARTED_AT:-}"
ACTIVE_MODEL_KEY="${TRADING_APP_ACTIVE_MODEL_KEY:-monthly_sector_momentum:1.0.0}"
SHADOW_CHALLENGER_MODEL_KEY="${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEY:-}"
SHADOW_CHALLENGER_MODEL_KEYS="${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEYS:-}"
STRATEGY_SCHEDULE="${TRADING_APP_STRATEGY_SCHEDULE:-daily_close}"
SYMBOLS="${TRADING_APP_SYMBOLS:-}"

while (($#)); do
  case "$1" in
    --env-file)
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --dashboard-host)
      DASHBOARD_HOST="$2"
      shift 2
      ;;
    --dashboard-port)
      DASHBOARD_PORT="$2"
      shift 2
      ;;
    --operator-dashboard-url)
      OPERATOR_DASHBOARD_URL="$2"
      shift 2
      ;;
    --feed)
      FEED="$2"
      shift 2
      ;;
    --starting-cash)
      STARTING_CASH="$2"
      shift 2
      ;;
    --managed-capital)
      MANAGED_CAPITAL="$2"
      shift 2
      ;;
    --max-paper-symbol-allocation)
      MAX_PAPER_SYMBOL_ALLOCATION="$2"
      shift 2
      ;;
    --max-paper-semiconductor-allocation)
      MAX_PAPER_SEMICONDUCTOR_ALLOCATION="$2"
      shift 2
      ;;
    --initial-paper-deployment-allocation)
      INITIAL_PAPER_DEPLOYMENT_ALLOCATION="$2"
      shift 2
      ;;
    --paper-epoch-started-at)
      PAPER_EPOCH_STARTED_AT="$2"
      shift 2
      ;;
    --active-model-key)
      ACTIVE_MODEL_KEY="$2"
      shift 2
      ;;
    --shadow-challenger-model-key)
      SHADOW_CHALLENGER_MODEL_KEY="$2"
      shift 2
      ;;
    --shadow-challenger-model-keys)
      SHADOW_CHALLENGER_MODEL_KEYS="$2"
      shift 2
      ;;
    --strategy-schedule)
      STRATEGY_SCHEDULE="$2"
      shift 2
      ;;
    --symbols)
      SYMBOLS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ "${DASHBOARD_HOST}" != "127.0.0.1" && "${DASHBOARD_HOST}" != "localhost" && "${DASHBOARD_HOST}" != "::1" ]]; then
  echo "Refusing non-local dashboard host: ${DASHBOARD_HOST}" >&2
  exit 78
fi

if ! [[ "${DASHBOARD_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Dashboard port must be numeric: ${DASHBOARD_PORT}" >&2
  exit 64
fi

case "${OPERATOR_DASHBOARD_URL}" in
  ""|http://127.0.0.1|http://127.0.0.1:*|http://localhost|http://localhost:*|http://[::1]|http://[::1]:*) ;;
  *)
    echo "Refusing non-local operator dashboard URL: ${OPERATOR_DASHBOARD_URL}" >&2
    exit 78
    ;;
esac

if command -v lsof >/dev/null 2>&1; then
  listeners="$(lsof -tiTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN || true)"
  if [[ -n "${listeners}" ]]; then
    echo "Dashboard port ${DASHBOARD_PORT} is already in use; refusing to choose a different port." >&2
    lsof -nP -iTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN >&2 || true
    exit 78
  fi
fi

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Project virtualenv Python not found: ${PYTHON_BIN}" >&2
  echo "Run: uv sync --dev" >&2
  exit 78
fi

mkdir -p "${ROOT_DIR}/${OUTPUT_DIR}/logs"
cd "${ROOT_DIR}"

cmd=(
  "${PYTHON_BIN}"
  "-u"
  "-m"
  "trading_app.runtime.run_alpaca_paper"
  "--output-dir"
  "${OUTPUT_DIR}"
  "--dashboard-host"
  "${DASHBOARD_HOST}"
  "--dashboard-port"
  "${DASHBOARD_PORT}"
  "--dashboard-redirect-url"
  "${OPERATOR_DASHBOARD_URL}"
  "--feed"
  "${FEED}"
  "--starting-cash"
  "${STARTING_CASH}"
  "--managed-capital"
  "${MANAGED_CAPITAL}"
  "--max-paper-symbol-allocation"
  "${MAX_PAPER_SYMBOL_ALLOCATION}"
  "--max-paper-semiconductor-allocation"
  "${MAX_PAPER_SEMICONDUCTOR_ALLOCATION}"
  "--initial-paper-deployment-allocation"
  "${INITIAL_PAPER_DEPLOYMENT_ALLOCATION}"
  "--active-model-key"
  "${ACTIVE_MODEL_KEY}"
  "--strategy-schedule"
  "${STRATEGY_SCHEDULE}"
  "--monitor-only-dry-run-first"
)

if [[ -n "${PAPER_EPOCH_STARTED_AT}" ]]; then
  cmd+=("--paper-epoch-started-at" "${PAPER_EPOCH_STARTED_AT}")
fi

if [[ -n "${SHADOW_CHALLENGER_MODEL_KEY}" ]]; then
  cmd+=("--shadow-challenger-model-key" "${SHADOW_CHALLENGER_MODEL_KEY}")
fi

if [[ -n "${SHADOW_CHALLENGER_MODEL_KEYS}" ]]; then
  cmd+=("--shadow-challenger-model-keys" "${SHADOW_CHALLENGER_MODEL_KEYS}")
fi

if [[ -n "${SYMBOLS}" ]]; then
  cmd+=("--symbols" "${SYMBOLS}")
fi

echo "Starting Alpaca paper backend/API on http://${DASHBOARD_HOST}:${DASHBOARD_PORT}/"
echo "Redirecting browser dashboard routes to ${OPERATOR_DASHBOARD_URL}"
exec "${cmd[@]}"
