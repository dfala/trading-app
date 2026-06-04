#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

usage() {
  cat <<'EOF'
Usage: run_runtime_watchdog.sh [options]

Check the local paper runtime and optionally restart the launchd service.

Options:
  --env-file PATH       Local env file. Default: .env
  --output-dir PATH     Runtime artifact directory. Default: data/runtime
  --dashboard-url URL   Runtime API snapshot URL. Default: http://127.0.0.1:8765/api/snapshot
  --launchd-label LABEL Launchd job label. Default: com.trading-app.alpaca-paper
  --max-heartbeat-age-minutes N
                        Restart if the runtime heartbeat is older than this. Default: 5
  --no-restart          Report only; do not kickstart launchd.
  -h, --help            Show this help.
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

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

OUTPUT_DIR="${TRADING_APP_OUTPUT_DIR:-data/runtime}"
DASHBOARD_URL="${TRADING_APP_WATCHDOG_DASHBOARD_URL:-http://127.0.0.1:8765/api/snapshot}"
LAUNCHD_LABEL="${TRADING_APP_WATCHDOG_LAUNCHD_LABEL:-com.trading-app.alpaca-paper}"
MAX_HEARTBEAT_AGE_MINUTES="${TRADING_APP_WATCHDOG_MAX_HEARTBEAT_AGE_MINUTES:-5}"
RESTART="${TRADING_APP_WATCHDOG_RESTART:-yes}"

while (($#)); do
  case "$1" in
    --env-file)
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --dashboard-url)
      DASHBOARD_URL="$2"
      shift 2
      ;;
    --launchd-label)
      LAUNCHD_LABEL="$2"
      shift 2
      ;;
    --max-heartbeat-age-minutes)
      MAX_HEARTBEAT_AGE_MINUTES="$2"
      shift 2
      ;;
    --no-restart)
      RESTART="no"
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

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Project virtualenv Python not found: ${PYTHON_BIN}" >&2
  echo "Run: uv sync --dev" >&2
  exit 78
fi

cmd=(
  "${PYTHON_BIN}"
  "-m"
  "trading_app.runtime.watchdog"
  "--output-dir"
  "${OUTPUT_DIR}"
  "--dashboard-url"
  "${DASHBOARD_URL}"
  "--launchd-label"
  "${LAUNCHD_LABEL}"
  "--max-heartbeat-age-minutes"
  "${MAX_HEARTBEAT_AGE_MINUTES}"
)

if [[ "${RESTART}" == "yes" ]]; then
  cmd+=("--restart")
fi

cd "${ROOT_DIR}"
exec "${cmd[@]}"
