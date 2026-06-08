#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.autonomous-learning"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/autonomous-learning.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_autonomous_learning_service.sh"
ENV_FILE="${ROOT_DIR}/.env"
OUTPUT_DIR="data/research/replay"
STATUS_DIR="data/runtime/learning"
BAR_ROOT="data/market_data/bars"
FEED="SIP"
POLL_SECONDS="60"
HISTORICAL_INTERVAL_HOURS="0"
HISTORICAL_COOLDOWN_MINUTES="1"
MAX_STRATEGIES_HISTORICAL="36"
MAX_STRATEGIES_FRESH="24"
NO_DYNAMIC_HISTORICAL_BACKLOG="no"
DYNAMIC_HISTORICAL_BACKLOG_SIZE="5000"
LEADER_TUNING_PROFILE_COUNT="6"
TUNING_MODE="no"
START_SERVICE="yes"

usage() {
  cat <<'EOF'
Usage: install_autonomous_learning_launchd.sh [options]

Install the macOS LaunchAgent for the autonomous learning service.

Options:
  --env-file PATH       Local env file. Default: .env
  --output-dir PATH     Research report directory. Default: data/research/replay
  --status-dir PATH     Runtime learning state directory. Default: data/runtime/learning
  --root PATH           Historical bar store. Default: data/market_data/bars
  --feed FEED           Market data feed. Default: SIP
  --poll-seconds N      Scheduler polling interval. Default: 60
  --historical-interval-hours N
                         Extra coarse historical delay. Default: 0
  --historical-cooldown-minutes N
                         Cooldown after a successful historical run. Default: 1
  --max-strategies-historical N
                         Historical catalog cap. Default: 36
  --max-strategies-fresh N
                         Fresh after-close catalog cap. Default: 24
  --no-dynamic-historical-backlog
                         Disable generated historical exploration/tuning profiles.
  --dynamic-historical-backlog-size N
                         Generated profile cap. Default: 5000
  --leader-tuning-profile-count N
                         Leader-focused tuning profile cap. Default: 6
  --tuning-mode          Allow explicit repeated historical sweeps for parameter
                         tuning after the novelty queue is exhausted.
  --no-start            Write the plist but do not bootstrap/kickstart it.
  -h, --help            Show this help.

The service is research-only. It can generate recommendations, but model
promotion remains manual and evidence-gated.
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
    --status-dir)
      STATUS_DIR="$2"
      shift 2
      ;;
    --root)
      BAR_ROOT="$2"
      shift 2
      ;;
    --feed)
      FEED="$2"
      shift 2
      ;;
    --poll-seconds)
      POLL_SECONDS="$2"
      shift 2
      ;;
    --historical-interval-hours)
      HISTORICAL_INTERVAL_HOURS="$2"
      shift 2
      ;;
    --historical-cooldown-minutes)
      HISTORICAL_COOLDOWN_MINUTES="$2"
      shift 2
      ;;
    --max-strategies-historical)
      MAX_STRATEGIES_HISTORICAL="$2"
      shift 2
      ;;
    --max-strategies-fresh)
      MAX_STRATEGIES_FRESH="$2"
      shift 2
      ;;
    --no-dynamic-historical-backlog)
      NO_DYNAMIC_HISTORICAL_BACKLOG="yes"
      shift
      ;;
    --dynamic-historical-backlog-size)
      DYNAMIC_HISTORICAL_BACKLOG_SIZE="$2"
      shift 2
      ;;
    --leader-tuning-profile-count)
      LEADER_TUNING_PROFILE_COUNT="$2"
      shift 2
      ;;
    --tuning-mode)
      TUNING_MODE="yes"
      shift
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
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${ROOT_DIR}/${OUTPUT_DIR}"
fi
if [[ "${STATUS_DIR}" != /* ]]; then
  STATUS_DIR="${ROOT_DIR}/${STATUS_DIR}"
fi
if [[ "${BAR_ROOT}" != /* ]]; then
  BAR_ROOT="${ROOT_DIR}/${BAR_ROOT}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Required env file not found: ${ENV_FILE}" >&2
  exit 78
fi

if [[ "${START_SERVICE}" == "yes" ]]; then
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${APP_SUPPORT_DIR}" "${STATUS_DIR}" \
  "${ROOT_DIR}/data/runtime/logs"
install -m 600 "${ENV_FILE}" "${LAUNCHD_ENV_FILE}"

DYNAMIC_HISTORICAL_BACKLOG_STATUS="enabled"
if [[ "${NO_DYNAMIC_HISTORICAL_BACKLOG}" == "yes" ]]; then
  DYNAMIC_HISTORICAL_BACKLOG_STATUS="disabled"
fi

{
  cat <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR}"
ENV_FILE="${LAUNCHD_ENV_FILE}"
PYTHON_BIN="\${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "\${PYTHON_BIN}" ]]; then
  echo "Project virtualenv Python not found: \${PYTHON_BIN}" >&2
  echo "Run: uv sync --dev" >&2
  exit 78
fi

cd "\${ROOT_DIR}"
echo "Starting autonomous learning service"
echo "Historical experiments: continuous queue"
echo "Dynamic historical backlog: ${DYNAMIC_HISTORICAL_BACKLOG_STATUS}"
echo "Dynamic backlog size: ${DYNAMIC_HISTORICAL_BACKLOG_SIZE}"
echo "Historical cooldown: ${HISTORICAL_COOLDOWN_MINUTES} minute(s)"
echo "Tuning mode: ${TUNING_MODE}"
echo "Fresh market-data learning: after close via ${FEED}"
echo "Promotion: manual and evidence-gated"
cmd=(
  "\${PYTHON_BIN}"
  "-u"
  "-m"
  "trading_app.learning.autonomous_service"
  "--env-file"
  "\${ENV_FILE}"
  "--output-dir"
  "${OUTPUT_DIR}"
  "--status-dir"
  "${STATUS_DIR}"
  "--root"
  "${BAR_ROOT}"
  "--feed"
  "${FEED}"
  "--poll-seconds"
  "${POLL_SECONDS}"
  "--historical-interval-hours"
  "${HISTORICAL_INTERVAL_HOURS}"
  "--historical-cooldown-minutes"
  "${HISTORICAL_COOLDOWN_MINUTES}"
  "--max-strategies-historical"
  "${MAX_STRATEGIES_HISTORICAL}"
  "--max-strategies-fresh"
  "${MAX_STRATEGIES_FRESH}"
  "--dynamic-historical-backlog-size"
  "${DYNAMIC_HISTORICAL_BACKLOG_SIZE}"
  "--leader-tuning-profile-count"
  "${LEADER_TUNING_PROFILE_COUNT}"
)
if [[ "${NO_DYNAMIC_HISTORICAL_BACKLOG}" == "yes" ]]; then
  cmd+=("--no-dynamic-historical-backlog")
fi
if [[ "${TUNING_MODE}" == "yes" ]]; then
  cmd+=("--tuning-mode")
fi
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
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>60</integer>
  <key>StandardOutPath</key>
  <string>${ROOT_DIR}/data/runtime/logs/autonomous-learning.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT_DIR}/data/runtime/logs/autonomous-learning.launchd.err.log</string>
</dict>
</plist>
EOF
} > "${PLIST_PATH}"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "${PLIST_PATH}" >/dev/null
fi

echo "Installed plist: ${PLIST_PATH}"
echo "Installed service wrapper: ${LAUNCHD_WRAPPER}"
echo "Installed launchd env file: ${LAUNCHD_ENV_FILE}"
echo "Service state: ${STATUS_DIR}/latest-autonomous-service-state.json"
echo "Research reports: ${OUTPUT_DIR}"

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
