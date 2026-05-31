"""Named-scenario coverage requirements for persisted runtime audits."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from trading_app.runtime.models import (
    FunctionalRequirementStatus,
    RuntimePreflightStatus,
)

REQUIRED_FUNCTIONAL_REQUIREMENTS = frozenset(
    f"FR-{index:02d}" for index in range(1, 19)
)
REQUIRED_EVIDENCE_BUNDLE_ITEMS = frozenset(
    {
        "preflight",
        "operations_readiness",
        "lifecycle_drill",
        "monitor_dry_run",
        "validation_report",
        "soak_evidence",
        "runtime_snapshot",
        "restart_recovery",
        "dashboard_snapshot",
        "dashboard_consistency",
        "dashboard_visual",
        "data_quality_audit",
        "broker_order_history",
        "credentialed_session",
        "evidence_coherence",
        "artifact_integrity",
        "health_report",
        "daily_report",
        "nightly_learning",
        "model_governance",
        "schedule_guardrails",
        "order_guardrails",
        "fill_sync",
        "secret_scan",
        "statement_reconciliation",
        "completion_audit",
    }
)
REQUIRED_VALIDATION_CHECKLIST_ITEMS = frozenset(
    {
        "credentialed_preflight",
        "monitor_only_dry_run",
        "scheduled_order_dry_run",
        "latest_price_freshness",
        "broker_sync",
        "dashboard_snapshot",
        "soak_cycle_evidence",
        "full_day_plus_overnight_soak",
        "paper_order_boundary",
        "daily_report_proof",
        "nightly_learning_proof",
        "broker_provider_provenance",
        "latest_price_source_provenance",
    }
)
VALIDATION_CHECKLIST_SOAK_ITEMS = frozenset(
    {
        "soak_cycle_evidence",
        "full_day_plus_overnight_soak",
    }
)
REQUIRED_ARTIFACT_LABELS = frozenset(
    {
        "preflight state",
        "operations readiness state",
        "lifecycle drill state",
        "dry-run state",
        "validation state",
        "soak state",
        "runtime snapshot state",
        "dashboard snapshot state",
        "daily report state",
        "daily report path state",
        "dashboard consistency state",
        "dashboard visual state",
        "data quality audit state",
        "broker order history state",
        "credentialed session state",
        "evidence coherence state",
        "restart recovery state",
        "secret scan state",
        "model governance state",
        "order guardrail state",
        "schedule guardrail state",
        "fill sync state",
        "statement reconciliation state",
        "broker statement source",
        "completion audit state",
        "evidence bundle state",
        "evidence bundle markdown",
    }
)
EVIDENCE_BUNDLE_ARTIFACT_LABELS = frozenset(
    {"evidence bundle state", "evidence bundle markdown"}
)
REQUIRED_FINAL_ACCEPTANCE_CHECKS = frozenset(
    {
        "operator_signoff_accepted",
        "operator_signoff_final",
        "operator_signoff_artifacts_current",
        "operator_confirmations",
        "review_artifact_paths",
        "signed_paths_match_latest",
        "signed_review_artifacts_current",
        "completion_audit_final",
        "evidence_bundle_final",
        "artifact_integrity_final",
        "reviewed_artifact_hashes_current",
        "credentialed_session_final",
        "paper_account_alignment",
        "final_packet_ordering",
        "paper_only_acceptance_boundary",
    }
)
REQUIRED_OPERATOR_SIGNOFF_CHECKS = frozenset(
    {
        "evidence_bundle_ready",
        "completion_audit_passed",
        "artifact_integrity_passed",
        "reviewer_recorded",
        "paper_account_recorded",
        "credentialed_session_passed",
        "paper_account_matches_credentialed_session",
        "signoff_packet_ordering",
        "reviewed_markdown_artifacts_current",
        "confirmation_evidence_reviewed",
        "confirmation_alpaca_paper_account_history",
        "confirmation_no_unintended_orders",
        "confirmation_fills_and_reconciliation_reviewed",
        "confirmation_dashboard_reviewed",
        "confirmation_paper_only_boundary",
        "confirmation_limitations_acknowledged",
    }
)

REQUIRED_DATA_QUALITY_CHECKS = frozenset(
    {
        "fresh_sip_latest_prices_pass",
        "iex_latest_prices_warn_development_grade",
        "stale_missing_latest_prices_fail",
        "clean_sip_daily_bars_pass",
        "iex_missing_daily_bars_warn",
        "duplicate_mixed_lookahead_daily_bars_fail",
        "invalid_symbol_universe_fail",
    }
)
REQUIRED_ORDER_GUARDRAIL_CHECKS = frozenset(
    {
        "missing_latest_price_blocks_orders",
        "stale_latest_price_blocks_orders",
        "risk_rejection_blocks_orders",
        "dirty_reconciliation_blocks_orders",
        "paper_kill_switch_blocks_orders",
        "operator_pause_blocks_orders",
    }
)
REQUIRED_SCHEDULE_GUARDRAIL_CHECKS = frozenset(
    {
        "regular_hours_monitor_only",
        "pre_trade_window_monitor_only",
        "daily_close_evaluates",
        "same_day_repeat_blocks",
        "weekend_blocks_strategy",
    }
)
REQUIRED_FILL_SYNC_CHECKS = frozenset(
    {
        "first_incremental_fill_applies_once",
        "repeat_sync_does_not_duplicate_fill",
        "second_incremental_fill_applies_once",
        "restart_sync_does_not_duplicate_fill",
    }
)
REQUIRED_BROKER_ORDER_HISTORY_CHECKS = frozenset(
    {
        "broker_history_source",
        "broker_provider",
        "local_orders_have_broker_ids",
        "broker_orders_match_local_submissions",
        "broker_order_fields_match",
        "broker_filled_quantities_match_ledger_fills",
    }
)
REQUIRED_RECOVERY_CHECKS = frozenset(
    {
        "journals_readable",
        "state_recovered",
        "duplicate_order_ids",
        "duplicate_broker_order_ids",
        "duplicate_fill_ids",
        "dedupe_consistency",
        "runtime_snapshot_alignment",
    }
)
REQUIRED_OPERATIONS_CHECKS = frozenset(
    {
        "paper_only_startup",
        "local_dashboard_binding",
        "artifact_layout",
        "dependency_setup",
        "env_template",
        "operator_runbook",
        "emergency_stop_procedure",
        "supervisor_templates",
    }
)
REQUIRED_LIFECYCLE_CHECKS = frozenset(
    {
        "operations_readiness",
        "startup_command_documented",
        "dashboard_local_only",
        "runtime_start_evidence",
        "operator_controls_exercised",
        "control_state_recovered",
        "emergency_stop_controls_exercised",
        "force_reconciliation_and_report_effects",
        "shutdown_procedure_documented",
    }
)
REQUIRED_LIFECYCLE_ACTIONS = frozenset(
    {
        "pause_runtime",
        "resume_runtime",
        "enable_paper_kill_switch",
        "disable_paper_kill_switch",
        "force_reconciliation",
        "generate_report",
    }
)
REQUIRED_CREDENTIAL_SESSION_CHECKS = frozenset(
    {
        "preflight_credentials",
        "credentialed_validation",
        "runtime_snapshot_alpaca_paper",
        "dashboard_snapshot_alpaca_paper",
        "latest_price_provenance",
        "soak_session_window",
        "statement_provenance",
        "broker_order_history_provenance",
        "secret_scan_clean",
    }
)
REQUIRED_DASHBOARD_CONSISTENCY_CHECKS = frozenset(
    {
        "runtime_snapshot_present",
        "dashboard_snapshot_present",
        "snapshot_freshness",
        "runtime_paper_report_present",
        "runtime_daily_report_present",
        "paper_mode",
        "broker_provider",
        "embedded_runtime_state",
        "snapshot_timestamp",
        "cash",
        "estimated_equity",
        "realized_pnl",
        "open_orders",
        "recent_fills",
        "positions",
        "active_model",
        "data_quality",
        "operator_controls",
        "runtime_alerts",
        "runtime_health",
        "statement_review",
        "completion_audit",
    }
)
REQUIRED_DASHBOARD_VISUAL_CHECKS = frozenset(
    {
        "html_document_rendered",
        "paper_boundary_visible",
        "critical_runtime_surfaces_present",
        "operator_controls_present",
        "alerts_and_degraded_states_visible",
        "data_quality_panel_present",
        "active_model_explanation_present",
        "live_readiness_gated",
        "responsive_css_present",
        "financial_visuals_present",
        "visual_system_tokens_present",
    }
)
REQUIRED_MODEL_GOVERNANCE_CHECKS = frozenset(
    {
        "learning_run_present",
        "active_model_unchanged",
        "active_keys_unchanged",
        "recommendations_manual_review",
        "recommendation_evidence",
        "unreviewed_authority_increases",
        "learning_memo_boundary",
    }
)
REQUIRED_EVIDENCE_COHERENCE_CHECKS = frozenset(
    {
        "validation_present",
        "soak_present",
        "runtime_snapshot_present",
        "dashboard_snapshot_present",
        "dashboard_consistency_present",
        "statement_reconciliation_present",
        "broker_order_history_present",
        "credentialed_session_present",
        "validation_window",
        "soak_window",
        "validation_before_soak",
        "snapshot_within_review_window",
        "dashboard_consistency_passed",
        "dashboard_matches_runtime_snapshot",
        "statement_after_runtime_snapshot",
        "broker_order_history_after_runtime_snapshot",
        "alpaca_provider_alignment",
        "broker_order_history_provider_alignment",
        "broker_order_history_order_alignment",
        "alpaca_price_source_alignment",
        "soak_evidence_clean",
        "credentialed_session_passed",
        "credentialed_session_window_alignment",
        "credentialed_session_validation_alignment",
        "credentialed_session_account_alignment",
    }
)

MIN_LATEST_PRICE_SCENARIOS = 3
MIN_DAILY_BAR_SCENARIOS = 3
MIN_SYMBOL_UNIVERSE_SCENARIOS = 1
MIN_BLOCKED_ORDER_SCENARIOS = len(REQUIRED_ORDER_GUARDRAIL_CHECKS)
MIN_APPROVED_SCHEDULE_SCENARIOS = 1
MIN_PROTECTED_SCHEDULE_SCENARIOS = 4
MIN_INCREMENTAL_FILL_SCENARIOS = 2
MIN_DUPLICATE_FILL_SCENARIOS = 2
MIN_BROKER_LOCAL_ORDERS = 1
MIN_LIFECYCLE_CONTROL_ACTIONS = len(REQUIRED_LIFECYCLE_ACTIONS)
MIN_CREDENTIAL_REVIEWED_ARTIFACTS = len(REQUIRED_CREDENTIAL_SESSION_CHECKS)
MIN_CREDENTIAL_EXTERNAL_SOURCES = 3
MIN_DASHBOARD_CRITICAL_SURFACES = 7
MIN_DASHBOARD_RESPONSIVE_SURFACES = 3
MIN_MODEL_RECOMMENDATIONS = 1
MIN_FUNCTIONAL_REQUIREMENTS = len(REQUIRED_FUNCTIONAL_REQUIREMENTS)
MIN_EVIDENCE_BUNDLE_ITEMS = len(REQUIRED_EVIDENCE_BUNDLE_ITEMS)
MIN_REQUIRED_ARTIFACTS = len(REQUIRED_ARTIFACT_LABELS)


def _append_markdown_artifact_gap(gaps: list[str], report) -> None:
    markdown_path = getattr(report, "markdown_path", None)
    if not markdown_path:
        gaps.append("markdown_path=missing")
    elif not Path(markdown_path).exists():
        gaps.append("markdown_path_file=missing")


def data_quality_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted data-quality proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="latest_price_scenarios",
        minimum=MIN_LATEST_PRICE_SCENARIOS,
        actual=report.latest_price_scenarios,
    )
    _append_min_gap(
        gaps,
        name="daily_bar_scenarios",
        minimum=MIN_DAILY_BAR_SCENARIOS,
        actual=report.daily_bar_scenarios,
    )
    _append_min_gap(
        gaps,
        name="symbol_universe_scenarios",
        minimum=MIN_SYMBOL_UNIVERSE_SCENARIOS,
        actual=getattr(report, "symbol_universe_scenarios", 0),
    )
    if report.failed_quality_scenarios:
        gaps.append(f"failed_quality_scenarios={report.failed_quality_scenarios}")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_DATA_QUALITY_CHECKS))
    return tuple(gaps)


def order_guardrail_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted order-guardrail proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="blocked_order_scenarios",
        minimum=MIN_BLOCKED_ORDER_SCENARIOS,
        actual=report.blocked_order_scenarios,
    )
    if report.unexpected_order_scenarios:
        gaps.append(f"unexpected_order_scenarios={report.unexpected_order_scenarios}")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_ORDER_GUARDRAIL_CHECKS))
    return tuple(gaps)


def schedule_guardrail_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted schedule-guardrail proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="approved_schedule_scenarios",
        minimum=MIN_APPROVED_SCHEDULE_SCENARIOS,
        actual=report.approved_schedule_scenarios,
    )
    _append_min_gap(
        gaps,
        name="protected_schedule_scenarios",
        minimum=MIN_PROTECTED_SCHEDULE_SCENARIOS,
        actual=report.protected_schedule_scenarios,
    )
    if report.unexpected_schedule_scenarios:
        gaps.append(
            f"unexpected_schedule_scenarios={report.unexpected_schedule_scenarios}"
        )
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_SCHEDULE_GUARDRAIL_CHECKS))
    return tuple(gaps)


def fill_sync_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted fill-sync proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="incremental_fill_scenarios",
        minimum=MIN_INCREMENTAL_FILL_SCENARIOS,
        actual=report.incremental_fill_scenarios,
    )
    _append_min_gap(
        gaps,
        name="duplicate_fill_scenarios",
        minimum=MIN_DUPLICATE_FILL_SCENARIOS,
        actual=report.duplicate_fill_scenarios,
    )
    if report.unexpected_fill_scenarios:
        gaps.append(f"unexpected_fill_scenarios={report.unexpected_fill_scenarios}")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_FILL_SYNC_CHECKS))
    return tuple(gaps)


def broker_order_history_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted broker order-history proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    if report.provider != "alpaca-paper":
        gaps.append(f"provider={report.provider}")
    _append_min_gap(
        gaps,
        name="local_order_count",
        minimum=MIN_BROKER_LOCAL_ORDERS,
        actual=report.local_order_count,
    )
    if report.broker_order_count < report.local_order_count:
        gaps.append(
            "broker_order_count_missing="
            f"{report.local_order_count - report.broker_order_count}"
        )
    if report.matched_order_count < report.local_order_count:
        gaps.append(
            "matched_order_count_missing="
            f"{report.local_order_count - report.matched_order_count}"
        )
    if report.mismatch_count:
        gaps.append(f"mismatch_count={report.mismatch_count}")
    if report.missing_broker_order_ids:
        gaps.append(
            "missing_broker_order_ids="
            + ",".join(sorted(report.missing_broker_order_ids))
        )
    if report.unexpected_broker_order_ids:
        gaps.append(
            "unexpected_broker_order_ids="
            + ",".join(sorted(report.unexpected_broker_order_ids))
        )
    gaps.extend(
        _required_check_gaps(report.checks, REQUIRED_BROKER_ORDER_HISTORY_CHECKS)
    )
    return tuple(gaps)


def recovery_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted restart-recovery proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_count_match_gap(
        gaps,
        name="submission_count",
        raw=report.raw_submission_count,
        recovered=report.recovered_submission_count,
    )
    _append_count_match_gap(
        gaps,
        name="order_status_count",
        raw=report.raw_order_status_count,
        recovered=report.recovered_order_status_count,
    )
    _append_count_match_gap(
        gaps,
        name="fill_count",
        raw=report.raw_fill_count,
        recovered=report.recovered_fill_count,
    )
    if report.duplicate_order_ids:
        gaps.append(
            "duplicate_order_ids=" + ",".join(sorted(report.duplicate_order_ids))
        )
    if report.duplicate_broker_order_ids:
        gaps.append(
            "duplicate_broker_order_ids="
            + ",".join(sorted(report.duplicate_broker_order_ids))
        )
    if report.duplicate_fill_ids:
        gaps.append("duplicate_fill_ids=" + ",".join(sorted(report.duplicate_fill_ids)))
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_RECOVERY_CHECKS))
    return tuple(gaps)


def operations_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted operations-readiness proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    startup = report.startup_command
    if "run_alpaca_paper" not in startup:
        gaps.append("startup_command_missing=run_alpaca_paper")
    if "--monitor-only-dry-run-first" not in startup:
        gaps.append("startup_command_missing=monitor_only_dry_run_first")
    if "--skip-preflight" in startup:
        gaps.append("startup_command_forbidden=skip_preflight")
    if "live" in startup.casefold():
        gaps.append("startup_command_forbidden=live")
    if not _local_url(report.dashboard_url):
        gaps.append(f"dashboard_url_not_local={report.dashboard_url}")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_OPERATIONS_CHECKS))
    return tuple(gaps)


def validation_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted supervised-validation checklist proof gaps, if any."""

    gaps: list[str] = []
    checklist = tuple(getattr(report, "checklist", ()))
    names = [item.name for item in checklist]
    gaps.extend(
        _name_set_gaps(
            names,
            REQUIRED_VALIDATION_CHECKLIST_ITEMS,
            label="checklist_items",
        )
    )
    failed_items = tuple(
        sorted(
            item.name
            for item in checklist
            if item.name in REQUIRED_VALIDATION_CHECKLIST_ITEMS
            and item.status == RuntimePreflightStatus.FAILED
        )
    )
    if failed_items:
        gaps.append("failed_checklist_items=" + ",".join(failed_items))
    nonpassing_blocking_items = tuple(
        sorted(
            item.name
            for item in checklist
            if item.name
            in REQUIRED_VALIDATION_CHECKLIST_ITEMS - VALIDATION_CHECKLIST_SOAK_ITEMS
            and item.status != RuntimePreflightStatus.PASSED
        )
    )
    if nonpassing_blocking_items:
        gaps.append("nonpassing_checklist_items=" + ",".join(nonpassing_blocking_items))
    return tuple(gaps)


