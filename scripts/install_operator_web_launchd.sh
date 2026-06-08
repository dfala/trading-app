#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${ROOT_DIR}/web"
LABEL="com.trading-app.operator-web"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/operator-web.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_operator_web.sh"
OUTPUT_DIR="data/runtime"
WEB_HOST="127.0.0.1"
WEB_PORT="3003"
BACKEND_URL="http://127.0.0.1:8765"
REPLAY_REPORT_DIR="${ROOT_DIR}/data/research/replay"
NPM_BIN="${NPM_BIN:-}"
INSTALL_DEPS="yes"
BUILD_APP="yes"
START_SERVICE="yes"

usage() {
  cat <<'EOF'
Usage: install_operator_web_launchd.sh [options]

Install the macOS LaunchAgent for the Next.js operator dashboard.

Options:
  --backend-url URL  Python backend URL. Default: http://127.0.0.1:8765
  --web-host HOST    Next.js bind host. Default: 127.0.0.1
  --web-port PORT    Next.js dashboard port. Default: 3003
  --replay-report-dir PATH
                     Historical replay markdown directory. Default: data/research/replay
  --output-dir PATH  Runtime artifact directory. Default: data/runtime
  --npm-bin PATH     npm binary to use. Default: first npm on PATH
  --no-install       Skip npm ci/install before building.
  --no-build         Skip npm run build before installing launchd.
  --no-start         Write the plist but do not bootstrap/kickstart it.
  -h, --help         Show this help.

This service runs the web UI only. The Python paper runtime remains the trading
authority and should keep running at the configured backend URL.
EOF
}

while (($#)); do
  case "$1" in
    --backend-url)
      BACKEND_URL="$2"
      shift 2
      ;;
    --web-host)
      WEB_HOST="$2"
      shift 2
      ;;
    --web-port)
      WEB_PORT="$2"
      shift 2
      ;;
    --replay-report-dir)
      REPLAY_REPORT_DIR="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --npm-bin)
      NPM_BIN="$2"
      shift 2
      ;;
    --no-install)
      INSTALL_DEPS="no"
      shift
      ;;
    --no-build)
      BUILD_APP="no"
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

