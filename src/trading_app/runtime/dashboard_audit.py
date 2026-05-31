"""Dashboard consistency audit for persisted paper runtime state."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.runtime.acceptance import render_final_acceptance_markdown
from trading_app.runtime.audit_coverage import (
    artifact_integrity_coverage_gap,
    credentialed_session_coverage_gap,
    evidence_bundle_coverage_gap,
    final_acceptance_coverage_gap,
    functional_completion_coverage_gap,
)
from trading_app.runtime.completion import render_completion_audit_markdown
from trading_app.runtime.evidence import render_evidence_bundle_markdown
from trading_app.runtime.integrity import render_artifact_integrity_markdown
from trading_app.runtime.models import (
    RuntimeDashboardConsistencyCheck,
    RuntimeDashboardConsistencyReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.session_proof import render_credentialed_session_markdown
from trading_app.schemas import OrderStatus


class RuntimeDashboardConsistencyAuditor:
    """Compare latest dashboard and runtime snapshots."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        persist_report: bool = True,
        max_snapshot_age: timedelta | None = timedelta(minutes=15),
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.persist_report = persist_report
        self.max_snapshot_age = max_snapshot_age

    def audit(
        self, *, as_of: datetime | None = None
    ) -> RuntimeDashboardConsistencyReport:
        now = as_of or datetime.now(tz=UTC)
        runtime = _read_model(
            self.store.state_dir / "latest-runtime-snapshot.json",
            RuntimeSnapshot,
        )
        dashboard = _read_model(
            self.store.state_dir / "latest-dashboard-snapshot.json",
            OperatorDashboardSnapshot,
        )
        checks = tuple(
            _checks(runtime, dashboard, self.store, now, self.max_snapshot_age)
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
        report = RuntimeDashboardConsistencyReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            checks=checks,
            summary=_summary(status, failures, warnings),
        )
        if self.persist_report:
            markdown_path = write_dashboard_consistency_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_dashboard_consistency_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_dashboard_consistency_text(
    report: RuntimeDashboardConsistencyReport,
) -> str:
    """Render compact dashboard consistency status."""

    lines = [
        f"Dashboard consistency status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
    return "\n".join(lines)


def render_dashboard_consistency_markdown(
    report: RuntimeDashboardConsistencyReport,
) -> str:
    """Render dashboard consistency audit Markdown."""

    lines = [
        "# Dashboard Consistency Audit",
        "",
        (
            "> Paper trading only. This audit compares persisted dashboard and "
            "runtime state."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        "",
        report.summary,
        "",
        "## Checks",
        "",
        "| Check | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        evidence = "<br>".join(check.evidence) if check.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(check.name)} | "
            f"{check.status.value} | "
            f"{_escape_table(check.message)} | "
            f"{_escape_table(evidence)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_dashboard_consistency_markdown_report(
    report: RuntimeDashboardConsistencyReport,
    reports_dir: Path | str,
) -> Path:
    """Write dashboard consistency Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"dashboard-consistency-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_dashboard_consistency_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit persisted dashboard snapshot consistency."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--max-snapshot-age-seconds", type=float, default=900)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeDashboardConsistencyAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
        max_snapshot_age=timedelta(seconds=args.max_snapshot_age_seconds),
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_dashboard_consistency_text(report)
    )
    return 0 if report.passed else 1


def _checks(
    runtime: RuntimeSnapshot | None,
    dashboard: OperatorDashboardSnapshot | None,
    store: RuntimePersistenceStore,
    as_of: datetime,
    max_snapshot_age: timedelta | None,
) -> list[RuntimeDashboardConsistencyCheck]:
    checks = [
        _check(
            "runtime_snapshot_present",
            runtime is not None,
            "Latest runtime snapshot is present.",
            "Latest runtime snapshot is missing.",
        ),
        _check(
            "dashboard_snapshot_present",
            dashboard is not None,
            "Latest dashboard snapshot is present.",
            "Latest dashboard snapshot is missing.",
        ),
    ]
    if runtime is None or dashboard is None:
        return checks

    checks.append(_freshness_check(runtime, dashboard, as_of, max_snapshot_age))

    paper_report = runtime.paper_report
    daily_report = runtime.daily_report
    embedded_runtime = dashboard.runtime_state
    checks.extend(
        (
            _check(
                "runtime_paper_report_present",
                paper_report is not None,
                "Runtime snapshot includes a paper portfolio report.",
                "Runtime snapshot is missing a paper portfolio report.",
            ),
            _check(
                "runtime_daily_report_present",
                daily_report is not None,
                "Runtime snapshot includes a daily report.",
                "Runtime snapshot is missing a daily report.",
            ),
        )
    )
    if paper_report is None or daily_report is None:
        return checks

    statement_ok, statement_evidence = _statement_matches_store(dashboard, store)
    completion_ok, completion_evidence = _completion_matches_store(dashboard, store)
    evidence_bundle_ok, evidence_bundle_evidence = _evidence_bundle_matches_store(store)
    artifact_integrity_ok, artifact_integrity_evidence = (
        _artifact_integrity_matches_store(store)
    )
    credentialed_session_ok, credentialed_session_evidence = (
        _credentialed_session_matches_store(store)
    )
    final_acceptance_ok, final_acceptance_evidence = _final_acceptance_matches_store(
        dashboard,
        store,
    )
    checks.extend(
        (
            _check(
                "paper_mode",
                runtime.mode == "Alpaca Paper" and dashboard.mode == "Alpaca Paper",
                "Runtime and dashboard are both Alpaca Paper.",
                "Runtime and dashboard modes do not both show Alpaca Paper.",
                (f"runtime={runtime.mode}", f"dashboard={dashboard.mode}"),
            ),
            _check(
                "broker_provider",
                dashboard.broker == paper_report.broker_portfolio.provider,
                "Dashboard broker matches runtime paper broker provider.",
                "Dashboard broker does not match runtime paper broker provider.",
                (
                    f"dashboard_broker={dashboard.broker}",
                    f"runtime_broker={paper_report.broker_portfolio.provider}",
                ),
            ),
            _check(
                "embedded_runtime_state",
                _field(embedded_runtime, "mode") == runtime.mode
                and _field(embedded_runtime, "active_model_key")
                == runtime.active_model_key,
                "Dashboard embeds the latest runtime mode and active model.",
                "Dashboard embedded runtime state is missing or stale.",
                (
                    f"embedded_mode={_field(embedded_runtime, 'mode', 'missing')}",
                    (
                        "embedded_active_model="
                        f"{_field(embedded_runtime, 'active_model_key', 'missing')}"
                    ),
                ),
            ),
            _check(
                "snapshot_timestamp",
                _same_timestamp(dashboard.generated_at, runtime.as_of)
                and _same_timestamp(
                    _field(embedded_runtime, "as_of"),
                    runtime.as_of,
                ),
                "Dashboard timestamp matches latest runtime snapshot.",
                "Dashboard timestamp does not match latest runtime snapshot.",
                (
                    f"dashboard_generated_at={dashboard.generated_at.isoformat()}",
                    f"runtime_as_of={runtime.as_of.isoformat()}",
                    (f"embedded_as_of={_field(embedded_runtime, 'as_of', 'missing')}"),
                ),
            ),
            _check(
                "cash",
                _decimal_equal(dashboard.cash, daily_report.pnl_report.ending_cash),
                "Dashboard cash matches runtime daily report.",
                "Dashboard cash does not match runtime daily report.",
                (
                    f"dashboard_cash={dashboard.cash}",
                    f"runtime_cash={daily_report.pnl_report.ending_cash}",
                ),
            ),
            _check(
                "estimated_equity",
                _decimal_equal(
                    dashboard.estimated_equity,
                    daily_report.pnl_report.estimated_equity,
                ),
                "Dashboard estimated equity matches runtime daily report.",
                "Dashboard estimated equity does not match runtime daily report.",
                (
                    f"dashboard_equity={dashboard.estimated_equity}",
                    (f"runtime_equity={daily_report.pnl_report.estimated_equity}"),
                ),
            ),
            _check(
                "realized_pnl",
                _decimal_equal(
                    dashboard.realized_pnl,
                    daily_report.pnl_report.realized_pnl,
                ),
                "Dashboard realized P&L matches runtime daily report.",
                "Dashboard realized P&L does not match runtime daily report.",
                (
                    f"dashboard_realized_pnl={dashboard.realized_pnl}",
                    (f"runtime_realized_pnl={daily_report.pnl_report.realized_pnl}"),
                ),
            ),
            _check(
                "open_orders",
                dashboard.open_orders == _open_order_count(paper_report),
                "Dashboard open-order count matches runtime paper report.",
                "Dashboard open-order count does not match runtime paper report.",
                (
                    f"dashboard_open_orders={dashboard.open_orders}",
                    f"runtime_open_orders={_open_order_count(paper_report)}",
                ),
            ),
            _check(
                "recent_fills",
                tuple(fill.id for fill in dashboard.recent_fills)
                == tuple(fill.id for fill in paper_report.fills),
                "Dashboard recent fills match runtime paper report.",
                "Dashboard recent fills do not match runtime paper report.",
                (
                    f"dashboard_fills={len(dashboard.recent_fills)}",
                    f"runtime_fills={len(paper_report.fills)}",
                ),
            ),
            _check(
                "positions",
                _positions_equal(
                    dashboard.paper_report.ledger_snapshot.positions,
                    paper_report.ledger_snapshot.positions,
                ),
                "Dashboard positions match runtime paper report.",
                "Dashboard positions do not match runtime paper report.",
                (
                    (
                        "dashboard_positions="
                        f"{len(dashboard.paper_report.ledger_snapshot.positions)}"
                    ),
                    (
                        "runtime_positions="
                        f"{len(paper_report.ledger_snapshot.positions)}"
                    ),
                ),
            ),
            _check(
                "active_model",
                dashboard.active_strategy_definition is not None
                and (
                    f"{dashboard.active_strategy_definition.strategy_id}:"
                    f"{dashboard.active_strategy_definition.version}"
                )
                == runtime.active_model_key,
                "Dashboard active model matches runtime active model.",
                "Dashboard active model is missing or does not match runtime.",
                (f"runtime_active_model={runtime.active_model_key}",),
            ),
            _check(
                "data_quality",
                dashboard.daily_report.data_quality_report is not None
                and daily_report.data_quality_report is not None
                and dashboard.daily_report.data_quality_report.status
                == daily_report.data_quality_report.status,
                "Dashboard data-quality evidence matches runtime report.",
                "Dashboard data-quality evidence is missing or inconsistent.",
            ),
            _check(
                "operator_controls",
                _control_state_matches(dashboard.control_state, runtime.control_state),
                "Dashboard operator controls match runtime control state.",
                "Dashboard operator controls are missing or stale.",
                _control_state_evidence(
                    dashboard.control_state,
                    runtime.control_state,
                ),
            ),
            _check(
                "runtime_alerts",
                _alerts_match(dashboard.alerts, runtime.alerts),
                "Dashboard alerts match runtime alerts.",
                "Dashboard alerts are missing or stale.",
                (
                    f"dashboard_alerts={len(dashboard.alerts)}",
                    f"runtime_alerts={len(runtime.alerts)}",
                ),
            ),
            _check(
                "runtime_health",
                _health_matches(dashboard.health_report, runtime.health_report),
                "Dashboard health state matches runtime health.",
                "Dashboard health state is missing or stale.",
                (
                    f"dashboard_health={_status_value(dashboard.health_report)}",
                    f"runtime_health={_status_value(runtime.health_report)}",
                ),
            ),
            _check(
                "statement_review",
                statement_ok,
                "Dashboard statement review matches persisted statement evidence.",
                "Dashboard statement review is stale or inconsistent.",
                statement_evidence,
            ),
            _check(
                "completion_audit",
                completion_ok,
                "Dashboard completion audit matches persisted completion evidence.",
                "Dashboard completion audit is stale or inconsistent.",
                completion_evidence,
            ),
            _check(
                "evidence_bundle",
                evidence_bundle_ok,
                "Dashboard evidence bundle artifact is current.",
                "Dashboard evidence bundle artifact is stale or inconsistent.",
                evidence_bundle_evidence,
            ),
            _check(
                "artifact_integrity",
                artifact_integrity_ok,
                "Dashboard artifact-integrity artifact is current.",
                "Dashboard artifact-integrity artifact is stale or inconsistent.",
                artifact_integrity_evidence,
            ),
            _check(
                "credentialed_session",
                credentialed_session_ok,
                "Dashboard credentialed-session artifact is current.",
                "Dashboard credentialed-session artifact is stale or inconsistent.",
                credentialed_session_evidence,
            ),
            _check(
                "final_acceptance",
                final_acceptance_ok,
                "Dashboard final acceptance matches persisted signoff evidence.",
                "Dashboard final acceptance is stale or inconsistent.",
                final_acceptance_evidence,
            ),
        )
    )
    return checks


def _open_order_count(paper_report) -> int:
    return sum(
        1
        for status in paper_report.order_statuses
        if status.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
    )


def _statement_matches_store(
    dashboard: OperatorDashboardSnapshot,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_statement_reconciliation_report()
    if persisted is None:
        return (
            dashboard.statement_reconciliation is None,
            ("persisted_statement_reconciliation=missing",),
        )
    if dashboard.generated_at < persisted.as_of:
        return (
            True,
            (
                f"dashboard_generated_at={dashboard.generated_at.isoformat()}",
                f"statement_as_of={persisted.as_of.isoformat()}",
                "statement evidence was generated after this dashboard snapshot",
            ),
        )
    dashboard_report = dashboard.statement_reconciliation
    passed = (
        dashboard_report is not None
        and _field(dashboard_report, "reconciled") == persisted.reconciled
        and _field(_field(dashboard_report, "statement", {}), "statement_id")
        == persisted.statement.statement_id
    )
    return (
        passed,
        (
            f"persisted_statement={persisted.statement.statement_id}",
            f"persisted_reconciled={persisted.reconciled}",
        ),
    )


def _artifact_integrity_matches_store(
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_artifact_integrity_report()
    if persisted is None:
        return True, ("persisted_artifact_integrity=missing",)
    coverage_gap = artifact_integrity_coverage_gap(persisted)
    if coverage_gap:
        return (
            False,
            (
                f"persisted_artifact_integrity_passed={persisted.passed}",
                f"persisted_hashed={persisted.hashed_count}",
                *coverage_gap,
            ),
        )
    artifact_ok, artifact_evidence = _artifact_integrity_artifact_current(
        persisted,
        store,
    )
    if not artifact_ok:
        return (
            False,
            (
                f"persisted_artifact_integrity_passed={persisted.passed}",
                f"persisted_hashed={persisted.hashed_count}",
                *artifact_evidence,
            ),
        )
    return (
        True,
        (
            f"persisted_artifact_integrity_passed={persisted.passed}",
            f"persisted_hashed={persisted.hashed_count}",
        ),
    )


def _artifact_integrity_artifact_current(
    persisted,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    state_path = store.state_dir / "latest-artifact-integrity-report.json"
    pointer_path = store.read_artifact_integrity_report_path()
    markdown_path = Path(persisted.markdown_path) if persisted.markdown_path else None
    missing: list[str] = []
    mismatches: list[str] = []

    if not state_path.exists():
        missing.append("artifact_integrity_state")
    if pointer_path is None:
        missing.append("artifact_integrity_path_pointer")
    if markdown_path is None:
        missing.append("artifact_integrity_markdown_path")
    elif pointer_path is not None and str(pointer_path) != str(markdown_path):
        mismatches.append("artifact_integrity_markdown_path")

    if markdown_path is not None:
        if not markdown_path.exists():
            missing.append("artifact_integrity_markdown")
        else:
            expected = render_artifact_integrity_markdown(persisted)
            if markdown_path.read_text(encoding="utf-8") != expected:
                mismatches.append("artifact_integrity_markdown")

    passed = not missing and not mismatches
    return passed, (
        f"state_path={state_path}",
        f"pointer_path={pointer_path or 'missing'}",
        f"markdown_path={markdown_path or 'missing'}",
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _credentialed_session_matches_store(
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_credentialed_session_report()
    if persisted is None:
        return True, ("persisted_credentialed_session=missing",)
    coverage_gap = credentialed_session_coverage_gap(persisted)
    if coverage_gap:
        return (
            False,
            (
                f"persisted_credentialed_session_passed={persisted.passed}",
                f"persisted_checks={len(persisted.checks)}",
                *coverage_gap,
            ),
        )
    artifact_ok, artifact_evidence = _credentialed_session_artifact_current(
        persisted,
        store,
    )
    if not artifact_ok:
        return (
            False,
            (
                f"persisted_credentialed_session_passed={persisted.passed}",
                f"persisted_checks={len(persisted.checks)}",
                *artifact_evidence,
            ),
        )
    return (
        True,
        (
            f"persisted_credentialed_session_passed={persisted.passed}",
            f"persisted_checks={len(persisted.checks)}",
        ),
    )


def _credentialed_session_artifact_current(
    persisted,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    state_path = store.state_dir / "latest-credentialed-session-report.json"
    pointer_path = store.read_credentialed_session_report_path()
    markdown_path = Path(persisted.markdown_path) if persisted.markdown_path else None
    missing: list[str] = []
    mismatches: list[str] = []

    if not state_path.exists():
        missing.append("credentialed_session_state")
    if pointer_path is None:
        missing.append("credentialed_session_path_pointer")
    if markdown_path is None:
        missing.append("credentialed_session_markdown_path")
    elif pointer_path is not None and str(pointer_path) != str(markdown_path):
        mismatches.append("credentialed_session_markdown_path")

    if markdown_path is not None:
        if not markdown_path.exists():
            missing.append("credentialed_session_markdown")
        else:
            expected = render_credentialed_session_markdown(persisted)
            if markdown_path.read_text(encoding="utf-8") != expected:
                mismatches.append("credentialed_session_markdown")

    passed = not missing and not mismatches
    return passed, (
        f"state_path={state_path}",
        f"pointer_path={pointer_path or 'missing'}",
        f"markdown_path={markdown_path or 'missing'}",
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _evidence_bundle_matches_store(
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_evidence_bundle_report()
    if persisted is None:
        return True, ("persisted_evidence_bundle=missing",)
    coverage_gap = evidence_bundle_coverage_gap(persisted)
    if coverage_gap:
        return (
            False,
            (
                f"persisted_evidence_bundle_ready={persisted.ready_for_operator_review}",
                f"persisted_passed={persisted.passed_count}",
                *coverage_gap,
            ),
        )
    artifact_ok, artifact_evidence = _evidence_bundle_artifact_current(
        persisted,
        store,
    )
    if not artifact_ok:
        return (
            False,
            (
                f"persisted_evidence_bundle_ready={persisted.ready_for_operator_review}",
                f"persisted_passed={persisted.passed_count}",
                *artifact_evidence,
            ),
        )
    return (
        True,
        (
            f"persisted_evidence_bundle_ready={persisted.ready_for_operator_review}",
            f"persisted_passed={persisted.passed_count}",
        ),
    )


def _evidence_bundle_artifact_current(
    persisted,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    state_path = store.state_dir / "latest-evidence-bundle-report.json"
    pointer_path = store.read_evidence_bundle_report_path()
    markdown_path = Path(persisted.markdown_path) if persisted.markdown_path else None
    missing: list[str] = []
    mismatches: list[str] = []

    if not state_path.exists():
        missing.append("evidence_bundle_state")
    if pointer_path is None:
        missing.append("evidence_bundle_path_pointer")
    if markdown_path is None:
        missing.append("evidence_bundle_markdown_path")
    elif pointer_path is not None and str(pointer_path) != str(markdown_path):
        mismatches.append("evidence_bundle_markdown_path")

    if markdown_path is not None:
        if not markdown_path.exists():
            missing.append("evidence_bundle_markdown")
        else:
            expected = render_evidence_bundle_markdown(persisted)
            if markdown_path.read_text(encoding="utf-8") != expected:
                mismatches.append("evidence_bundle_markdown")

    passed = not missing and not mismatches
    return passed, (
        f"state_path={state_path}",
        f"pointer_path={pointer_path or 'missing'}",
        f"markdown_path={markdown_path or 'missing'}",
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _completion_matches_store(
    dashboard: OperatorDashboardSnapshot,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_completion_audit_report()
    if persisted is None:
        return (
            dashboard.completion_audit is None,
            ("persisted_completion_audit=missing",),
        )
    coverage_gap = functional_completion_coverage_gap(persisted)
    if coverage_gap:
        return (
            False,
            (
                f"persisted_completion_passed={persisted.passed}",
                f"persisted_proven={persisted.proven_count}",
                *coverage_gap,
            ),
        )
    artifact_ok, artifact_evidence = _completion_audit_artifact_current(
        persisted,
        store,
    )
    if not artifact_ok:
        return (
            False,
            (
                f"persisted_completion_passed={persisted.passed}",
                f"persisted_proven={persisted.proven_count}",
                *artifact_evidence,
            ),
        )
    if dashboard.generated_at < persisted.as_of:
        return (
            True,
            (
                f"dashboard_generated_at={dashboard.generated_at.isoformat()}",
                f"completion_as_of={persisted.as_of.isoformat()}",
                "completion audit was generated after this dashboard snapshot",
            ),
        )
    dashboard_report = dashboard.completion_audit
    passed = (
        dashboard_report is not None
        and _field(dashboard_report, "passed") == persisted.passed
        and _field(dashboard_report, "proven_count") == persisted.proven_count
    )
    return (
        passed,
        (
            f"persisted_completion_passed={persisted.passed}",
            f"persisted_proven={persisted.proven_count}",
        ),
    )


def _completion_audit_artifact_current(
    persisted,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    state_path = store.state_dir / "latest-completion-audit-report.json"
    markdown_path = Path(persisted.markdown_path) if persisted.markdown_path else None
    missing: list[str] = []
    mismatches: list[str] = []

    if not state_path.exists():
        missing.append("completion_audit_state")
    if markdown_path is None:
        missing.append("completion_audit_markdown_path")
    elif not markdown_path.exists():
        missing.append("completion_audit_markdown")
    else:
        expected = render_completion_audit_markdown(persisted)
        if markdown_path.read_text(encoding="utf-8") != expected:
            mismatches.append("completion_audit_markdown")

    passed = not missing and not mismatches
    return passed, (
        f"state_path={state_path}",
        f"markdown_path={markdown_path or 'missing'}",
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _final_acceptance_matches_store(
    dashboard: OperatorDashboardSnapshot,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    persisted = store.read_final_acceptance_report()
    if persisted is None:
        return (
            dashboard.final_acceptance is None,
            ("persisted_final_acceptance=missing",),
        )
    coverage_gap = final_acceptance_coverage_gap(persisted)
    if coverage_gap:
        return (
            False,
            (
                f"persisted_final_acceptance={persisted.accepted_for_functional_paper_app}",
                f"persisted_final_acceptance_checks={len(persisted.checks)}",
                *coverage_gap,
            ),
        )
    artifact_ok, artifact_evidence = _final_acceptance_artifact_current(
        persisted,
        store,
    )
    if not artifact_ok:
        return (
            False,
            (
                f"persisted_final_acceptance={persisted.accepted_for_functional_paper_app}",
                f"persisted_final_acceptance_checks={len(persisted.checks)}",
                *artifact_evidence,
            ),
        )
    if dashboard.generated_at < persisted.as_of:
        return (
            True,
            (
                f"dashboard_generated_at={dashboard.generated_at.isoformat()}",
                f"final_acceptance_as_of={persisted.as_of.isoformat()}",
                "final acceptance was generated after this dashboard snapshot",
            ),
        )
    dashboard_report = dashboard.final_acceptance
    passed = (
        dashboard_report is not None
        and _field(dashboard_report, "accepted_for_functional_paper_app")
        == persisted.accepted_for_functional_paper_app
        and _status_value(dashboard_report) == persisted.status.value
        and len(_field(dashboard_report, "checks", ()) or ()) == len(persisted.checks)
    )
    return (
        passed,
        (
            f"persisted_final_acceptance={persisted.accepted_for_functional_paper_app}",
            f"persisted_final_acceptance_checks={len(persisted.checks)}",
        ),
    )


def _final_acceptance_artifact_current(
    persisted,
    store: RuntimePersistenceStore,
) -> tuple[bool, tuple[str, ...]]:
    state_path = store.state_dir / "latest-final-acceptance-report.json"
    pointer_path = store.read_final_acceptance_report_path()
    markdown_path = Path(persisted.markdown_path) if persisted.markdown_path else None
    missing: list[str] = []
    mismatches: list[str] = []

    if not state_path.exists():
        missing.append("final_acceptance_state")
    if pointer_path is None:
        missing.append("final_acceptance_path_pointer")
    if markdown_path is None:
        missing.append("final_acceptance_markdown_path")
    elif pointer_path is not None and str(pointer_path) != str(markdown_path):
        mismatches.append("final_acceptance_markdown_path")

    if markdown_path is not None:
        if not markdown_path.exists():
            missing.append("final_acceptance_markdown")
        else:
            expected = render_final_acceptance_markdown(persisted)
            if markdown_path.read_text(encoding="utf-8") != expected:
                mismatches.append("final_acceptance_markdown")

    passed = not missing and not mismatches
    return passed, (
        f"state_path={state_path}",
        f"pointer_path={pointer_path or 'missing'}",
        f"markdown_path={markdown_path or 'missing'}",
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _read_model(path: Path, model_type):
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeDashboardConsistencyCheck:
    return RuntimeDashboardConsistencyCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _freshness_check(
    runtime: RuntimeSnapshot,
    dashboard: OperatorDashboardSnapshot,
    as_of: datetime,
    max_snapshot_age: timedelta | None,
) -> RuntimeDashboardConsistencyCheck:
    if max_snapshot_age is None:
        return _check(
            "snapshot_freshness",
            True,
            "Dashboard snapshot freshness check is disabled.",
            "Dashboard snapshot freshness check is disabled.",
        )

    runtime_age = _age_seconds(as_of, runtime.as_of)
    dashboard_age = _age_seconds(as_of, dashboard.generated_at)
    allowed = max_snapshot_age.total_seconds()
    passed = (
        runtime_age is not None
        and dashboard_age is not None
        and 0 <= runtime_age <= allowed
        and 0 <= dashboard_age <= allowed
    )
    return _check(
        "snapshot_freshness",
        passed,
        "Dashboard and runtime snapshots are fresh for operator review.",
        "Dashboard or runtime snapshot is stale relative to audit time.",
        (
            f"runtime_age_seconds={_format_age(runtime_age)}",
            f"dashboard_age_seconds={_format_age(dashboard_age)}",
            f"allowed_seconds={allowed:.2f}",
        ),
    )


def _decimal_equal(left: Decimal, right: Decimal) -> bool:
    return Decimal(left) == Decimal(right)


def _positions_equal(left, right) -> bool:
    return _position_index(left) == _position_index(right)


def _control_state_matches(dashboard_state, runtime_state) -> bool:
    if dashboard_state is None or runtime_state is None:
        return False
    return (
        _field(dashboard_state, "paused") == _field(runtime_state, "paused")
        and _field(dashboard_state, "paper_kill_switch_enabled")
        == _field(runtime_state, "paper_kill_switch_enabled")
        and _same_timestamp(
            _field(dashboard_state, "updated_at"),
            _field(runtime_state, "updated_at"),
        )
        and _field(dashboard_state, "updated_by") == _field(runtime_state, "updated_by")
        and _field(dashboard_state, "reason") == _field(runtime_state, "reason")
    )


def _control_state_evidence(dashboard_state, runtime_state) -> tuple[str, ...]:
    return (
        f"dashboard_paused={_field(dashboard_state, 'paused', 'missing')}",
        f"runtime_paused={_field(runtime_state, 'paused', 'missing')}",
        (
            "dashboard_kill_switch="
            f"{_field(dashboard_state, 'paper_kill_switch_enabled', 'missing')}"
        ),
        (
            "runtime_kill_switch="
            f"{_field(runtime_state, 'paper_kill_switch_enabled', 'missing')}"
        ),
    )


def _alerts_match(dashboard_alerts, runtime_alerts) -> bool:
    dashboard_index = tuple(_alert_signature(alert) for alert in dashboard_alerts)
    runtime_index = tuple(_alert_signature(alert) for alert in runtime_alerts)
    return dashboard_index == runtime_index


def _alert_signature(alert) -> tuple[str, str, str]:
    return (
        _field(alert, "id", "missing"),
        _enum_value(_field(alert, "severity", "missing")),
        _enum_value(_field(alert, "code", "missing")),
    )


def _health_matches(dashboard_health, runtime_health) -> bool:
    if dashboard_health is None or runtime_health is None:
        return False
    return _status_value(dashboard_health) == _status_value(runtime_health)


def _status_value(report) -> str:
    status = _field(report, "status", "missing")
    return _enum_value(status)


def _enum_value(value) -> str:
    if isinstance(value, dict):
        return str(value.get("value", value))
    return str(getattr(value, "value", value))


def _position_index(positions) -> tuple[tuple[str, Decimal, Decimal], ...]:
    return tuple(
        sorted(
            (
                position.symbol,
                Decimal(position.quantity),
                Decimal(position.average_cost),
            )
            for position in positions
        )
    )


def _same_timestamp(left, right) -> bool:
    left_dt = _datetime_value(left)
    right_dt = _datetime_value(right)
    return left_dt is not None and right_dt is not None and left_dt == right_dt


def _datetime_value(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_seconds(as_of: datetime, value) -> float | None:
    timestamp = _datetime_value(value)
    if timestamp is None:
        return None
    return (as_of - timestamp).total_seconds()


def _format_age(value: float | None) -> str:
    return "missing" if value is None else f"{value:.2f}"


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    warnings: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Dashboard snapshot is consistent with latest runtime state."
    return (
        f"Dashboard consistency found {failures} failed check(s) and {warnings} "
        "warning check(s)."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