def lifecycle_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted lifecycle-drill proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="operator_control_count",
        minimum=MIN_LIFECYCLE_CONTROL_ACTIONS,
        actual=report.operator_control_count,
    )
    if not report.emergency_stop_confirmed:
        gaps.append("emergency_stop_confirmed=false")
    if not report.shutdown_procedure_documented:
        gaps.append("shutdown_procedure_documented=false")
    action_values = {
        _action_value(action) for action in report.persisted_control_actions
    }
    missing_actions = tuple(sorted(REQUIRED_LIFECYCLE_ACTIONS - action_values))
    if missing_actions:
        gaps.append("missing_control_actions=" + ",".join(missing_actions))
    if not _local_url(report.dashboard_url):
        gaps.append(f"dashboard_url_not_local={report.dashboard_url}")
    if "--monitor-only-dry-run-first" not in report.startup_command:
        gaps.append("startup_command_missing=monitor_only_dry_run_first")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_LIFECYCLE_CHECKS))
    return tuple(gaps)


def credentialed_session_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted credentialed-session proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    if not report.validation_id:
        gaps.append("validation_id=missing")
    if not report.paper_account_id:
        gaps.append("paper_account_id=missing")
    if report.session_started_at is None:
        gaps.append("session_started_at=missing")
    if report.session_completed_at is None:
        gaps.append("session_completed_at=missing")
    if (
        report.session_started_at is not None
        and report.session_completed_at is not None
        and report.session_completed_at < report.session_started_at
    ):
        gaps.append("session_window=out_of_order")
    if "alpaca-paper" not in set(report.broker_providers):
        gaps.append("broker_providers_missing=alpaca-paper")
    if not any(
        _trusted_alpaca_source(source) for source in report.latest_price_sources
    ):
        gaps.append("latest_price_sources_missing=alpaca")
    if report.feed is None:
        gaps.append("feed=missing")
    _append_min_gap(
        gaps,
        name="reviewed_artifact_count",
        minimum=MIN_CREDENTIAL_REVIEWED_ARTIFACTS,
        actual=report.reviewed_artifact_count,
    )
    _append_min_gap(
        gaps,
        name="external_source_count",
        minimum=MIN_CREDENTIAL_EXTERNAL_SOURCES,
        actual=report.external_source_count,
    )
    forbidden_sources = tuple(
        sorted(
            source
            for source in (*report.broker_providers, *report.latest_price_sources)
            if _forbidden_provenance(source)
        )
    )
    if forbidden_sources:
        gaps.append("forbidden_sources=" + ",".join(forbidden_sources))
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_CREDENTIAL_SESSION_CHECKS))
    return tuple(gaps)


