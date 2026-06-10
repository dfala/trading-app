#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.autonomous-learning"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/autonomous-learning.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_autonomous_learning_service.sh"
LOG_DIR="${HOME}/Library/Logs/trading-app"
STATE_FILE="${ROOT_DIR}/data/runtime/learning/latest-autonomous-service-state.json"
LATEST_CYCLE="${ROOT_DIR}/data/runtime/learning/latest-learning-cycle.json"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi

echo "Label: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
if [[ -f "${PLIST_PATH}" ]]; then
  echo "Plist installed: yes"
else
  echo "Plist installed: no"
fi
if [[ -x "${LAUNCHD_WRAPPER}" ]]; then
  echo "Service wrapper installed: yes (${LAUNCHD_WRAPPER})"
else
  echo "Service wrapper installed: no (${LAUNCHD_WRAPPER})"
fi
if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  echo "Launchd env file installed: yes ($(stat -f '%Sp' "${LAUNCHD_ENV_FILE}" 2>/dev/null || echo permissions-unknown))"
else
  echo "Launchd env file installed: no (${LAUNCHD_ENV_FILE})"
fi
echo "Service state: ${STATE_FILE}"
echo "Latest learning cycle: ${LATEST_CYCLE}"
echo "Launchd logs: ${LOG_DIR}"

echo
echo "launchctl:"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | sed -n '1,80p' || true

echo
echo "Recent service state:"
if [[ -n "${PYTHON_BIN}" ]]; then
  "${PYTHON_BIN}" - <<EOF 2>/dev/null || true
import json
from pathlib import Path
path = Path("${STATE_FILE}")
if path.exists():
    state = json.loads(path.read_text())
    for key in (
        "service_status",
        "heartbeat_at",
        "current_task",
        "current_historical_hypothesis_id",
        "last_historical_hypothesis_id",
        "next_historical_hypothesis_id",
        "historical_hypothesis_counts",
        "last_cycle_run_id",
        "last_cycle_status",
        "latest_recommended_challenger_model_key",
        "next_historical_experiment_due_at",
        "next_fresh_market_data_due_at",
        "last_error",
    ):
        print(f"{key}: {state.get(key)}")
else:
    print("missing")
EOF
else
  echo "python unavailable"
fi

echo
echo "Recent stdout log:"
tail -40 "${LOG_DIR}/autonomous-learning.launchd.out.log" 2>/dev/null || true

echo
echo "Recent stderr log:"
tail -40 "${LOG_DIR}/autonomous-learning.launchd.err.log" 2>/dev/null || true
