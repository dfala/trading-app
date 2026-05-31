"""Runtime health and incident evaluation."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from trading_app.runtime.models import (
    RuntimeAlertCode,
    RuntimeEventSeverity,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeIncident,
    RuntimeSnapshot,
)

_STATUS_RANK = {
    RuntimeHealthStatus.HEALTHY: 0,
    RuntimeHealthStatus.WATCH: 1,
    RuntimeHealthStatus.DEGRADED: 2,
    RuntimeHealthStatus.CRITICAL: 3,
}


class RuntimeHealthEngine:
    """Evaluate runtime health from the latest snapshot evidence."""

    def __init__(
        self,
        *,
        max_cycle_age: timedelta = timedelta(minutes=30),
    ) -> None:
        self.max_cycle_age = max_cycle_age

    def evaluate(self, snapshot: RuntimeSnapshot) -> RuntimeHealthReport:
        checks = (
            self._heartbeat_check(snapshot),
            self._market_data_check(snapshot),
            self._broker_sync_check(snapshot),
            self._reconciliation_check(snapshot),
            self._operator_control_check(snapshot),
            self._alerts_check(snapshot),
            self._daily_report_check(snapshot),
            self._nightly_learning_check(snapshot),
        )
        status = _highest_status(check.status for check in checks)
        incidents = self._incidents(snapshot, checks)
        return RuntimeHealthReport(
            as_of=snapshot.as_of,
            status=status,
            summary=_summary(status, checks, incidents),
            next_action=_next_action(status, incidents),
            checks=checks,
            incidents=incidents,
        )

    def _heartbeat_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if snapshot.last_cycle is None:
            return _check(
                snapshot,
                "runtime_loop",
                RuntimeHealthStatus.WATCH,
                "Runtime is waiting for its first completed cycle.",
            )
        age = snapshot.as_of - snapshot.last_cycle.as_of
        if age > self.max_cycle_age:
            return _check(
                snapshot,
                "runtime_loop",
                RuntimeHealthStatus.CRITICAL,
                "Runtime heartbeat is stale.",
                (f"age_seconds={int(age.total_seconds())}",),
            )
        return _check(
            snapshot,
            "runtime_loop",
            RuntimeHealthStatus.HEALTHY,
            "Runtime heartbeat is fresh.",
            (f"age_seconds={int(age.total_seconds())}",),
        )

    def _market_data_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if snapshot.latest_prices is None:
            status = (
                RuntimeHealthStatus.WATCH
                if snapshot.last_cycle is None
                else RuntimeHealthStatus.DEGRADED
            )
            return _check(
                snapshot,
                "market_data",
                status,
                "Latest price snapshot is not available yet.",
            )
        if snapshot.latest_prices.all_fresh:
            return _check(
                snapshot,
                "market_data",
                RuntimeHealthStatus.HEALTHY,
                "Latest prices are fresh.",
                (snapshot.latest_prices.status.value,),
            )
        return _check(
            snapshot,
            "market_data",
            RuntimeHealthStatus.DEGRADED,
            "Latest prices are stale or missing.",
            (
                snapshot.latest_prices.status.value,
                *snapshot.latest_prices.missing_symbols,
            ),
        )

    def _broker_sync_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if snapshot.last_cycle is None:
            return _check(
                snapshot,
                "broker_sync",
                RuntimeHealthStatus.WATCH,
                "Broker sync is waiting for the first runtime cycle.",
            )
        if snapshot.last_cycle.broker_synced:
            return _check(
                snapshot,
                "broker_sync",
                RuntimeHealthStatus.HEALTHY,
                "Broker sync completed in the latest cycle.",
            )
        return _check(
            snapshot,
            "broker_sync",
            RuntimeHealthStatus.CRITICAL,
            "Broker sync did not complete in the latest cycle.",
        )

    def _reconciliation_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        report = snapshot.paper_report
        if report is None:
            return _check(
                snapshot,
                "reconciliation",
                RuntimeHealthStatus.WATCH,
                "Reconciliation is waiting for paper portfolio state.",
            )
        if report.reconciliation.reconciled:
            return _check(
                snapshot,
                "reconciliation",
                RuntimeHealthStatus.HEALTHY,
                "Broker and internal ledger reconciliation is clean.",
            )
        evidence = tuple(issue.message for issue in report.reconciliation.issues)
        return _check(
            snapshot,
            "reconciliation",
            RuntimeHealthStatus.CRITICAL,
            "Broker and internal ledger reconciliation is not clean.",
            evidence,
        )

    def _operator_control_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        state = snapshot.control_state
        if state is None:
            return _check(
                snapshot,
                "operator_controls",
                RuntimeHealthStatus.WATCH,
                "Operator control state is not available yet.",
            )
        if state.paper_kill_switch_enabled:
            return _check(
                snapshot,
                "operator_controls",
                RuntimeHealthStatus.DEGRADED,
                "Paper kill switch is enabled.",
                (state.updated_by, state.reason),
            )
        if state.paused:
            return _check(
                snapshot,
                "operator_controls",
                RuntimeHealthStatus.WATCH,
                "Runtime is intentionally paused by the operator.",
                (state.updated_by, state.reason),
            )
        return _check(
            snapshot,
            "operator_controls",
            RuntimeHealthStatus.HEALTHY,
            "Operator controls allow scheduled paper trading.",
        )

    def _alerts_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if any(
            alert.severity == RuntimeEventSeverity.ERROR for alert in snapshot.alerts
        ):
            return _check(
                snapshot,
                "alerts",
                RuntimeHealthStatus.CRITICAL,
                "Critical runtime alerts are active.",
                tuple(alert.code.value for alert in snapshot.alerts),
            )
        if any(
            alert.severity == RuntimeEventSeverity.WARNING for alert in snapshot.alerts
        ):
            return _check(
                snapshot,
                "alerts",
                RuntimeHealthStatus.DEGRADED,
                "Warning runtime alerts are active.",
                tuple(alert.code.value for alert in snapshot.alerts),
            )
        if snapshot.alerts:
            return _check(
                snapshot,
                "alerts",
                RuntimeHealthStatus.WATCH,
                "Informational runtime alerts are active.",
                tuple(alert.code.value for alert in snapshot.alerts),
            )
        return _check(
            snapshot,
            "alerts",
            RuntimeHealthStatus.HEALTHY,
            "No active runtime alerts.",
        )

    def _daily_report_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if snapshot.daily_report is None:
            return _check(
                snapshot,
                "daily_report",
                RuntimeHealthStatus.WATCH,
                "Daily report has not been built yet.",
            )
        evidence = (f"trading_day={snapshot.daily_report.trading_day.isoformat()}",)
        return _check(
            snapshot,
            "daily_report",
            RuntimeHealthStatus.HEALTHY,
            "Daily report state is available.",
            evidence,
        )

    def _nightly_learning_check(self, snapshot: RuntimeSnapshot) -> RuntimeHealthCheck:
        if snapshot.nightly_learning is None:
            return _check(
                snapshot,
                "nightly_learning",
                RuntimeHealthStatus.HEALTHY,
                "Nightly learning has no failure evidence.",
            )
        if snapshot.nightly_learning.active_model_unchanged:
            return _check(
                snapshot,
                "nightly_learning",
                RuntimeHealthStatus.HEALTHY,
                "Nightly learning completed without mutating the active model.",
                (snapshot.nightly_learning.id,),
            )
        return _check(
            snapshot,
            "nightly_learning",
            RuntimeHealthStatus.DEGRADED,
            "Nightly learning changed active model state unexpectedly.",
            (snapshot.nightly_learning.id,),
        )

    def _incidents(
        self,
        snapshot: RuntimeSnapshot,
        checks: tuple[RuntimeHealthCheck, ...],
    ) -> tuple[RuntimeIncident, ...]:
        incidents = [_incident_from_check(snapshot, check) for check in checks]
        incidents = [incident for incident in incidents if incident is not None]
        for alert in snapshot.alerts:
            if alert.code in {
                RuntimeAlertCode.RUNTIME_BLOCKED,
                RuntimeAlertCode.RUNTIME_ERROR,
                RuntimeAlertCode.RECONCILIATION_BREAK,
                RuntimeAlertCode.MARKET_DATA_STALE,
                RuntimeAlertCode.RISK_REJECTION,
                RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED,
                RuntimeAlertCode.OPERATOR_PAUSED,
            }:
                incidents.append(
                    RuntimeIncident(
                        id=f"alert-{alert.code.value}",
                        opened_at=alert.created_at,
                        status=_status_from_alert(alert.severity),
                        title=alert.title,
                        summary=alert.message,
                        suggested_action=_suggested_action_for_alert(alert.code),
                        evidence=alert.evidence,
                    )
                )
        return tuple(_dedupe_incidents(incidents))


def render_health_markdown_report(report: RuntimeHealthReport) -> str:
    """Render runtime health and incidents as a reviewable operator report."""

    lines = [
        "# Runtime Health Incident Review",
        "",
        "> Alpaca paper mode only. This report does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Checked at: `{report.as_of.isoformat()}`",
        f"- Open incidents: `{len(report.incidents)}`",
        f"- Next action: {report.next_action}",
        "",
        report.summary,
        "",
        "## Health Checks",
        "",
        "| Check | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        lines.append(
            "| "
            f"{_table_text(check.name)} | "
            f"{_table_text(check.status.value)} | "
            f"{_table_text(check.message)} | "
            f"{_table_text(', '.join(check.evidence) or '-')} |"
        )

    lines.extend(
        [
            "",
            "## Incident Command",
            "",
        ]
    )
    if report.incidents:
        lines.extend(
            [
                "| Incident | Status | Summary | Suggested Action | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for incident in report.incidents:
            lines.append(
                "| "
                f"{_table_text(incident.title)} | "
                f"{_table_text(incident.status.value)} | "
                f"{_table_text(incident.summary)} | "
                f"{_table_text(incident.suggested_action)} | "
                f"{_table_text(', '.join(incident.evidence) or '-')} |"
            )
    else:
        lines.append("No open incidents were detected.")

    lines.extend(
        [
            "",
            "## Paper Safety Boundary",
            "",
            "- Do not submit new paper orders while critical incidents are open.",
            "- Do not interpret a healthy paper report as live-money readiness.",
            "- Keep dashboard controls local-only and preserve all incident evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def write_health_markdown_report(
    report: RuntimeHealthReport,
    reports_dir: Path | str,
) -> Path:
    """Write a runtime health incident review report and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"health-report-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_health_markdown_report(report), encoding="utf-8")
    return path