def dashboard_consistency_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted dashboard consistency proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    gaps.extend(
        _required_check_gaps(report.checks, REQUIRED_DASHBOARD_CONSISTENCY_CHECKS)
    )
    return tuple(gaps)


def dashboard_visual_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted dashboard visual-readiness proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="critical_surface_count",
        minimum=MIN_DASHBOARD_CRITICAL_SURFACES,
        actual=report.critical_surface_count,
    )
    _append_min_gap(
        gaps,
        name="responsive_surface_count",
        minimum=MIN_DASHBOARD_RESPONSIVE_SURFACES,
        actual=report.responsive_surface_count,
    )
    if report.failed_visual_scenarios:
        gaps.append(f"failed_visual_scenarios={report.failed_visual_scenarios}")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_DASHBOARD_VISUAL_CHECKS))
    return tuple(gaps)


def model_governance_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted model-governance proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    if not report.learning_run_id:
        gaps.append("learning_run_id=missing")
    _append_min_gap(
        gaps,
        name="recommendation_count",
        minimum=MIN_MODEL_RECOMMENDATIONS,
        actual=report.recommendation_count,
    )
    if report.unreviewed_authority_increases:
        gaps.append(
            "unreviewed_authority_increases="
            + ",".join(sorted(report.unreviewed_authority_increases))
        )
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_MODEL_GOVERNANCE_CHECKS))
    return tuple(gaps)


