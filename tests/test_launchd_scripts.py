from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path("scripts")
SCRIPT_NAMES = (
    "run_alpaca_paper_runtime.sh",
    "install_alpaca_paper_launchd.sh",
    "uninstall_alpaca_paper_launchd.sh",
    "status_alpaca_paper_launchd.sh",
    "install_operator_web_launchd.sh",
    "uninstall_operator_web_launchd.sh",
    "status_operator_web_launchd.sh",
    "run_runtime_watchdog.sh",
    "install_runtime_watchdog_launchd.sh",
    "uninstall_runtime_watchdog_launchd.sh",
    "status_runtime_watchdog_launchd.sh",
    "run_autonomous_learning_service.sh",
    "install_autonomous_learning_launchd.sh",
    "uninstall_autonomous_learning_launchd.sh",
    "status_autonomous_learning_launchd.sh",
)


def test_launchd_scripts_are_present_executable_and_parse() -> None:
    paths = [SCRIPT_DIR / name for name in SCRIPT_NAMES]

    for path in paths:
        assert path.exists()
        assert os.access(path, os.X_OK)

    subprocess.run(["bash", "-n", *map(str, paths)], check=True)


def test_runtime_wrapper_uses_fixed_paper_runtime_startup() -> None:
    text = (SCRIPT_DIR / "run_alpaca_paper_runtime.sh").read_text(encoding="utf-8")

    assert 'DASHBOARD_PORT="${TRADING_APP_DASHBOARD_PORT:-8765}"' in text
    assert (
        'OPERATOR_DASHBOARD_URL="${TRADING_APP_OPERATOR_DASHBOARD_URL:-'
        'http://127.0.0.1:3003/}"'
    ) in text
    assert 'ACTIVE_MODEL_KEY="${TRADING_APP_ACTIVE_MODEL_KEY:-' in text
    assert 'STARTING_CASH="${TRADING_APP_STARTING_CASH:-100000}"' in text
    assert 'MANAGED_CAPITAL="${TRADING_APP_MANAGED_CAPITAL:-}"' in text
    assert (
        'MAX_PAPER_SYMBOL_ALLOCATION="${TRADING_APP_MAX_PAPER_SYMBOL_ALLOCATION:-}"'
        in text
    )
    assert (
        'MAX_PAPER_SEMICONDUCTOR_ALLOCATION="'
        '${TRADING_APP_MAX_PAPER_SEMICONDUCTOR_ALLOCATION:-}"'
    ) in text
    assert (
        'INITIAL_PAPER_DEPLOYMENT_ALLOCATION="'
        '${TRADING_APP_INITIAL_PAPER_DEPLOYMENT_ALLOCATION:-}"'
    ) in text
    assert 'PAPER_EPOCH_STARTED_AT="${TRADING_APP_PAPER_EPOCH_STARTED_AT:-}"' in text
    assert (
        'SHADOW_CHALLENGER_MODEL_KEY="${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEY:-'
    ) in text
    assert (
        'SHADOW_CHALLENGER_MODEL_KEYS="${TRADING_APP_SHADOW_CHALLENGER_MODEL_KEYS:-'
    ) in text
    assert 'STRATEGY_SCHEDULE="${TRADING_APP_STRATEGY_SCHEDULE:-daily_close}"' in text
    assert 'lsof -tiTCP:"${DASHBOARD_PORT}"' in text
    assert "refusing to choose a different port" in text
    assert "trading_app.runtime.run_alpaca_paper" in text
    assert "--dashboard-redirect-url" in text
    assert "--starting-cash" in text
    assert "--managed-capital" in text
    assert "--max-paper-symbol-allocation" in text
    assert "--max-paper-semiconductor-allocation" in text
    assert "--initial-paper-deployment-allocation" in text
    assert "--paper-epoch-started-at" in text
    assert "--active-model-key" in text
    assert "--shadow-challenger-model-key" in text
    assert "--shadow-challenger-model-keys" in text
    assert "--strategy-schedule" in text
    assert "--monitor-only-dry-run-first" in text
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_launchd_installer_writes_run_at_load_without_keepalive_restart() -> None:
    text = (SCRIPT_DIR / "install_alpaca_paper_launchd.sh").read_text(encoding="utf-8")

    assert 'LABEL="com.trading-app.alpaca-paper"' in text
    assert 'DASHBOARD_PORT="8765"' in text
    assert 'OPERATOR_DASHBOARD_URL="http://127.0.0.1:3003/"' in text
    assert 'ACTIVE_MODEL_KEY="monthly_sector_momentum:1.0.0"' in text
    assert 'STARTING_CASH="100000"' in text
    assert 'MANAGED_CAPITAL=""' in text
    assert 'MAX_PAPER_SYMBOL_ALLOCATION=""' in text
    assert 'MAX_PAPER_SEMICONDUCTOR_ALLOCATION=""' in text
    assert 'INITIAL_PAPER_DEPLOYMENT_ALLOCATION=""' in text
    assert 'PAPER_EPOCH_STARTED_AT=""' in text
    assert 'SHADOW_CHALLENGER_MODEL_KEY=""' in text
    assert 'SHADOW_CHALLENGER_MODEL_KEYS=""' in text
    assert 'STRATEGY_SCHEDULE="daily_close"' in text
    assert "RunAtLoad" in text
    assert "<true/>" in text
    assert "KeepAlive" in text
    assert "<false/>" in text
    assert "Library/Application Support/trading-app" in text
    assert "alpaca-paper.env" in text
    assert "run_alpaca_paper_runtime.sh" in text
    assert "TRADING_APP_OPERATOR_DASHBOARD_URL" in text
    assert "TRADING_APP_STARTING_CASH" in text
    assert "TRADING_APP_MANAGED_CAPITAL" in text
    assert "TRADING_APP_MAX_PAPER_SYMBOL_ALLOCATION" in text
    assert "TRADING_APP_MAX_PAPER_SEMICONDUCTOR_ALLOCATION" in text
    assert "TRADING_APP_INITIAL_PAPER_DEPLOYMENT_ALLOCATION" in text
    assert "TRADING_APP_PAPER_EPOCH_STARTED_AT" in text
    assert "TRADING_APP_ACTIVE_MODEL_KEY" in text
    assert "TRADING_APP_SHADOW_CHALLENGER_MODEL_KEY" in text
    assert "TRADING_APP_SHADOW_CHALLENGER_MODEL_KEYS" in text
    assert "TRADING_APP_STRATEGY_SCHEDULE" in text
    assert "--dashboard-redirect-url" in text
    assert "--starting-cash" in text
    assert "--managed-capital" in text
    assert "--max-paper-symbol-allocation" in text
    assert "--max-paper-semiconductor-allocation" in text
    assert "--initial-paper-deployment-allocation" in text
    assert "--paper-epoch-started-at" in text
    assert "--active-model-key" in text
    assert "--shadow-challenger-model-key" in text
    assert "--shadow-challenger-model-keys" in text
    assert "--strategy-schedule" in text
    assert "install -m 600" in text
    assert "LAUNCHD_WRAPPER" in text
    assert "launchctl bootstrap" in text
    assert "launchctl kickstart" in text
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_launchd_uninstaller_removes_generated_support_files() -> None:
    text = (SCRIPT_DIR / "uninstall_alpaca_paper_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert "Library/Application Support/trading-app" in text
    assert "alpaca-paper.env" in text
    assert "run_alpaca_paper_runtime.sh" in text
    assert "--keep-support-files" in text
    assert 'rm -f "${LAUNCHD_ENV_FILE}"' in text


def test_launchd_status_reports_generated_support_files() -> None:
    text = (SCRIPT_DIR / "status_alpaca_paper_launchd.sh").read_text(encoding="utf-8")

    assert "Library/Application Support/trading-app" in text
    assert "Runtime wrapper installed" in text
    assert "Launchd env file installed" in text
    assert "Python backend/API URL: http://127.0.0.1:${DASHBOARD_PORT}/" in text
    assert "Operator dashboard URL: ${OPERATOR_DASHBOARD_URL}" in text


def test_operator_web_launchd_installer_runs_next_against_backend() -> None:
    text = (SCRIPT_DIR / "install_operator_web_launchd.sh").read_text(encoding="utf-8")

    assert 'LABEL="com.trading-app.operator-web"' in text
    assert 'WEB_HOST="127.0.0.1"' in text
    assert 'WEB_PORT="3003"' in text
    assert 'BACKEND_URL="http://127.0.0.1:8765"' in text
    assert 'REPLAY_REPORT_DIR="${ROOT_DIR}/data/research/replay"' in text
    assert '"${NPM_BIN}" ci' in text
    assert 'TRADING_APP_REPLAY_REPORT_DIR="${REPLAY_REPORT_DIR}"' in text
    assert '"${NPM_BIN}" run build' in text
    assert "TRADING_APP_BACKEND_URL" in text
    assert '"\\${NPM_BIN}" run start -- --hostname' in text
    assert "--port" in text
    assert "operator-web.launchd.out.log" in text
    assert "operator-web.launchd.err.log" in text
    assert "RunAtLoad" in text
    assert "KeepAlive" in text
    assert "<false/>" in text
    assert "launchctl bootstrap" in text
    assert "launchctl kickstart" in text
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_operator_web_uninstaller_removes_generated_support_files() -> None:
    text = (SCRIPT_DIR / "uninstall_operator_web_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert "Library/Application Support/trading-app" in text
    assert "operator-web.env" in text
    assert "run_operator_web.sh" in text
    assert "--keep-support-files" in text
    assert 'rm -f "${LAUNCHD_ENV_FILE}"' in text


def test_operator_web_status_reports_web_and_backend_urls() -> None:
    text = (SCRIPT_DIR / "status_operator_web_launchd.sh").read_text(encoding="utf-8")

    assert "Library/Application Support/trading-app" in text
    assert "Web wrapper installed" in text
    assert "Launchd env file installed" in text
    assert "Replay report directory: ${TRADING_APP_REPLAY_REPORT_DIR}" in text
    assert (
        "Operator dashboard URL: "
        "http://${TRADING_APP_WEB_HOST}:${TRADING_APP_WEB_PORT}/"
    ) in text
    assert "Python backend URL: ${TRADING_APP_BACKEND_URL}" in text


def test_runtime_watchdog_launchd_installer_checks_fixed_backend() -> None:
    text = (SCRIPT_DIR / "install_runtime_watchdog_launchd.sh").read_text(
        encoding="utf-8"
    )
    wrapper = (SCRIPT_DIR / "run_runtime_watchdog.sh").read_text(encoding="utf-8")
    status = (SCRIPT_DIR / "status_runtime_watchdog_launchd.sh").read_text(
        encoding="utf-8"
    )
    uninstaller = (SCRIPT_DIR / "uninstall_runtime_watchdog_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert 'LABEL="com.trading-app.runtime-watchdog"' in text
    assert "StartInterval" in text
    assert "runtime-watchdog.launchd.out.log" in text
    assert "launchctl kickstart" in text
    assert "run_runtime_watchdog.sh" in text
    assert "runtime-watchdog.env" in text
    assert "install -m 600" in text
    assert "http://127.0.0.1:8765/api/snapshot" in wrapper
    assert "trading_app.runtime.watchdog" in wrapper
    assert "--restart" in wrapper
    assert "latest-runtime-watchdog-report.json" in status
    assert "Launchd env file installed" in status
    assert "runtime-watchdog.env" in uninstaller
    assert "run_runtime_watchdog.sh" in uninstaller
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_autonomous_learning_launchd_installer_runs_research_service() -> None:
    text = (SCRIPT_DIR / "install_autonomous_learning_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert 'LABEL="com.trading-app.autonomous-learning"' in text
    assert 'OUTPUT_DIR="data/research/replay"' in text
    assert 'STATUS_DIR="data/runtime/learning"' in text
    assert 'BAR_ROOT="data/market_data/bars"' in text
    assert 'FEED="SIP"' in text
    assert 'POLL_SECONDS="60"' in text
    assert 'HISTORICAL_INTERVAL_HOURS="0"' in text
    assert 'HISTORICAL_COOLDOWN_MINUTES="1"' in text
    assert 'MAX_STRATEGIES_HISTORICAL="36"' in text
    assert 'MAX_STRATEGIES_FRESH="24"' in text
    assert "trading_app.learning.autonomous_service" in text
    assert "--historical-interval-hours" in text
    assert "--historical-cooldown-minutes" in text
    assert "--max-strategies-historical" in text
    assert "--max-strategies-fresh" in text
    assert "RunAtLoad" in text
    assert "KeepAlive" in text
    assert "<true/>" in text
    assert "ThrottleInterval" in text
    assert "autonomous-learning.launchd.out.log" in text
    assert "autonomous-learning.launchd.err.log" in text
    assert "install -m 600" in text
    assert "launchctl bootstrap" in text
    assert "launchctl kickstart" in text
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_autonomous_learning_runner_uses_service_cli() -> None:
    text = (SCRIPT_DIR / "run_autonomous_learning_service.sh").read_text(
        encoding="utf-8"
    )

    assert "trading_app.learning.autonomous_service" in text
    assert "--env-file" in text
    assert "Strategy promotion remains manual" in text
    assert "ALPACA_SECRET_KEY=" not in text
    assert "ALPACA_API_KEY=" not in text


def test_autonomous_learning_uninstaller_removes_generated_support_files() -> None:
    text = (SCRIPT_DIR / "uninstall_autonomous_learning_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert "Library/Application Support/trading-app" in text
    assert "autonomous-learning.env" in text
    assert "run_autonomous_learning_service.sh" in text
    assert "--keep-support-files" in text
    assert 'rm -f "${LAUNCHD_ENV_FILE}"' in text


def test_autonomous_learning_status_reports_state_and_logs() -> None:
    text = (SCRIPT_DIR / "status_autonomous_learning_launchd.sh").read_text(
        encoding="utf-8"
    )

    assert "Library/Application Support/trading-app" in text
    assert "Service wrapper installed" in text
    assert "Launchd env file installed" in text
    assert "latest-autonomous-service-state.json" in text
    assert "latest-learning-cycle.json" in text
    assert "next_historical_hypothesis_id" in text
    assert "historical_hypothesis_counts" in text
    assert "autonomous-learning.launchd.out.log" in text
    assert "autonomous-learning.launchd.err.log" in text
