#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.operator-web"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/operator-web.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_operator_web.sh"

TRADING_APP_WEB_HOST="${TRADING_APP_WEB_HOST:-127.0.0.1}"
TRADING_APP_WEB_PORT="${TRADING_APP_WEB_PORT:-3003}"
TRADING_APP_BACKEND_URL="${TRADING_APP_BACKEND_URL:-http://127.0.0.1:8765}"
TRADING_APP_REPLAY_REPORT_DIR="${TRADING_APP_REPLAY_REPORT_DIR:-${ROOT_DIR}/data/research/replay}"

if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  . "${LAUNCHD_ENV_FILE}"
fi

echo "Label: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
if [[ -f "${PLIST_PATH}" ]]; then
  echo "Plist installed: yes"
else
  echo "Plist installed: no"
fi
if [[ -x "${LAUNCHD_WRAPPER}" ]]; then
  echo "Web wrapper installed: yes (${LAUNCHD_WRAPPER})"
else
  echo "Web wrapper installed: no (${LAUNCHD_WRAPPER})"
fi
if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  echo "Launchd env file installed: yes ($(stat -f '%Sp' "${LAUNCHD_ENV_FILE}" 2>/dev/null || echo permissions-unknown))"
else
  echo "Launchd env file installed: no (${LAUNCHD_ENV_FILE})"
fi
echo "Operator dashboard URL: http://${TRADING_APP_WEB_HOST}:${TRADING_APP_WEB_PORT}/"
echo "Python backend URL: ${TRADING_APP_BACKEND_URL}"
echo "Replay report directory: ${TRADING_APP_REPLAY_REPORT_DIR}"

echo
echo "launchctl:"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | sed -n '1,80p' || true

echo
echo "Operator dashboard listener:"
lsof -nP -iTCP:"${TRADING_APP_WEB_PORT}" -sTCP:LISTEN || true

backend_port="$(
  printf '%s' "${TRADING_APP_BACKEND_URL}" |
    sed -E 's#^https?://(127\.0\.0\.1|localhost|\[::1\]):?([0-9]*).*#\2#'
)"
if [[ -n "${backend_port}" && "${backend_port}" != "${TRADING_APP_BACKEND_URL}" ]]; then
  echo
  echo "Python backend listener:"
  lsof -nP -iTCP:"${backend_port}" -sTCP:LISTEN || true
fi

echo
echo "Recent stdout log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/operator-web.launchd.out.log" 2>/dev/null || true

echo
echo "Recent stderr log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/operator-web.launchd.err.log" 2>/dev/null || true