def evidence_coherence_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted evidence-coherence proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_EVIDENCE_COHERENCE_CHECKS))
    return tuple(gaps)


def functional_completion_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted functional-completion proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="proven_count",
        minimum=MIN_FUNCTIONAL_REQUIREMENTS,
        actual=report.proven_count,
    )
    if report.missing_count:
        gaps.append(f"missing_count={report.missing_count}")
    if report.failed_count:
        gaps.append(f"failed_count={report.failed_count}")
    if report.external_required_count:
        gaps.append(f"external_required_count={report.external_required_count}")
    requirement_ids = [requirement.id for requirement in report.requirements]
    gaps.extend(_name_set_gaps(requirement_ids, REQUIRED_FUNCTIONAL_REQUIREMENTS))
    nonproven = tuple(
        sorted(
            requirement.id
            for requirement in report.requirements
            if requirement.id in REQUIRED_FUNCTIONAL_REQUIREMENTS
            and requirement.status != FunctionalRequirementStatus.PROVEN
        )
    )
    if nonproven:
        gaps.append("nonproven_requirements=" + ",".join(nonproven))
    return tuple(gaps)


def evidence_bundle_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted evidence-bundle proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    _append_min_gap(
        gaps,
        name="required_count",
        minimum=MIN_EVIDENCE_BUNDLE_ITEMS,
        actual=report.required_count,
    )
    if not report.ready_for_operator_review:
        gaps.append("ready_for_operator_review=false")
    if report.warning_count:
        gaps.append(f"warning_count={report.warning_count}")
    if report.failed_count:
        gaps.append(f"failed_count={report.failed_count}")
    if report.missing_required_count:
        gaps.append(f"missing_required_count={report.missing_required_count}")
    if report.passed_count < report.required_count:
        gaps.append(
            f"passed_count_missing={report.required_count - report.passed_count}"
        )
    item_names = [item.name for item in report.items if item.required]
    gaps.extend(_name_set_gaps(item_names, REQUIRED_EVIDENCE_BUNDLE_ITEMS))
    nonpassing = tuple(
        sorted(
            item.name
            for item in report.items
            if item.required and item.status != RuntimePreflightStatus.PASSED
        )
    )
    if nonpassing:
        gaps.append("nonpassing_items=" + ",".join(nonpassing))
    missing_paths = tuple(
        sorted(
            item.name
            for item in report.items
            if item.required
            and item.status == RuntimePreflightStatus.PASSED
            and not item.path
        )
    )
    if missing_paths:
        gaps.append("missing_item_paths=" + ",".join(missing_paths))
    missing_path_files = tuple(
        sorted(
            item.name
            for item in report.items
            if item.required
            and item.status == RuntimePreflightStatus.PASSED
            and item.path
            and not Path(item.path).exists()
        )
    )
    if missing_path_files:
        gaps.append("missing_item_path_files=" + ",".join(missing_path_files))
    self_referential_paths = tuple(
        sorted(
            item.name
            for item in report.items
            if item.required
            and item.status == RuntimePreflightStatus.PASSED
            and item.path
            and report.markdown_path
            and Path(item.path) == Path(report.markdown_path)
        )
    )
    if self_referential_paths:
        gaps.append("self_referential_item_paths=" + ",".join(self_referential_paths))
    return tuple(gaps)


