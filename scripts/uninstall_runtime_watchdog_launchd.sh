#!/usr/bin/env bash
set -euo pipefail

LABEL="com.trading-app.runtime-watchdog"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/runtime-watchdog.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_runtime_watchdog.sh"
KEEP_PLIST="no"
KEEP_SUPPORT_FILES="no"

usage() {
  cat <<'EOF'
Usage: uninstall_runtime_watchdog_launchd.sh [--keep-plist] [--keep-support-files]

Unload and remove the local paper runtime watchdog LaunchAgent.
EOF
}

while (($#)); do
  case "$1" in
    --keep-plist)
      KEEP_PLIST="yes"
      shift
      ;;
    --keep-support-files)
      KEEP_SUPPORT_FILES="yes"
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

launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

if [[ "${KEEP_PLIST}" != "yes" ]]; then
  rm -f "${PLIST_PATH}"
  echo "Removed plist: ${PLIST_PATH}"
fi

if [[ "${KEEP_SUPPORT_FILES}" != "yes" ]]; then
  rm -f "${LAUNCHD_ENV_FILE}"
  echo "Removed launchd env file: ${LAUNCHD_ENV_FILE}"
  rm -f "${LAUNCHD_WRAPPER}"
  echo "Removed watchdog wrapper: ${LAUNCHD_WRAPPER}"
fi
