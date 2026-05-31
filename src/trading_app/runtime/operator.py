"""Operator controls and alerts for the always-on paper runtime."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_app.runtime.models import (
    OperatorControlAction,
    OperatorControlRequest,
    OperatorControlResult,
    OperatorControlState,
    OperatorControlStatus,
    RuntimeAlert,
    RuntimeAlertCode,
    RuntimeEventSeverity,
    RuntimeSnapshot,
    RuntimeStatus,
)


class RuntimeControlCenter:
    """Apply local paper-runtime controls and keep a compact action history."""

    def __init__(
        self,
        *,
        state: OperatorControlState | None = None,
        history: tuple[OperatorControlResult, ...] = (),
    ) -> None:
        self._state = state or OperatorControlState(
            paused=False,
            paper_kill_switch_enabled=False,
            updated_at=datetime.now(tz=UTC),
            updated_by="system",
            reason="initialized",
        )
        self._history = list(history)

    @property
    def state(self) -> OperatorControlState:
        return self._state

    @property
    def history(self) -> tuple[OperatorControlResult, ...]:
        return tuple(self._history)

    @property
    def last_result(self) -> OperatorControlResult | None:
        return self._history[-1] if self._history else None

    def apply(self, request: OperatorControlRequest) -> OperatorControlResult:
        """Apply a validated control action."""

        update = {
            "updated_at": request.requested_at,
            "updated_by": request.requested_by,
            "reason": request.reason or request.action.value,
        }
        message = "Control action accepted."

        if request.action == OperatorControlAction.PAUSE_RUNTIME:
            self._state = self._state.model_copy(update={**update, "paused": True})
            message = "Paper trading is paused; monitoring remains active."
        elif request.action == OperatorControlAction.RESUME_RUNTIME:
            self._state = self._state.model_copy(update={**update, "paused": False})
            message = "Paper trading schedule is resumed."
        elif request.action == OperatorControlAction.ENABLE_PAPER_KILL_SWITCH:
            self._state = self._state.model_copy(
                update={**update, "paper_kill_switch_enabled": True}
            )
            message = "Paper kill switch is enabled; new paper orders are blocked."
        elif request.action == OperatorControlAction.DISABLE_PAPER_KILL_SWITCH:
            self._state = self._state.model_copy(
                update={**update, "paper_kill_switch_enabled": False}
            )
            message = "Paper kill switch is disabled."
        elif request.action in {
            OperatorControlAction.FORCE_RECONCILIATION,
            OperatorControlAction.GENERATE_REPORT,
        }:
            self._state = self._state.model_copy(update=update)

        result = OperatorControlResult(
            request=request,
            status=OperatorControlStatus.ACCEPTED,
            message=message,
            control_state=self._state,
        )
        self._history.append(result)
        return result


class RuntimeAlertEngine:
    """Convert runtime evidence into dashboard-ready operator alerts."""

    def evaluate(
        self,
        snapshot: RuntimeSnapshot,
        *,
        control_state: OperatorControlState | None = None,
    ) -> tuple[RuntimeAlert, ...]:
        active_control_state = control_state or snapshot.control_state
        alerts: list[RuntimeAlert] = []
        as_of = snapshot.as_of

        if snapshot.status == RuntimeStatus.BLOCKED:
            alerts.append(
                _alert(
                    "runtime-status-blocked",
                    as_of,
                    RuntimeEventSeverity.ERROR,
                    RuntimeAlertCode.RUNTIME_BLOCKED,
                    "Runtime blocked",
                    "The paper runtime is blocked and needs operator review.",
                )
            )
        elif snapshot.status == RuntimeStatus.DEGRADED:
            alerts.append(
                _alert(
                    "runtime-status-degraded",
                    as_of,
                    RuntimeEventSeverity.WARNING,
                    RuntimeAlertCode.RUNTIME_DEGRADED,
                    "Runtime degraded",
                    (
                        "The paper runtime is still alive, but one or more checks "
                        "degraded."
                    ),
                )
            )

        if active_control_state and active_control_state.paused:
            alerts.append(
                _alert(
                    "operator-paused",
                    as_of,
                    RuntimeEventSeverity.INFO,
                    RuntimeAlertCode.OPERATOR_PAUSED,
                    "Runtime paused",
                    "Monitoring continues, but scheduled paper orders are paused.",
                    (active_control_state.updated_by, active_control_state.reason),
                )
            )

        if active_control_state and active_control_state.paper_kill_switch_enabled:
            alerts.append(
                _alert(
                    "paper-kill-switch-enabled",
                    as_of,
                    RuntimeEventSeverity.WARNING,
                    RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED,
                    "Paper kill switch enabled",
                    "New Alpaca paper orders are blocked by operator control.",
                    (active_control_state.updated_by, active_control_state.reason),
                )
            )

        latest_prices = snapshot.latest_prices
        if latest_prices is None:
            alerts.append(
                _alert(
                    "market-data-unavailable",
                    as_of,
                    RuntimeEventSeverity.WARNING,
                    RuntimeAlertCode.MARKET_DATA_STALE,
                    "Latest prices unavailable",
                    "The runtime has no latest-price snapshot yet.",
                )
            )
        elif not latest_prices.all_fresh:
            evidence = (
                latest_prices.status.value,
                *latest_prices.missing_symbols,
            )
            alerts.append(
                _alert(
                    "market-data-stale-or-missing",
                    as_of,
                    RuntimeEventSeverity.WARNING,
                    RuntimeAlertCode.MARKET_DATA_STALE,
                    "Latest prices stale or missing",
                    "New paper orders are blocked until all required prices are fresh.",
                    evidence,
                )
            )

        paper_report = snapshot.paper_report
        if paper_report and not paper_report.reconciliation.reconciled:
            evidence = tuple(
                issue.message for issue in paper_report.reconciliation.issues
            )
            alerts.append(
                _alert(
                    "reconciliation-break",
                    as_of,
                    RuntimeEventSeverity.ERROR,
                    RuntimeAlertCode.RECONCILIATION_BREAK,
                    "Broker reconciliation issue",
                    "Internal paper ledger and broker-reported state do not match.",
                    evidence,
                )
            )
        if paper_report:
            for rejection in paper_report.risk_rejections[-5:]:
                alerts.append(
                    _alert(
                        f"risk-rejection-{rejection.order_id}-{rejection.rule.value}",
                        as_of,
                        RuntimeEventSeverity.WARNING,
                        RuntimeAlertCode.RISK_REJECTION,
                        "Risk rejected an order",
                        rejection.message,
                        (rejection.order_id, rejection.symbol, rejection.rule.value),
                    )
                )

        for event in snapshot.events[-10:]:
            if event.severity != RuntimeEventSeverity.ERROR:
                continue
            alerts.append(
                _alert(
                    f"runtime-error-{event.category}-{event.timestamp.isoformat()}",
                    as_of,
                    RuntimeEventSeverity.ERROR,
                    RuntimeAlertCode.RUNTIME_ERROR,
                    "Runtime error",
                    event.message,
                    (event.category, *event.evidence),
                )
            )

        return tuple(_dedupe_alerts(alerts))


def _alert(
    id: str,  # noqa: A002
    created_at: datetime,
    severity: RuntimeEventSeverity,
    code: RuntimeAlertCode,
    title: str,
    message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeAlert:
    return RuntimeAlert(
        id=id,
        created_at=created_at,
        severity=severity,
        code=code,
        title=title,
        message=message,
        evidence=tuple(item for item in evidence if item),
    )


def _dedupe_alerts(alerts: list[RuntimeAlert]) -> list[RuntimeAlert]:
    by_id: dict[str, RuntimeAlert] = {}
    for alert in alerts:
        by_id[alert.id] = alert
    return list(by_id.values())