def artifact_integrity_coverage_gap(
    report, *, require_evidence_bundle: bool = True
) -> tuple[str, ...]:
    """Return persisted artifact-integrity proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    required_labels = (
        REQUIRED_ARTIFACT_LABELS
        if require_evidence_bundle
        else REQUIRED_ARTIFACT_LABELS - EVIDENCE_BUNDLE_ARTIFACT_LABELS
    )
    _append_min_gap(
        gaps,
        name="required_count",
        minimum=len(required_labels),
        actual=report.required_count,
    )
    if report.missing_required_count:
        gaps.append(f"missing_required_count={report.missing_required_count}")
    hash_mismatch_count = getattr(report, "hash_mismatch_count", 0)
    if hash_mismatch_count:
        gaps.append(f"hash_mismatch_count={hash_mismatch_count}")
    if report.hashed_count < report.required_count:
        gaps.append(
            f"hashed_count_missing={report.required_count - report.hashed_count}"
        )
    relevant_required_items = tuple(
        item for item in report.items if item.required and item.label in required_labels
    )
    labels = [item.label for item in report.items if item.required]
    gaps.extend(_name_set_gaps(labels, required_labels, label="labels"))
    missing_hashes = tuple(
        sorted(
            item.label
            for item in relevant_required_items
            if not item.exists or not item.sha256
        )
    )
    if missing_hashes:
        gaps.append("unhashed_required=" + ",".join(missing_hashes))
    mismatched_hashes = tuple(
        sorted(
            item.label
            for item in relevant_required_items
            if getattr(item, "hash_matches", None) is False
        )
    )
    if mismatched_hashes:
        gaps.append("hash_mismatch_required=" + ",".join(mismatched_hashes))
    missing_current_files: list[str] = []
    changed_current_files: list[str] = []
    for item in relevant_required_items:
        path = Path(item.path)
        if not path.exists():
            missing_current_files.append(item.label)
            continue
        if item.sha256 and hashlib.sha256(path.read_bytes()).hexdigest() != item.sha256:
            changed_current_files.append(item.label)
    if missing_current_files:
        gaps.append(
            "current_file_missing_required=" + ",".join(sorted(missing_current_files))
        )
    if changed_current_files:
        gaps.append(
            "current_hash_mismatch_required=" + ",".join(sorted(changed_current_files))
        )
    return tuple(gaps)


def final_acceptance_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted final-acceptance proof gaps, if any."""

    gaps: list[str] = []
    _append_markdown_artifact_gap(gaps, report)
    if report.status != RuntimePreflightStatus.PASSED:
        gaps.append(f"status={report.status.value}")
    if not report.accepted_for_functional_paper_app:
        gaps.append("accepted_for_functional_paper_app=false")
    if not report.signoff_path:
        gaps.append("signoff_path=missing")
    elif not Path(report.signoff_path).exists():
        gaps.append("signoff_path_file=missing")
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_FINAL_ACCEPTANCE_CHECKS))
    return tuple(gaps)


