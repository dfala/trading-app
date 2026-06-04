#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.alpaca-paper"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/alpaca-paper.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_alpaca_paper_runtime.sh"
DASHBOARD_PORT="${TRADING_APP_DASHBOARD_PORT:-8765}"
OPERATOR_DASHBOARD_URL="${TRADING_APP_OPERATOR_DASHBOARD_URL:-http://127.0.0.1:3003/}"

if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  . "${LAUNCHD_ENV_FILE}"
fi

DASHBOARD_PORT="${TRADING_APP_DASHBOARD_PORT:-${DASHBOARD_PORT}}"
OPERATOR_DASHBOARD_URL="${TRADING_APP_OPERATOR_DASHBOARD_URL:-${OPERATOR_DASHBOARD_URL}}"

echo "Label: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
if [[ -f "${PLIST_PATH}" ]]; then
  echo "Plist installed: yes"
else
  echo "Plist installed: no"
fi
if [[ -x "${LAUNCHD_WRAPPER}" ]]; then
  echo "Runtime wrapper installed: yes (${LAUNCHD_WRAPPER})"
else
  echo "Runtime wrapper installed: no (${LAUNCHD_WRAPPER})"
fi
if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  echo "Launchd env file installed: yes ($(stat -f '%Sp' "${LAUNCHD_ENV_FILE}" 2>/dev/null || echo permissions-unknown))"
else
  echo "Launchd env file installed: no (${LAUNCHD_ENV_FILE})"
fi
echo "Python backend/API URL: http://127.0.0.1:${DASHBOARD_PORT}/"
echo "Operator dashboard URL: ${OPERATOR_DASHBOARD_URL}"

echo
echo "launchctl:"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | sed -n '1,80p' || true

echo
echo "Python backend/API listener:"
lsof -nP -iTCP:"${DASHBOARD_PORT}" -sTCP:LISTEN || true

echo
echo "Recent stdout log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/launchd.out.log" 2>/dev/null || true

echo
echo "Recent stderr log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/launchd.err.log" 2>/dev/null || true
