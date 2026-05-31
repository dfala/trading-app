"""Offline startup preflight for the Alpaca paper runtime."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

from trading_app.alpaca_credentials import (
    ALPACA_API_KEY_ENV,
    ALPACA_SECRET_KEY_ENV,
    alpaca_credential_present,
    alpaca_paper_boundary_violations,
)
from trading_app.runtime.cli import parse_symbol_list
from trading_app.runtime.models import (
    RuntimePreflightCheck,
    RuntimePreflightReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, validate_symbol

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AlpacaPaperRuntimePreflight:
    """Evaluate whether local configuration is safe to start paper runtime."""

    def __init__(
        self,
        *,
        config: Any,
        dashboard_host: str = "127.0.0.1",
        env: Mapping[str, str] | None = None,
        require_credentials: bool = True,
        persistence_store: RuntimePersistenceStore | None = None,
    ) -> None:
        self.config = config
        self.dashboard_host = dashboard_host
        self.env = env if env is not None else os.environ
        self.require_credentials = require_credentials
        self.persistence_store = persistence_store or RuntimePersistenceStore(
            config.output_dir
        )

    def run(self, *, as_of: datetime | None = None) -> RuntimePreflightReport:
        checked_at = as_of or datetime.now(tz=UTC)
        checks = (
            self._credentials_check(checked_at),
            self._paper_boundary_check(checked_at),
            self._symbol_scope_check(checked_at),
            self._feed_check(checked_at),
            self._storage_check(checked_at),
            self._recovery_check(checked_at),
            self._dashboard_bind_check(checked_at),
            self._schedule_check(checked_at),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        warnings = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.WARNING
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimePreflightReport(
            as_of=checked_at,
            status=status,
            can_start=failures == 0,
            summary=_summary(status, failures, warnings),
            checks=checks,
            warnings=warnings,
            failures=failures,
        )
        self.persistence_store.persist_preflight_report(report)
        return report

    def _credentials_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        has_api_key = alpaca_credential_present(self.env, ALPACA_API_KEY_ENV)
        has_secret_key = alpaca_credential_present(self.env, ALPACA_SECRET_KEY_ENV)
        if has_api_key and has_secret_key:
            return _check(
                "credentials",
                RuntimePreflightStatus.PASSED,
                "Alpaca credential variables are present.",
                "Keep secrets out of logs and committed files.",
                checked_at,
                ("ALPACA_API_KEY=present", "ALPACA_SECRET_KEY=present"),
            )
        status = (
            RuntimePreflightStatus.FAILED
            if self.require_credentials
            else RuntimePreflightStatus.WARNING
        )
        return _check(
            "credentials",
            status,
            "Alpaca credential variables are missing.",
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY before starting paper runtime.",
            checked_at,
            (
                f"ALPACA_API_KEY={'present' if has_api_key else 'missing'}",
                f"ALPACA_SECRET_KEY={'present' if has_secret_key else 'missing'}",
            ),
        )

    def _paper_boundary_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        violations = alpaca_paper_boundary_violations(self.env)
        if violations:
            return _check(
                "paper_boundary",
                RuntimePreflightStatus.FAILED,
                "A live-trading flag or endpoint override is enabled.",
                (
                    "Unset live-trading flags and live Alpaca endpoint overrides "
                    "before starting paper runtime."
                ),
                checked_at,
                violations,
            )
        return _check(
            "paper_boundary",
            RuntimePreflightStatus.PASSED,
            "Runtime is configured for Alpaca paper mode only.",
            "Keep live trading disabled until a later explicit milestone.",
            checked_at,
            ("broker=alpaca-paper", "live_trading_enabled=false"),
        )

    def _symbol_scope_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        symbols = tuple(getattr(self.config, "symbols", ()))
        invalid: list[str] = []
        normalized: list[str] = []
        for symbol in symbols:
            try:
                normalized.append(validate_symbol(symbol))
            except ValueError:
                invalid.append(str(symbol))
        if invalid:
            return _check(
                "symbol_scope",
                RuntimePreflightStatus.FAILED,
                "One or more symbols are outside the supported U.S. stock/ETF format.",
                "Use uppercase U.S.-listed stock or ETF tickers only.",
                checked_at,
                tuple(invalid),
            )
        if not normalized:
            return _check(
                "symbol_scope",
                RuntimePreflightStatus.FAILED,
                "No symbols were configured for the runtime.",
                "Provide at least one U.S.-listed stock or ETF symbol.",
                checked_at,
            )
        return _check(
            "symbol_scope",
            RuntimePreflightStatus.PASSED,
            "Configured symbols pass the U.S. stock/ETF ticker format check.",
            "Keep non-U.S. markets, options, crypto, and futures out of this runtime.",
            checked_at,
            tuple(normalized),
        )

    def _feed_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        feed = self.config.feed
        if feed not in {DataFeed.IEX, DataFeed.SIP}:
            return _check(
                "market_data_feed",
                RuntimePreflightStatus.FAILED,
                "Alpaca latest-price runtime requires IEX or SIP feed.",
                (
                    "Use IEX for development or SIP when subscription and readiness "
                    "allow it."
                ),
                checked_at,
                (str(feed),),
            )
        if feed == DataFeed.IEX:
            return _check(
                "market_data_feed",
                RuntimePreflightStatus.WARNING,
                "IEX/free data is development-grade.",
                "Use this for paper runtime learning, not final funding decisions.",
                checked_at,
                (feed.value,),
            )
        return _check(
            "market_data_feed",
            RuntimePreflightStatus.PASSED,
            "SIP feed is configured.",
            (
                "Confirm subscription, cost assumptions, and data freshness during "
                "runtime."
            ),
            checked_at,
            (feed.value,),
        )

    def _storage_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        output_dir = Path(self.config.output_dir)
        try:
            self.persistence_store.ensure()
            test_path = self.persistence_store.state_dir / ".preflight-write-test"
            test_path.write_text("ok", encoding="utf-8")
            test_path.unlink(missing_ok=True)
        except OSError as error:
            return _check(
                "runtime_storage",
                RuntimePreflightStatus.FAILED,
                "Runtime storage is not writable.",
                "Choose a writable ignored local output directory.",
                checked_at,
                (str(output_dir), str(error)),
            )
        status = (
            RuntimePreflightStatus.PASSED
            if str(output_dir).startswith("data/")
            or str(output_dir) == "data"
            or output_dir.is_absolute()
            else RuntimePreflightStatus.WARNING
        )
        return _check(
            "runtime_storage",
            status,
            "Runtime storage is writable.",
            "Keep paper runtime state under ignored local data folders.",
            checked_at,
            (str(output_dir),),
        )

    def _recovery_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        try:
            recovered = self.persistence_store.recover()
        except Exception as error:
            return _check(
                "runtime_recovery",
                RuntimePreflightStatus.FAILED,
                "Persisted runtime state could not be recovered.",
                "Inspect local runtime JSON/JSONL files before restarting.",
                checked_at,
                (str(error),),
            )
        return _check(
            "runtime_recovery",
            RuntimePreflightStatus.PASSED,
            "Persisted runtime state is readable.",
            "Review recovered orders/fills if restarting after an interruption.",
            checked_at,
            (
                f"submissions={len(recovered.submissions)}",
                f"fills={len(recovered.fills)}",
            ),
        )

    def _dashboard_bind_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        if self.dashboard_host not in _LOCAL_HOSTS:
            return _check(
                "dashboard_binding",
                RuntimePreflightStatus.FAILED,
                "Dashboard host is not local-only.",
                "Bind the operator dashboard to 127.0.0.1, localhost, or ::1.",
                checked_at,
                (self.dashboard_host,),
            )
        return _check(
            "dashboard_binding",
            RuntimePreflightStatus.PASSED,
            "Dashboard host is local-only.",
            "Keep operator controls off public network interfaces.",
            checked_at,
            (self.dashboard_host,),
        )

    def _schedule_check(self, checked_at: datetime) -> RuntimePreflightCheck:
        trade_time = self.config.trade_after_close_time
        learning_time = self.config.nightly_learning_time
        if trade_time < dt_time(hour=16):
            return _check(
                "runtime_schedule",
                RuntimePreflightStatus.FAILED,
                "Paper trading schedule is before the regular close.",
                "Keep strategy authority on the approved daily-close schedule.",
                checked_at,
                (f"trade_after_close_time={trade_time.isoformat()}",),
            )
        if learning_time <= trade_time:
            return _check(
                "runtime_schedule",
                RuntimePreflightStatus.FAILED,
                "Nightly learning is scheduled before or at paper trading time.",
                (
                    "Schedule learning after reports and after the daily-close trade "
                    "window."
                ),
                checked_at,
                (
                    f"trade_after_close_time={trade_time.isoformat()}",
                    f"nightly_learning_time={learning_time.isoformat()}",
                ),
            )
        return _check(
            "runtime_schedule",
            RuntimePreflightStatus.PASSED,
            "Trading and learning schedules preserve daily-close authority.",
            "Keep intraday monitoring separate from trading authority.",
            checked_at,
            (
                f"trade_after_close_time={trade_time.isoformat()}",
                f"nightly_learning_time={learning_time.isoformat()}",
            ),
        )


def render_preflight_text(report: RuntimePreflightReport) -> str:
    """Render a compact operator-facing preflight summary."""

    lines = [
        f"Preflight status: {report.status.value}",
        f"Can start: {'yes' if report.can_start else 'no'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run an offline preflight check for Alpaca paper runtime."""

    from trading_app.runtime.paper import AlwaysOnPaperRuntimeConfig

    parser = argparse.ArgumentParser(description="Preflight Alpaca paper runtime.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-credential-required", action="store_true")
    args = parser.parse_args(argv)

    symbols = parse_symbol_list(
        args.symbols,
        default=AlwaysOnPaperRuntimeConfig().symbols,
    )
    config = AlwaysOnPaperRuntimeConfig(
        symbols=symbols,
        feed=DataFeed(args.feed.upper()),
        output_dir=Path(args.output_dir),
    )
    report = AlpacaPaperRuntimePreflight(
        config=config,
        dashboard_host=args.dashboard_host,
        require_credentials=not args.no_credential_required,
    ).run()
    print(report.model_dump_json() if args.json else render_preflight_text(report))
    return 0 if report.can_start else 1


def _check(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    remediation: str,
    checked_at: datetime,
    evidence: tuple[str, ...] = (),
) -> RuntimePreflightCheck:
    return RuntimePreflightCheck(
        name=name,
        status=status,
        message=message,
        remediation=remediation,
        checked_at=checked_at,
        evidence=tuple(str(item) for item in evidence),
    )


def _summary(status: RuntimePreflightStatus, failures: int, warnings: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Preflight passed; Alpaca paper runtime may start."
    if status == RuntimePreflightStatus.WARNING:
        return (
            "Preflight passed with warnings; paper runtime may start, but review "
            "development-grade assumptions."
        )
    return (
        f"Preflight failed with {failures} failure(s) and {warnings} warning(s); "
        "do not start paper runtime yet."
    )


if __name__ == "__main__":
    raise SystemExit(main())