def operator_signoff_coverage_gap(report) -> tuple[str, ...]:
    """Return persisted operator-signoff proof gaps, if any."""

    gaps: list[str] = []
    if report.status != RuntimePreflightStatus.PASSED:
        gaps.append(f"status={report.status.value}")
    if not report.accepted_for_paper_review:
        gaps.append("accepted_for_paper_review=false")
    if report.missing_confirmation_count:
        gaps.append(f"missing_confirmation_count={report.missing_confirmation_count}")
    if not report.reviewer or report.reviewer == "missing":
        gaps.append("reviewer=missing")
    if not report.paper_account_id or report.paper_account_id == "missing":
        gaps.append("paper_account_id=missing")
    required_paths = {
        "evidence_bundle_path": report.evidence_bundle_path,
        "credentialed_session_path": report.credentialed_session_path,
        "completion_audit_path": report.completion_audit_path,
        "artifact_integrity_path": report.artifact_integrity_path,
        "markdown_path": report.markdown_path,
    }
    missing_paths = tuple(
        sorted(name for name, path in required_paths.items() if not path)
    )
    if missing_paths:
        gaps.append("missing_paths=" + ",".join(missing_paths))
    missing_path_files = tuple(
        sorted(
            name
            for name, path in required_paths.items()
            if path and not Path(path).exists()
        )
    )
    if missing_path_files:
        gaps.append("missing_path_files=" + ",".join(missing_path_files))
    gaps.extend(_required_check_gaps(report.checks, REQUIRED_OPERATOR_SIGNOFF_CHECKS))
    return tuple(gaps)


