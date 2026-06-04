WEB_REPLAY_REPORT_DIR := $(CURDIR)/data/research/replay

.PHONY: dev dashboard test lint web-install web-dev web-start web-test web-build web-typecheck web-check launchd-install launchd-status launchd-uninstall web-launchd-install web-launchd-status web-launchd-uninstall

dev:
	uv run dev

dashboard:
	uv run dashboard

web-install:
	cd web && npm install

web-dev:
	cd web && TRADING_APP_REPLAY_REPORT_DIR="$(WEB_REPLAY_REPORT_DIR)" npm run dev

web-start: web-build
	cd web && TRADING_APP_REPLAY_REPORT_DIR="$(WEB_REPLAY_REPORT_DIR)" npm run start -- --hostname 127.0.0.1 --port 3003

web-test:
	cd web && npm test

web-build:
	cd web && TRADING_APP_REPLAY_REPORT_DIR="$(WEB_REPLAY_REPORT_DIR)" npm run build

web-typecheck:
	cd web && npm run typecheck

web-check: web-typecheck web-test web-build

launchd-install:
	scripts/install_alpaca_paper_launchd.sh
	scripts/install_operator_web_launchd.sh

launchd-status:
	scripts/status_alpaca_paper_launchd.sh
	scripts/status_operator_web_launchd.sh

launchd-uninstall:
	scripts/uninstall_operator_web_launchd.sh
	scripts/uninstall_alpaca_paper_launchd.sh

web-launchd-install:
	scripts/install_operator_web_launchd.sh

web-launchd-status:
	scripts/status_operator_web_launchd.sh

web-launchd-uninstall:
	scripts/uninstall_operator_web_launchd.sh

test:
	uv run pytest

lint:
	uv run ruff check
