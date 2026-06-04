#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.alpaca-paper"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/alpaca-paper.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_alpaca_paper_runtime.sh"
ENV_FILE="${ROOT_DIR}/.env"
OUTPUT_DIR="data/runtime"
DASHBOARD_HOST="127.0.0.1"
DASHBOARD_PORT="8765"
OPERATOR_DASHBOARD_URL="http://127.0.0.1:3003/"
FEED="IEX"
STARTING_CASH="100000"
MANAGED_CAPITAL=""
MAX_PAPER_SYMBOL_ALLOCATION=""
MAX_PAPER_SEMICONDUCTOR_ALLOCATION=""
INITIAL_PAPER_DEPLOYMENT_ALLOCATION=""
PAPER_EPOCH_STARTED_AT=""
ACTIVE_MODEL_KEY="monthly_sector_momentum:1.0.0"
SHADOW_CHALLENGER_MODEL_KEY=""
SHADOW_CHALLENGER_MODEL_KEYS=""
STRATEGY_SCHEDULE="daily_close"
SYMBOLS=""
START_SERVICE="yes"

usage() {
  cat <<'EOF'
Usage: install_alpaca_paper_launchd.sh [options]

Install the macOS LaunchAgent for the Alpaca paper runtime.

Options:
  --env-file PATH        Local env file. Default: .env
  --output-dir PATH      Runtime artifact directory. Default: data/runtime
  --dashboard-host HOST  Dashboard bind host. Default: 127.0.0.1
  --dashboard-port PORT  Fixed backend/API port. Default: 8765
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
  --no-start             Write the plist but do not bootstrap/kickstart it.
  -h, --help             Show this help.

The installer uses one canonical backend/API port. If the port is busy, stop the
old process first; the service will not silently switch to a different port.
EOF
}