def _append_min_gap(gaps: list[str], *, name: str, minimum: int, actual: int) -> None:
    if actual < minimum:
        gaps.append(f"{name}_missing={minimum - actual}")


def _append_count_match_gap(
    gaps: list[str], *, name: str, raw: int, recovered: int
) -> None:
    if raw != recovered:
        gaps.append(f"{name}_mismatch=raw:{raw}:recovered:{recovered}")


def _action_value(action) -> str:
    return getattr(action, "value", str(action))


def _local_url(value: str) -> bool:
    normalized = value.casefold()
    return normalized.startswith("http://127.0.0.1") or normalized.startswith(
        "http://localhost"
    )


def _trusted_alpaca_source(source: str | None) -> bool:
    return (
        bool(source)
        and "alpaca" in source.casefold()
        and not _forbidden_provenance(source)
    )


def _forbidden_provenance(source: str | None) -> bool:
    if not source:
        return True
    normalized = source.casefold()
    return normalized in {"provided", "missing"} or any(
        marker in normalized for marker in ("fixture", "demo", "memory", "mock")
    )


def _required_check_gaps(checks, required_checks: frozenset[str]) -> tuple[str, ...]:
    check_names = [check.name for check in checks]
    counts = Counter(check_names)
    gaps: list[str] = []
    missing_checks = tuple(sorted(required_checks - set(check_names)))
    if missing_checks:
        gaps.append("missing_checks=" + ",".join(missing_checks))
    duplicate_checks = tuple(
        sorted(name for name, count in counts.items() if count > 1)
    )
    if duplicate_checks:
        gaps.append("duplicate_checks=" + ",".join(duplicate_checks))
    nonpassing_checks = tuple(
        sorted(
            check.name
            for check in checks
            if check.name in required_checks
            and check.status != RuntimePreflightStatus.PASSED
        )
    )
    if nonpassing_checks:
        gaps.append("nonpassing_checks=" + ",".join(nonpassing_checks))
    return tuple(gaps)


def _name_set_gaps(
    names: list[str], required_names: frozenset[str], *, label: str = "items"
) -> tuple[str, ...]:
    counts = Counter(names)
    gaps: list[str] = []
    missing_names = tuple(sorted(required_names - set(names)))
    if missing_names:
        gaps.append(f"missing_{label}=" + ",".join(missing_names))
    duplicate_names = tuple(sorted(name for name, count in counts.items() if count > 1))
    if duplicate_names:
        gaps.append(f"duplicate_{label}=" + ",".join(duplicate_names))
    return tuple(gaps)
