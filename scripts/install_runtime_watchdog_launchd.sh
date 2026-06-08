#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.runtime-watchdog"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/runtime-watchdog.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_runtime_watchdog.sh"
ENV_FILE="${ROOT_DIR}/.env"
START_INTERVAL_SECONDS="60"
START_SERVICE="yes"

usage() {
  cat <<'EOF'
Usage: install_runtime_watchdog_launchd.sh [options]

Install the macOS LaunchAgent for the local paper runtime watchdog.

Options:
  --env-file PATH       Local env file. Default: .env
  --start-interval N    Watchdog interval in seconds. Default: 60
  --no-start            Write the plist but do not bootstrap/kickstart it.
  -h, --help            Show this help.

The watchdog checks the fixed local backend/API URL and restarts the existing
Alpaca paper LaunchAgent when the heartbeat is stale or unavailable.
EOF
}

while (($#)); do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --start-interval)
      START_INTERVAL_SECONDS="$2"
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

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Required env file not found: ${ENV_FILE}" >&2
  exit 78
fi

if ! [[ "${START_INTERVAL_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "Start interval must be numeric: ${START_INTERVAL_SECONDS}" >&2
  exit 64
fi

if [[ "${START_SERVICE}" == "yes" ]]; then
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${APP_SUPPORT_DIR}" "${ROOT_DIR}/data/runtime/logs"
install -m 600 "${ENV_FILE}" "${LAUNCHD_ENV_FILE}"
{
  cat <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR}"
ENV_FILE="${LAUNCHD_ENV_FILE}"

set -a
. "\${ENV_FILE}"
set +a

OUTPUT_DIR="\${TRADING_APP_OUTPUT_DIR:-data/runtime}"
DASHBOARD_URL="\${TRADING_APP_WATCHDOG_DASHBOARD_URL:-http://127.0.0.1:8765/api/snapshot}"
LAUNCHD_LABEL="\${TRADING_APP_WATCHDOG_LAUNCHD_LABEL:-com.trading-app.alpaca-paper}"
MAX_HEARTBEAT_AGE_MINUTES="\${TRADING_APP_WATCHDOG_MAX_HEARTBEAT_AGE_MINUTES:-5}"
RESTART="\${TRADING_APP_WATCHDOG_RESTART:-yes}"

cmd=(
  "\${ROOT_DIR}/.venv/bin/python"
  "-m"
  "trading_app.runtime.watchdog"
  "--output-dir"
  "\${OUTPUT_DIR}"
  "--dashboard-url"
  "\${DASHBOARD_URL}"
  "--launchd-label"
  "\${LAUNCHD_LABEL}"
  "--max-heartbeat-age-minutes"
  "\${MAX_HEARTBEAT_AGE_MINUTES}"
)

if [[ "\${RESTART}" == "yes" ]]; then
  cmd+=("--restart")
fi

cd "\${ROOT_DIR}"
exec "\${cmd[@]}"
EOF
} > "${LAUNCHD_WRAPPER}"
chmod 700 "${LAUNCHD_WRAPPER}"

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
    <string>/bin/bash</string>
    <string>$(xml_escape "${LAUNCHD_WRAPPER}")</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>${START_INTERVAL_SECONDS}</integer>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${ROOT_DIR}/data/runtime/logs/runtime-watchdog.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT_DIR}/data/runtime/logs/runtime-watchdog.launchd.err.log</string>
</dict>
</plist>
EOF
} > "${PLIST_PATH}"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "${PLIST_PATH}" >/dev/null
fi

echo "Installed plist: ${PLIST_PATH}"
echo "Installed watchdog wrapper: ${LAUNCHD_WRAPPER}"
echo "Installed launchd env file: ${LAUNCHD_ENV_FILE}"

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
