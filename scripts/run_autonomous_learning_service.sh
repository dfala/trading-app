#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

usage() {
  cat <<'EOF'
Usage: run_autonomous_learning_service.sh [options]

Start the autonomous self-feeding research service.

Options:
  --env-file PATH       Local env file. Default: .env
  --output-dir PATH     Research report directory. Default: data/research/replay
  --status-dir PATH     Runtime learning state directory. Default: data/runtime/learning
  --root PATH           Historical bar store. Default: data/market_data/bars
  --feed FEED           Market data feed. Default: SIP
  --poll-seconds N      Scheduler polling interval. Default: 900
  --no-dynamic-historical-backlog
                       Disable generated historical exploration/tuning profiles.
  --dynamic-historical-backlog-size N
                       Generated profile cap. Default: 5000
  --leader-tuning-profile-count N
                       Leader-focused tuning profile cap. Default: 6
  --tuning-mode         Allow explicit repeated historical sweeps for parameter
                        tuning after the novelty queue is exhausted.
  --once                Run one due scheduler pass and exit.
  -h, --help            Show this help.

The service runs research only. Strategy promotion remains manual and
evidence-gated.
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

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Project virtualenv Python not found: ${PYTHON_BIN}" >&2
  echo "Run: uv sync --dev" >&2
  exit 78
fi

mkdir -p "${ROOT_DIR}/data/runtime/logs"
cd "${ROOT_DIR}"

exec "${PYTHON_BIN}" -u -m trading_app.learning.autonomous_service \
  --env-file "${ENV_FILE}" "$@"
