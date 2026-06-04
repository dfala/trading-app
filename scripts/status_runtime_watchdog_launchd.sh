#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.trading-app.runtime-watchdog"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/runtime-watchdog.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_runtime_watchdog.sh"

echo "Label: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
if [[ -f "${PLIST_PATH}" ]]; then
  echo "Plist installed: yes"
else
  echo "Plist installed: no"
fi
if [[ -x "${LAUNCHD_WRAPPER}" ]]; then
  echo "Watchdog wrapper installed: yes (${LAUNCHD_WRAPPER})"
else
  echo "Watchdog wrapper installed: no (${LAUNCHD_WRAPPER})"
fi
if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
  echo "Launchd env file installed: yes (${LAUNCHD_ENV_FILE})"
else
  echo "Launchd env file installed: no (${LAUNCHD_ENV_FILE})"
fi

echo
echo "launchctl:"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | sed -n '1,80p' || true

echo
echo "Latest watchdog report:"
cat "${ROOT_DIR}/data/runtime/state/latest-runtime-watchdog-report.json" 2>/dev/null || true

echo
echo "Recent stdout log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/runtime-watchdog.launchd.out.log" 2>/dev/null || true

echo
echo "Recent stderr log:"
tail -40 "${ROOT_DIR}/data/runtime/logs/runtime-watchdog.launchd.err.log" 2>/dev/null || true