while (($#)); do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
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
    --no-start)
      START_SERVICE="no"
      shift
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

if [[ "${ENV_FILE}" != /* ]]; then
  ENV_FILE="${ROOT_DIR}/${ENV_FILE}"
fi

if [[ "${OUTPUT_DIR}" == /* ]]; then
  RUNTIME_OUTPUT_DIR="${OUTPUT_DIR}"
else
  RUNTIME_OUTPUT_DIR="${ROOT_DIR}/${OUTPUT_DIR}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Required env file not found: ${ENV_FILE}" >&2
  exit 78
fi

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

if [[ "${START_SERVICE}" == "yes" ]]; then
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

if [[ "${START_SERVICE}" == "yes" ]] && command -v lsof >/dev/null 2>&1; then
  listeners="$(lsof -tiTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN || true)"
  if [[ -n "${listeners}" ]]; then
    echo "Dashboard port ${DASHBOARD_PORT} is already in use. Stop that process before installing launchd." >&2
    lsof -nP -iTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN >&2 || true
    exit 78
  fi
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${APP_SUPPORT_DIR}" "${RUNTIME_OUTPUT_DIR}/logs"
install -m 600 "${ENV_FILE}" "${LAUNCHD_ENV_FILE}"
{
  echo
  printf 'TRADING_APP_OPERATOR_DASHBOARD_URL=%q\n' "${OPERATOR_DASHBOARD_URL}"
} >> "${LAUNCHD_ENV_FILE}"

{
  cat <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR}"
ENV_FILE="${LAUNCHD_ENV_FILE}"
OUTPUT_DIR="${RUNTIME_OUTPUT_DIR}"
DASHBOARD_HOST="${DASHBOARD_HOST}"
DASHBOARD_PORT="${DASHBOARD_PORT}"
OPERATOR_DASHBOARD_URL="${OPERATOR_DASHBOARD_URL}"
FEED="${FEED}"
STARTING_CASH="${STARTING_CASH}"
MANAGED_CAPITAL="${MANAGED_CAPITAL}"
MAX_PAPER_SYMBOL_ALLOCATION="${MAX_PAPER_SYMBOL_ALLOCATION}"
MAX_PAPER_SEMICONDUCTOR_ALLOCATION="${MAX_PAPER_SEMICONDUCTOR_ALLOCATION}"
INITIAL_PAPER_DEPLOYMENT_ALLOCATION="${INITIAL_PAPER_DEPLOYMENT_ALLOCATION}"
PAPER_EPOCH_STARTED_AT="${PAPER_EPOCH_STARTED_AT}"
ACTIVE_MODEL_KEY="${ACTIVE_MODEL_KEY}"
SHADOW_CHALLENGER_MODEL_KEY="${SHADOW_CHALLENGER_MODEL_KEY}"
SHADOW_CHALLENGER_MODEL_KEYS="${SHADOW_CHALLENGER_MODEL_KEYS}"
STRATEGY_SCHEDULE="${STRATEGY_SCHEDULE}"
SYMBOLS="${SYMBOLS}"

set -a
. "\${ENV_FILE}"
set +a

FEED="\${TRADING_APP_FEED:-\${FEED}}"
STARTING_CASH="\${TRADING_APP_STARTING_CASH:-\${STARTING_CASH}}"
MANAGED_CAPITAL="\${TRADING_APP_MANAGED_CAPITAL:-\${MANAGED_CAPITAL}}"
MAX_PAPER_SYMBOL_ALLOCATION="\${TRADING_APP_MAX_PAPER_SYMBOL_ALLOCATION:-\${MAX_PAPER_SYMBOL_ALLOCATION}}"
MAX_PAPER_SEMICONDUCTOR_ALLOCATION="\${TRADING_APP_MAX_PAPER_SEMICONDUCTOR_ALLOCATION:-\${MAX_PAPER_SEMICONDUCTOR_ALLOCATION}}"
INITIAL_PAPER_DEPLOYMENT_ALLOCATION="\${TRADING_APP_INITIAL_PAPER_DEPLOYMENT_ALLOCATION:-\${INITIAL_PAPER_DEPLOYMENT_ALLOCATION}}"
PAPER_EPOCH_STARTED_AT="\${TRADING_APP_PAPER_EPOCH_STARTED_AT:-\${PAPER_EPOCH_STARTED_AT}}"
ACTIVE_MODEL_KEY="\${TRADING_APP_ACTIVE_MODEL_KEY:-\${ACTIVE_MODEL_KEY}}"
SHADOW_CHALLENGER_MODEL_KEY="\${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEY:-\${SHADOW_CHALLENGER_MODEL_KEY}}"
SHADOW_CHALLENGER_MODEL_KEYS="\${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEYS:-\${SHADOW_CHALLENGER_MODEL_KEYS}}"
STRATEGY_SCHEDULE="\${TRADING_APP_STRATEGY_SCHEDULE:-\${STRATEGY_SCHEDULE}}"
SYMBOLS="\${TRADING_APP_SYMBOLS:-\${SYMBOLS}}"

if command -v lsof >/dev/null 2>&1; then
  listeners="\$(lsof -tiTCP:"\${DASHBOARD_PORT}" -sTCP:LISTEN || true)"
  if [[ -n "\${listeners}" ]]; then
    echo "Dashboard port \${DASHBOARD_PORT} is already in use; refusing to choose a different port." >&2
    lsof -nP -iTCP:"\${DASHBOARD_PORT}" -sTCP:LISTEN >&2 || true
    exit 78
  fi
fi

cmd=(
  "\${ROOT_DIR}/.venv/bin/python"
  "-u"
  "-m"
  "trading_app.runtime.run_alpaca_paper"
  "--output-dir"
  "\${OUTPUT_DIR}"
  "--dashboard-host"
  "\${DASHBOARD_HOST}"
  "--dashboard-port"
  "\${DASHBOARD_PORT}"
  "--dashboard-redirect-url"
  "\${OPERATOR_DASHBOARD_URL}"
  "--feed"
  "\${FEED}"
  "--starting-cash"
  "\${STARTING_CASH}"
  "--managed-capital"
  "\${MANAGED_CAPITAL}"
  "--max-paper-symbol-allocation"
  "\${MAX_PAPER_SYMBOL_ALLOCATION}"
  "--max-paper-semiconductor-allocation"
  "\${MAX_PAPER_SEMICONDUCTOR_ALLOCATION}"
  "--initial-paper-deployment-allocation"
  "\${INITIAL_PAPER_DEPLOYMENT_ALLOCATION}"
  "--active-model-key"
  "\${ACTIVE_MODEL_KEY}"
  "--strategy-schedule"
  "\${STRATEGY_SCHEDULE}"
  "--monitor-only-dry-run-first"
)

if [[ -n "\${PAPER_EPOCH_STARTED_AT}" ]]; then
  cmd+=("--paper-epoch-started-at" "\${PAPER_EPOCH_STARTED_AT}")
fi

if [[ -n "\${SHADOW_CHALLENGER_MODEL_KEY}" ]]; then
  cmd+=("--shadow-challenger-model-key" "\${SHADOW_CHALLENGER_MODEL_KEY}")
fi

if [[ -n "\${SHADOW_CHALLENGER_MODEL_KEYS}" ]]; then
  cmd+=("--shadow-challenger-model-keys" "\${SHADOW_CHALLENGER_MODEL_KEYS}")
fi

if [[ -n "\${SYMBOLS}" ]]; then
  cmd+=("--symbols" "\${SYMBOLS}")
fi

cd /
echo "Starting Alpaca paper backend/API on http://\${DASHBOARD_HOST}:\${DASHBOARD_PORT}/"
echo "Redirecting browser dashboard routes to \${OPERATOR_DASHBOARD_URL}"
exec "\${cmd[@]}"
EOF
} > "${LAUNCHD_WRAPPER}"
chmod 700 "${LAUNCHD_WRAPPER}"

program_args=("${LAUNCHD_WRAPPER}")

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  printf '%s' "${value}"
}

{
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
EOF
  for arg in "${program_args[@]}"; do
    printf '    <string>%s</string>\n' "$(xml_escape "${arg}")"
  done
  cat <<EOF
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${RUNTIME_OUTPUT_DIR}/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${RUNTIME_OUTPUT_DIR}/logs/launchd.err.log</string>
</dict>
</plist>
EOF
} > "${PLIST_PATH}"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "${PLIST_PATH}" >/dev/null
fi

echo "Installed plist: ${PLIST_PATH}"
echo "Installed runtime wrapper: ${LAUNCHD_WRAPPER}"
echo "Installed launchd env file: ${LAUNCHD_ENV_FILE}"
echo "Python backend/API URL: http://${DASHBOARD_HOST}:${DASHBOARD_PORT}/"
echo "Operator dashboard URL: ${OPERATOR_DASHBOARD_URL}"

if [[ "${START_SERVICE}" == "yes" ]]; then
  (
    cd /
    launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
    launchctl kickstart -k "gui/$(id -u)/${LABEL}"
  )
  echo "LaunchAgent started: ${LABEL}"
else
  echo "LaunchAgent not started because --no-start was provided."
fi