def _check(
    snapshot: RuntimeSnapshot,
    name: str,
    status: RuntimeHealthStatus,
    message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeHealthCheck:
    return RuntimeHealthCheck(
        name=name,
        status=status,
        message=message,
        checked_at=snapshot.as_of,
        evidence=tuple(item for item in evidence if item),
    )


def _incident_from_check(
    snapshot: RuntimeSnapshot, check: RuntimeHealthCheck
) -> RuntimeIncident | None:
    if check.status == RuntimeHealthStatus.HEALTHY:
        return None
    if check.status == RuntimeHealthStatus.WATCH and check.name not in {
        "runtime_loop",
        "operator_controls",
    }:
        return None
    return RuntimeIncident(
        id=f"check-{check.name}",
        opened_at=snapshot.as_of,
        status=check.status,
        title=check.name.replace("_", " ").title(),
        summary=check.message,
        suggested_action=_suggested_action_for_check(check),
        evidence=check.evidence,
    )


def _highest_status(statuses) -> RuntimeHealthStatus:
    return max(statuses, key=lambda status: _STATUS_RANK[status])


def _status_from_alert(severity: RuntimeEventSeverity) -> RuntimeHealthStatus:
    if severity == RuntimeEventSeverity.ERROR:
        return RuntimeHealthStatus.CRITICAL
    if severity == RuntimeEventSeverity.WARNING:
        return RuntimeHealthStatus.DEGRADED
    return RuntimeHealthStatus.WATCH


def _dedupe_incidents(incidents: list[RuntimeIncident]) -> list[RuntimeIncident]:
    by_id: dict[str, RuntimeIncident] = {}
    for incident in incidents:
        current = by_id.get(incident.id)
        if (
            current is None
            or _STATUS_RANK[incident.status] > _STATUS_RANK[current.status]
        ):
            by_id[incident.id] = incident
    return list(by_id.values())


def _summary(
    status: RuntimeHealthStatus,
    checks: tuple[RuntimeHealthCheck, ...],
    incidents: tuple[RuntimeIncident, ...],
) -> str:
    unhealthy = sum(
        1 for check in checks if check.status != RuntimeHealthStatus.HEALTHY
    )
    if status == RuntimeHealthStatus.HEALTHY:
        return "All runtime health checks are healthy."
    return (
        f"{unhealthy} health check(s) need attention; "
        f"{len(incidents)} incident(s) are open."
    )


def _next_action(
    status: RuntimeHealthStatus,
    incidents: tuple[RuntimeIncident, ...],
) -> str:
    if not incidents:
        return "Continue monitoring the Alpaca paper runtime."
    if status == RuntimeHealthStatus.CRITICAL:
        return "Review critical incidents before allowing new paper orders."
    if status == RuntimeHealthStatus.DEGRADED:
        return "Review degraded incidents before trusting new paper signals."
    return "Review watch items when convenient."


def _suggested_action_for_check(check: RuntimeHealthCheck) -> str:
    if check.name == "runtime_loop":
        return "Confirm the always-on runtime process is still cycling."
    if check.name == "market_data":
        return "Check Alpaca market data freshness before paper trading."
    if check.name == "broker_sync":
        return "Check Alpaca paper broker connectivity and order polling."
    if check.name == "reconciliation":
        return "Force reconciliation and review ledger versus broker differences."
    if check.name == "operator_controls":
        return "Confirm the pause or paper kill switch reflects current intent."
    if check.name == "alerts":
        return "Open the Runtime Alerts panel and review active alerts."
    return "Review the health check evidence."


def _suggested_action_for_alert(code: RuntimeAlertCode) -> str:
    if code == RuntimeAlertCode.RECONCILIATION_BREAK:
        return "Do not submit paper orders until reconciliation is clean."
    if code == RuntimeAlertCode.MARKET_DATA_STALE:
        return "Wait for fresh prices or investigate the Alpaca data feed."
    if code == RuntimeAlertCode.RISK_REJECTION:
        return "Review the rejected order and risk rule before changing strategy."
    if code == RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED:
        return "Leave the kill switch on unless paper trading should resume."
    if code == RuntimeAlertCode.OPERATOR_PAUSED:
        return "Resume only when scheduled paper trading should continue."
    return "Review runtime logs and alerts before proceeding."


def _timestamp_id(value) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _table_text(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
