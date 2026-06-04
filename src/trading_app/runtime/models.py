"""Runtime state models for always-on paper trading."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.learning import NightlyLearningRun
from trading_app.market_data import LatestPriceSnapshot
from trading_app.paper import PaperPortfolioReport
from trading_app.reporting import DailyTradingReport
from trading_app.schemas import OrderSide, PortfolioSnapshot, TradingModel


class RuntimeStatus(StrEnum):
    RUNNING = "running"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    STOPPED = "stopped"


class RuntimeEventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RuntimeEvent(TradingModel):
    timestamp: AwareDatetime
    severity: RuntimeEventSeverity
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class OperatorControlAction(StrEnum):
    PAUSE_RUNTIME = "pause_runtime"
    RESUME_RUNTIME = "resume_runtime"
    ENABLE_PAPER_KILL_SWITCH = "enable_paper_kill_switch"
    DISABLE_PAPER_KILL_SWITCH = "disable_paper_kill_switch"
    FORCE_RECONCILIATION = "force_reconciliation"
    GENERATE_REPORT = "generate_report"


class OperatorControlStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OperatorControlState(TradingModel):
    paused: bool = False
    paper_kill_switch_enabled: bool = False
    updated_at: AwareDatetime
    updated_by: str = Field(min_length=1)
    reason: str = ""


class OperatorControlRequest(TradingModel):
    action: OperatorControlAction
    requested_at: AwareDatetime
    requested_by: str = Field(default="local-operator", min_length=1)
    reason: str = ""


class OperatorControlResult(TradingModel):
    request: OperatorControlRequest
    status: OperatorControlStatus
    message: str = Field(min_length=1)
    control_state: OperatorControlState


class RuntimeAlertCode(StrEnum):
    RUNTIME_DEGRADED = "runtime_degraded"
    RUNTIME_BLOCKED = "runtime_blocked"
    MARKET_DATA_STALE = "market_data_stale"
    RECONCILIATION_BREAK = "reconciliation_break"
    RISK_REJECTION = "risk_rejection"
    PAPER_KILL_SWITCH_ENABLED = "paper_kill_switch_enabled"
    OPERATOR_PAUSED = "operator_paused"
    RUNTIME_ERROR = "runtime_error"


class RuntimeAlert(TradingModel):
    id: str = Field(min_length=1)
    created_at: AwareDatetime
    severity: RuntimeEventSeverity
    code: RuntimeAlertCode
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()
    resolved: bool = False


class ShadowOrderIntent(TradingModel):
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: Decimal
    estimated_price: Decimal
    estimated_notional: Decimal
    current_value: Decimal
    target_value: Decimal


class ShadowChallengerObservation(TradingModel):
    as_of: AwareDatetime
    model_key: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    authority: str = Field(default="shadow", min_length=1)
    latest_prices_fresh: bool
    broker_orders_submitted: bool = False
    targets: dict[str, Decimal]
    explanation: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    orders: tuple[ShadowOrderIntent, ...] = ()
    ledger_snapshot: PortfolioSnapshot
    estimated_equity: Decimal
    previous_estimated_equity: Decimal | None = None


class RuntimeHealthStatus(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class RuntimeHealthCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimeHealthStatus
    message: str = Field(min_length=1)
    checked_at: AwareDatetime
    evidence: tuple[str, ...] = ()


class RuntimeIncident(TradingModel):
    id: str = Field(min_length=1)
    opened_at: AwareDatetime
    status: RuntimeHealthStatus
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeHealthReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimeHealthStatus
    summary: str = Field(min_length=1)
    next_action: str = Field(min_length=1)
    checks: tuple[RuntimeHealthCheck, ...]
    incidents: tuple[RuntimeIncident, ...] = ()


class RuntimePreflightStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class FunctionalRequirementStatus(StrEnum):
    PROVEN = "proven"
    MISSING = "missing"
    FAILED = "failed"
    EXTERNAL_REQUIRED = "external_required"


class FunctionalRequirementEvidence(TradingModel):
    id: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    status: FunctionalRequirementStatus
    evidence: tuple[str, ...] = ()
    remediation: str = Field(min_length=1)


class FunctionalCompletionAuditReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    proven_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    external_required_count: int = Field(ge=0)
    requirements: tuple[FunctionalRequirementEvidence, ...]
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeEvidenceBundleItem(TradingModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    status: RuntimePreflightStatus
    required: bool = True
    summary: str = Field(min_length=1)
    path: str | None = None
    evidence: tuple[str, ...] = ()
    next_action: str = Field(min_length=1)


class RuntimeEvidenceBundleReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    ready_for_operator_review: bool
    output_dir: str = Field(min_length=1)
    items: tuple[RuntimeEvidenceBundleItem, ...]
    required_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    missing_required_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeDashboardConsistencyCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeDashboardConsistencyReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeDashboardConsistencyCheck, ...]
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeDashboardVisualCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeDashboardVisualReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeDashboardVisualCheck, ...]
    critical_surface_count: int = Field(ge=0)
    responsive_surface_count: int = Field(ge=0)
    failed_visual_scenarios: int = Field(ge=0)
    summary: str = Field(min_length=1)
    rendered_html_path: str | None = None
    markdown_path: str | None = None


class RuntimeEvidenceCoherenceCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeEvidenceCoherenceReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeEvidenceCoherenceCheck, ...]
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeArtifactIntegrityItem(TradingModel):
    label: str = Field(min_length=1)
    path: str = Field(min_length=1)
    required: bool = True
    exists: bool
    size_bytes: int = Field(default=0, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    hash_matches: bool | None = None


class RuntimeArtifactIntegrityReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    items: tuple[RuntimeArtifactIntegrityItem, ...]
    required_count: int = Field(ge=0)
    hashed_count: int = Field(ge=0)
    missing_required_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(default=0, ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeOperatorSignoffCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeOperatorSignoffReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    accepted_for_paper_review: bool
    output_dir: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    paper_account_id: str = Field(min_length=1)
    checks: tuple[RuntimeOperatorSignoffCheck, ...]
    confirmation_count: int = Field(ge=0)
    missing_confirmation_count: int = Field(ge=0)
    evidence_bundle_path: str | None = None
    credentialed_session_path: str | None = None
    completion_audit_path: str | None = None
    artifact_integrity_path: str | None = None
    notes: str = ""
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeFinalAcceptanceCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeFinalAcceptanceReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    accepted_for_functional_paper_app: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeFinalAcceptanceCheck, ...]
    signoff_path: str | None = None
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeRecoveryAuditCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeRecoveryAuditReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeRecoveryAuditCheck, ...]
    raw_submission_count: int = Field(ge=0)
    recovered_submission_count: int = Field(ge=0)
    raw_order_status_count: int = Field(ge=0)
    recovered_order_status_count: int = Field(ge=0)
    raw_fill_count: int = Field(ge=0)
    recovered_fill_count: int = Field(ge=0)
    duplicate_order_ids: tuple[str, ...] = ()
    duplicate_broker_order_ids: tuple[str, ...] = ()
    duplicate_fill_ids: tuple[str, ...] = ()
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeOperationsReadinessCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeOperationsReadinessReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    dashboard_url: str = Field(min_length=1)
    startup_command: str = Field(min_length=1)
    checks: tuple[RuntimeOperationsReadinessCheck, ...]
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeLifecycleDrillCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeLifecycleDrillReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    startup_command: str = Field(min_length=1)
    dashboard_url: str = Field(min_length=1)
    checks: tuple[RuntimeLifecycleDrillCheck, ...]
    persisted_control_actions: tuple[OperatorControlAction, ...] = ()
    operator_control_count: int = Field(ge=0)
    emergency_stop_confirmed: bool = False
    shutdown_procedure_documented: bool = False
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeCredentialedSessionCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeCredentialedSessionReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    validation_id: str | None = Field(default=None, min_length=1)
    session_started_at: AwareDatetime | None = None
    session_completed_at: AwareDatetime | None = None
    paper_account_id: str | None = Field(default=None, min_length=1)
    broker_providers: tuple[str, ...] = ()
    latest_price_sources: tuple[str, ...] = ()
    feed: str | None = Field(default=None, min_length=1)
    checks: tuple[RuntimeCredentialedSessionCheck, ...]
    reviewed_artifact_count: int = Field(ge=0)
    external_source_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeModelGovernanceCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeModelGovernanceReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    learning_run_id: str | None = Field(default=None, min_length=1)
    checks: tuple[RuntimeModelGovernanceCheck, ...]
    recommendation_count: int = Field(ge=0)
    unreviewed_authority_increases: tuple[str, ...] = ()
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeOrderGuardrailCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeOrderGuardrailReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeOrderGuardrailCheck, ...]
    blocked_order_scenarios: int = Field(ge=0)
    unexpected_order_scenarios: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeScheduleGuardrailCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeScheduleGuardrailReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeScheduleGuardrailCheck, ...]
    approved_schedule_scenarios: int = Field(ge=0)
    protected_schedule_scenarios: int = Field(ge=0)
    unexpected_schedule_scenarios: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeFillSyncCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeFillSyncReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeFillSyncCheck, ...]
    incremental_fill_scenarios: int = Field(ge=0)
    duplicate_fill_scenarios: int = Field(ge=0)
    unexpected_fill_scenarios: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeDataQualityAuditCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeDataQualityAuditReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    checks: tuple[RuntimeDataQualityAuditCheck, ...]
    latest_price_scenarios: int = Field(ge=0)
    daily_bar_scenarios: int = Field(ge=0)
    symbol_universe_scenarios: int = Field(default=0, ge=0)
    failed_quality_scenarios: int = Field(ge=0)
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimeBrokerOrderHistoryCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeBrokerOrderHistoryReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    source: str = Field(min_length=1)
    checks: tuple[RuntimeBrokerOrderHistoryCheck, ...]
    local_order_count: int = Field(ge=0)
    broker_order_count: int = Field(ge=0)
    matched_order_count: int = Field(ge=0)
    mismatch_count: int = Field(ge=0)
    missing_broker_order_ids: tuple[str, ...] = ()
    unexpected_broker_order_ids: tuple[str, ...] = ()
    session_started_at: AwareDatetime | None = None
    session_completed_at: AwareDatetime | None = None
    symbols: tuple[str, ...] = ()
    order_history_path: str | None = None
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimePostRunReviewStep(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    required: bool = True
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()
    path: str | None = None


class RuntimePostRunReviewReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    steps: tuple[RuntimePostRunReviewStep, ...]
    soak_report: RuntimeSoakEvidenceReport | None = None
    secret_scan_report: RuntimeSecretScanReport | None = None
    statement_reconciliation_report: Any | None = None
    completion_audit_report: FunctionalCompletionAuditReport | None = None
    evidence_bundle_report: RuntimeEvidenceBundleReport | None = None
    dashboard_consistency_report: RuntimeDashboardConsistencyReport | None = None
    dashboard_visual_report: RuntimeDashboardVisualReport | None = None
    evidence_coherence_report: RuntimeEvidenceCoherenceReport | None = None
    artifact_integrity_report: RuntimeArtifactIntegrityReport | None = None
    lifecycle_drill_report: RuntimeLifecycleDrillReport | None = None
    credentialed_session_report: RuntimeCredentialedSessionReport | None = None
    model_governance_report: RuntimeModelGovernanceReport | None = None
    order_guardrail_report: RuntimeOrderGuardrailReport | None = None
    schedule_guardrail_report: RuntimeScheduleGuardrailReport | None = None
    fill_sync_report: RuntimeFillSyncReport | None = None
    data_quality_audit_report: RuntimeDataQualityAuditReport | None = None
    broker_order_history_report: RuntimeBrokerOrderHistoryReport | None = None
    operations_readiness_report: RuntimeOperationsReadinessReport | None = None
    recovery_audit_report: RuntimeRecoveryAuditReport | None = None
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


class RuntimePreflightCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    remediation: str = Field(min_length=1)
    checked_at: AwareDatetime
    evidence: tuple[str, ...] = ()


class RuntimePreflightReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    can_start: bool
    summary: str = Field(min_length=1)
    checks: tuple[RuntimePreflightCheck, ...]
    warnings: int = Field(ge=0)
    failures: int = Field(ge=0)


class RuntimeCycleResult(TradingModel):
    as_of: AwareDatetime
    status: RuntimeStatus
    prices_refreshed: bool = False
    broker_synced: bool = False
    strategy_evaluated: bool = False
    shadow_challenger_observed: bool = False
    orders_submitted: int = Field(default=0, ge=0)
    fills_applied: int = Field(default=0, ge=0)
    report_written: bool = False
    nightly_learning_ran: bool = False
    events: tuple[RuntimeEvent, ...] = ()
    alerts: tuple[RuntimeAlert, ...] = ()


class RuntimeDryRunStep(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    checked_at: AwareDatetime
    evidence: tuple[str, ...] = ()


class RuntimeDryRunReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    can_start_supervised_runtime: bool
    monitor_only: bool
    summary: str = Field(min_length=1)
    preflight_report: RuntimePreflightReport
    cycle_result: RuntimeCycleResult | None = None
    health_report: RuntimeHealthReport | None = None
    steps: tuple[RuntimeDryRunStep, ...]
    warnings: int = Field(ge=0)
    failures: int = Field(ge=0)
    orders_before: int = Field(default=0, ge=0)
    orders_after: int = Field(default=0, ge=0)
    orders_submitted: int = Field(default=0, ge=0)
    runtime_mode: str | None = Field(default=None, min_length=1)
    broker_provider: str | None = Field(default=None, min_length=1)
    latest_price_source: str | None = Field(default=None, min_length=1)
    latest_price_feed: str | None = Field(default=None, min_length=1)


class RuntimeValidationStep(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    checked_at: AwareDatetime
    evidence: tuple[str, ...] = ()


class RuntimeValidationChecklistItem(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeValidationReport(TradingModel):
    id: str = Field(min_length=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    status: RuntimePreflightStatus
    can_start_full_day_soak: bool
    summary: str = Field(min_length=1)
    preflight_report: RuntimePreflightReport
    monitor_dry_run_report: RuntimeDryRunReport | None = None
    scheduled_order_dry_run_report: RuntimeDryRunReport | None = None
    soak_cycles: tuple[RuntimeCycleResult, ...] = ()
    soak_health_report: RuntimeHealthReport | None = None
    steps: tuple[RuntimeValidationStep, ...]
    checklist: tuple[RuntimeValidationChecklistItem, ...] = ()
    warnings: int = Field(ge=0)
    failures: int = Field(ge=0)
    latest_prices_refreshed: bool = False
    latest_prices_fresh: bool = False
    broker_synced: bool = False
    dashboard_snapshot_serialized: bool = False
    report_written: bool = False
    nightly_learning_ran: bool = False
    orders_submitted: int = Field(default=0, ge=0)
    soak_cycles_completed: int = Field(default=0, ge=0)
    soak_monitor_only: bool = True
    mode: str = Field(default="Alpaca Paper", min_length=1)
    symbols: tuple[str, ...] = ()
    feed: str | None = Field(default=None, min_length=1)
    dashboard_host: str | None = Field(default=None, min_length=1)
    credential_required: bool = True
    scheduled_order_check_included: bool = False
    paper_orders_allowed_during_soak: bool = False
    broker_providers: tuple[str, ...] = ()
    latest_price_sources: tuple[str, ...] = ()
    latest_price_feeds: tuple[str, ...] = ()
    markdown_path: str | None = None


class RuntimeSoakEvidenceCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeSoakEvidenceReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    duration_hours: float = Field(default=0, ge=0)
    cycle_count: int = Field(default=0, ge=0)
    market_cycle_count: int = Field(default=0, ge=0)
    off_hours_cycle_count: int = Field(default=0, ge=0)
    overnight_cycle_count: int = Field(default=0, ge=0)
    prices_refreshed_cycle_count: int = Field(default=0, ge=0)
    broker_synced_cycle_count: int = Field(default=0, ge=0)
    missed_price_refresh_cycles: int = Field(default=0, ge=0)
    missed_broker_sync_cycles: int = Field(default=0, ge=0)
    order_cycles: int = Field(default=0, ge=0)
    off_schedule_order_cycles: int = Field(default=0, ge=0)
    max_market_gap_seconds: float | None = Field(default=None, ge=0)
    max_off_hours_gap_seconds: float | None = Field(default=None, ge=0)
    report_written: bool = False
    nightly_learning_ran: bool = False
    dashboard_snapshot_available: bool = False
    final_health_status: str | None = Field(default=None, min_length=1)
    runtime_event_count: int = Field(default=0, ge=0)
    runtime_warning_event_count: int = Field(default=0, ge=0)
    runtime_error_event_count: int = Field(default=0, ge=0)
    checks: tuple[RuntimeSoakEvidenceCheck, ...]


class RuntimeSecretScanFinding(TradingModel):
    path: str = Field(min_length=1)
    line_number: int = Field(ge=1)
    secret_name: str = Field(min_length=1)
    message: str = Field(min_length=1)


class RuntimeSecretScanReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    passed: bool
    output_dir: str = Field(min_length=1)
    scan_roots: tuple[str, ...] = ()
    files_scanned: int = Field(ge=0)
    files_skipped: int = Field(ge=0)
    secret_names_checked: tuple[str, ...]
    findings: tuple[RuntimeSecretScanFinding, ...] = ()
    summary: str = Field(min_length=1)


class RuntimeSnapshot(TradingModel):
    as_of: AwareDatetime
    status: RuntimeStatus
    mode: str = Field(min_length=1)
    latest_prices: LatestPriceSnapshot | None = None
    paper_report: PaperPortfolioReport | None = None
    daily_report: DailyTradingReport | None = None
    shadow_challenger: ShadowChallengerObservation | None = None
    shadow_challengers: tuple[ShadowChallengerObservation, ...] = ()
    nightly_learning: NightlyLearningRun | None = None
    active_model_key: str = Field(min_length=1)
    last_cycle: RuntimeCycleResult | None = None
    daily_report_path: str | None = None
    nightly_learning_path: str | None = None
    events: tuple[RuntimeEvent, ...] = ()
    control_state: OperatorControlState | None = None
    last_control_result: OperatorControlResult | None = None
    alerts: tuple[RuntimeAlert, ...] = ()
    health_report: RuntimeHealthReport | None = None