if [[ "${OUTPUT_DIR}" == /* ]]; then
  RUNTIME_OUTPUT_DIR="${OUTPUT_DIR}"
else
  RUNTIME_OUTPUT_DIR="${ROOT_DIR}/${OUTPUT_DIR}"
fi

if [[ "${REPLAY_REPORT_DIR}" != /* ]]; then
  REPLAY_REPORT_DIR="${ROOT_DIR}/${REPLAY_REPORT_DIR}"
fi

if [[ ! -f "${WEB_DIR}/package.json" ]]; then
  echo "Next.js web app not found: ${WEB_DIR}" >&2
  exit 78
fi

if [[ "${WEB_HOST}" != "127.0.0.1" && "${WEB_HOST}" != "localhost" && "${WEB_HOST}" != "::1" ]]; then
  echo "Refusing non-local web host: ${WEB_HOST}" >&2
  exit 78
fi

if ! [[ "${WEB_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Web port must be numeric: ${WEB_PORT}" >&2
  exit 64
fi

case "${BACKEND_URL}" in
  http://127.0.0.1|http://127.0.0.1:*|http://localhost|http://localhost:*|http://[::1]|http://[::1]:*) ;;
  *)
    echo "Refusing non-local backend URL: ${BACKEND_URL}" >&2
    exit 78
    ;;
esac

if [[ -z "${NPM_BIN}" ]]; then
  NPM_BIN="$(command -v npm || true)"
fi

if [[ -z "${NPM_BIN}" || ! -x "${NPM_BIN}" ]]; then
  echo "npm not found. Install Node.js/npm or pass --npm-bin." >&2
  exit 78
fi

if [[ "${START_SERVICE}" == "yes" ]]; then
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

if [[ "${START_SERVICE}" == "yes" ]] && command -v lsof >/dev/null 2>&1; then
  listeners="$(lsof -tiTCP:"${WEB_PORT}" -sTCP:LISTEN || true)"
  if [[ -n "${listeners}" ]]; then
    echo "Web port ${WEB_PORT} is already in use. Stop that process before installing launchd." >&2
    lsof -nP -iTCP:"${WEB_PORT}" -sTCP:LISTEN >&2 || true
    exit 78
  fi
fi

if [[ "${INSTALL_DEPS}" == "yes" ]]; then
  (
    cd "${WEB_DIR}"
    if [[ -f package-lock.json ]]; then
      "${NPM_BIN}" ci
    else
      "${NPM_BIN}" install
    fi
  )
fi

if [[ "${BUILD_APP}" == "yes" ]]; then
  (
    cd "${WEB_DIR}"
    TRADING_APP_REPLAY_REPORT_DIR="${REPLAY_REPORT_DIR}" "${NPM_BIN}" run build
  )
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${APP_SUPPORT_DIR}" "${RUNTIME_OUTPUT_DIR}/logs"
{
  printf 'NODE_ENV=%q\n' "production"
  printf 'TRADING_APP_WEB_HOST=%q\n' "${WEB_HOST}"
  printf 'TRADING_APP_WEB_PORT=%q\n' "${WEB_PORT}"
  printf 'TRADING_APP_BACKEND_URL=%q\n' "${BACKEND_URL}"
  printf 'TRADING_APP_REPLAY_REPORT_DIR=%q\n' "${REPLAY_REPORT_DIR}"
  printf 'NPM_BIN=%q\n' "${NPM_BIN}"
} > "${LAUNCHD_ENV_FILE}"
chmod 600 "${LAUNCHD_ENV_FILE}"

{
  cat <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR}"
WEB_DIR="\${ROOT_DIR}/web"
ENV_FILE="${LAUNCHD_ENV_FILE}"

set -a
. "\${ENV_FILE}"
set +a

NPM_DIR="\$(dirname "\${NPM_BIN}")"
export PATH="\${NPM_DIR}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NODE_ENV
export TRADING_APP_BACKEND_URL
export TRADING_APP_REPLAY_REPORT_DIR

if command -v lsof >/dev/null 2>&1; then
  listeners="\$(lsof -tiTCP:"\${TRADING_APP_WEB_PORT}" -sTCP:LISTEN || true)"
  if [[ -n "\${listeners}" ]]; then
    echo "Web port \${TRADING_APP_WEB_PORT} is already in use; refusing to choose a different port." >&2
    lsof -nP -iTCP:"\${TRADING_APP_WEB_PORT}" -sTCP:LISTEN >&2 || true
    exit 78
  fi
fi

cd "\${WEB_DIR}"
echo "Starting Next.js operator dashboard on http://\${TRADING_APP_WEB_HOST}:\${TRADING_APP_WEB_PORT}/"
echo "Proxying Python backend at \${TRADING_APP_BACKEND_URL}"
echo "Reading replay reports from \${TRADING_APP_REPLAY_REPORT_DIR}"
exec "\${NPM_BIN}" run start -- --hostname "\${TRADING_APP_WEB_HOST}" --port "\${TRADING_APP_WEB_PORT}"
EOF
} > "${LAUNCHD_WRAPPER}"
chmod 700 "${LAUNCHD_WRAPPER}"

program_args=("/bin/bash" "${LAUNCHD_WRAPPER}")

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
  <string>${RUNTIME_OUTPUT_DIR}/logs/operator-web.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${RUNTIME_OUTPUT_DIR}/logs/operator-web.launchd.err.log</string>
</dict>
</plist>
EOF
} > "${PLIST_PATH}"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "${PLIST_PATH}" >/dev/null
fi

echo "Installed plist: ${PLIST_PATH}"
echo "Installed web wrapper: ${LAUNCHD_WRAPPER}"
echo "Installed launchd env file: ${LAUNCHD_ENV_FILE}"
echo "Operator dashboard URL: http://${WEB_HOST}:${WEB_PORT}/"
echo "Python backend URL: ${BACKEND_URL}"
echo "Replay report directory: ${REPLAY_REPORT_DIR}"

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
