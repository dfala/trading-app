#!/usr/bin/env bash
set -euo pipefail

LABEL="com.trading-app.autonomous-learning"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_SUPPORT_DIR="${HOME}/Library/Application Support/trading-app"
LAUNCHD_ENV_FILE="${APP_SUPPORT_DIR}/autonomous-learning.env"
LAUNCHD_WRAPPER="${APP_SUPPORT_DIR}/run_autonomous_learning_service.sh"
REMOVE_PLIST="yes"
REMOVE_SUPPORT_FILES="yes"

usage() {
  cat <<'EOF'
Usage: uninstall_autonomous_learning_launchd.sh [--keep-plist] [--keep-support-files]

Unload the autonomous learning LaunchAgent and remove its generated local
support files by default.
EOF
}

while (($#)); do
  case "$1" in
    --keep-plist)
      REMOVE_PLIST="no"
      shift
      ;;
    --keep-support-files)
      REMOVE_SUPPORT_FILES="no"
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

if [[ -f "${PLIST_PATH}" ]]; then
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
else
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

if [[ "${REMOVE_PLIST}" == "yes" && -f "${PLIST_PATH}" ]]; then
  rm -f "${PLIST_PATH}"
  echo "Removed plist: ${PLIST_PATH}"
else
  echo "LaunchAgent unloaded: ${LABEL}"
fi

if [[ "${REMOVE_SUPPORT_FILES}" == "yes" ]]; then
  if [[ -f "${LAUNCHD_WRAPPER}" ]]; then
    rm -f "${LAUNCHD_WRAPPER}"
    echo "Removed service wrapper: ${LAUNCHD_WRAPPER}"
  fi
  if [[ -f "${LAUNCHD_ENV_FILE}" ]]; then
    rm -f "${LAUNCHD_ENV_FILE}"
    echo "Removed launchd env file: ${LAUNCHD_ENV_FILE}"
  fi
  rmdir "${APP_SUPPORT_DIR}" >/dev/null 2>&1 || true
fi
