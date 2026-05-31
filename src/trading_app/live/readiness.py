"""Readiness checks and hard gates for possible live-limited trading."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field, field_validator, model_validator

from trading_app.schemas import Order, TradingModel, validate_symbol

LIVE_RISK_CONFIRMATION = "I_UNDERSTAND_LIVE_RISK"


class EnvironmentMode(StrEnum):
    DEMO = "demo"
    PAPER = "paper"
    LIVE_READINESS = "live_readiness"
    LIVE_LIMITED = "live_limited"


class LiveReadinessStatus(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_REVIEW = "ready_for_review"
    READY_FOR_LIMITED_LIVE = "ready_for_limited_live"


class LiveRiskLimits(TradingModel):
    max_live_allocation: Decimal = Field(default=Decimal("1000"), gt=Decimal("0"))
    max_daily_loss: Decimal = Field(default=Decimal("50"), gt=Decimal("0"))
    max_order_notional: Decimal = Field(default=Decimal("250"), gt=Decimal("0"))
    max_orders_per_day: int = Field(default=2, gt=0)
    allowed_symbols: tuple[str, ...] = ()
    allow_margin: bool = False
    allow_short_selling: bool = False
    allow_options: bool = False
    kill_switch_enabled: bool = False

    @field_validator("allowed_symbols")
    @classmethod
    def _validate_allowed_symbols(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_symbol(symbol) for symbol in symbols)


class LiveTradingConfig(TradingModel):
    mode: EnvironmentMode = EnvironmentMode.LIVE_READINESS
    broker_provider: str = Field(default="alpaca", min_length=1)
    paper_account_id: str = Field(min_length=1)
    live_account_id: str = Field(min_length=1)
    live_trading_enabled: bool = False
    explicit_confirmation: str | None = Field(default=None, min_length=1)
    require_manual_approval: bool = True

    @model_validator(mode="after")
    def _validate_live_configuration(self) -> LiveTradingConfig:
        if self.paper_account_id == self.live_account_id:
            raise ValueError("paper and live account identifiers must be different")
        if self.live_trading_enabled:
            if self.mode != EnvironmentMode.LIVE_LIMITED:
                raise ValueError(
                    "live trading can only be enabled in live_limited mode"
                )
            if self.explicit_confirmation != LIVE_RISK_CONFIRMATION:
                raise ValueError("explicit live-risk confirmation is required")
        return self


class LiveReadinessCheck(TradingModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    passed: bool
    required: bool = True
    evidence: tuple[str, ...] = ()
    message: str = Field(min_length=1)


class LiveReadinessReport(TradingModel):
    as_of: AwareDatetime
    status: LiveReadinessStatus
    config: LiveTradingConfig
    limits: LiveRiskLimits
    checks: tuple[LiveReadinessCheck, ...]
    approved_model_keys: tuple[str, ...]
    audit_entries: tuple[str, ...]

    @property
    def ready_for_limited_live(self) -> bool:
        return self.status == LiveReadinessStatus.READY_FOR_LIMITED_LIVE


class LiveOrderApprovalRecord(TradingModel):
    id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime
    expires_at: AwareDatetime
    max_notional: Decimal = Field(gt=Decimal("0"))
    rationale: str = Field(min_length=1)


class LiveOrderGateDecision(TradingModel):
    approved: bool
    reason: str = Field(min_length=1)
    approval_id: str | None = Field(default=None, min_length=1)
    audit_entries: tuple[str, ...]


class LiveReadinessGate:
    """Build readiness reports and block unapproved live order attempts."""

    def __init__(self, *, config: LiveTradingConfig, limits: LiveRiskLimits) -> None:
        self.config = config
        self.limits = limits

    def build_report(
        self,
        *,
        as_of: datetime,
        paper_trading_days: int,
        candidate_model_key: str | None,
        candidate_model_state: str | None,
        risk_engine_active: bool,
        kill_switch_tested: bool,
        broker_reconciled: bool,
        data_feed_fresh: bool,
        limits_configured: bool,
        user_reviewed_assumptions: bool,
        explicit_user_approval: bool,
    ) -> LiveReadinessReport:
        checks = (
            _check(
                "paper_history",
                "Paper trading history",
                paper_trading_days >= 30,
                f"{paper_trading_days} paper trading day(s) recorded.",
            ),
            _check(
                "candidate_model",
                "Candidate model passed gates",
                candidate_model_key is not None
                and candidate_model_state == "candidate_live",
                candidate_model_key or "No candidate model approved.",
            ),
            _check("risk_engine", "Risk engine active", risk_engine_active),
            _check("kill_switch", "Kill switch tested", kill_switch_tested),
            _check("reconciliation", "Broker reconciliation clean", broker_reconciled),
            _check("data_freshness", "Data feed freshness checks", data_feed_fresh),
            _check("limits", "Live limits configured", limits_configured),
            _check(
                "assumptions_reviewed",
                "Costs, slippage, tax, and drawdown reviewed",
                user_reviewed_assumptions,
            ),
            _check(
                "explicit_approval",
                "Explicit live-limited approval",
                explicit_user_approval,
            ),
        )
        all_required_passed = all(check.passed for check in checks if check.required)
        status = LiveReadinessStatus.BLOCKED
        if all_required_passed and self.config.live_trading_enabled:
            status = LiveReadinessStatus.READY_FOR_LIMITED_LIVE
        elif all_required_passed:
            status = LiveReadinessStatus.READY_FOR_REVIEW

        approved_model_keys = (
            (candidate_model_key,)
            if candidate_model_key and candidate_model_state == "candidate_live"
            else ()
        )
        return LiveReadinessReport(
            as_of=as_of,
            status=status,
            config=self.config,
            limits=self.limits,
            checks=checks,
            approved_model_keys=approved_model_keys,
            audit_entries=(
                f"status:{status.value}",
                f"live_enabled:{self.config.live_trading_enabled}",
                f"kill_switch:{self.limits.kill_switch_enabled}",
            ),
        )

    def evaluate_live_order(
        self,
        *,
        order: Order,
        model_key: str,
        estimated_price: Decimal,
        approval: LiveOrderApprovalRecord | None,
        report: LiveReadinessReport,
        as_of: datetime,
        orders_today: int = 0,
        daily_loss: Decimal = Decimal("0"),
    ) -> LiveOrderGateDecision:
        notional = order.quantity * estimated_price
        audit_entries = [
            f"order:{order.id}",
            f"model:{model_key}",
            f"notional:{notional}",
        ]
        if not self.config.live_trading_enabled:
            return _blocked("Live trading is disabled by configuration.", audit_entries)
        if report.status != LiveReadinessStatus.READY_FOR_LIMITED_LIVE:
            return _blocked("Live readiness report is not ready.", audit_entries)
        if self.limits.kill_switch_enabled:
            return _blocked("Live kill switch is enabled.", audit_entries)
        if order.symbol not in self.limits.allowed_symbols:
            return _blocked("Symbol is not in the live allowlist.", audit_entries)
        if model_key not in report.approved_model_keys:
            return _blocked(
                "Model is not approved for live-limited trading.", audit_entries
            )
        if orders_today >= self.limits.max_orders_per_day:
            return _blocked("Live max orders per day would be exceeded.", audit_entries)
        if daily_loss <= -self.limits.max_daily_loss:
            return _blocked("Live daily loss stop has been reached.", audit_entries)
        if notional > self.limits.max_order_notional:
            return _blocked("Order notional exceeds live limit.", audit_entries)
        if approval is None:
            return _blocked("Live order approval record is required.", audit_entries)
        if approval.order_id != order.id or approval.model_key != model_key:
            return _blocked("Approval does not match order and model.", audit_entries)
        if approval.expires_at < as_of:
            return _blocked("Live order approval has expired.", audit_entries)
        if notional > approval.max_notional:
            return _blocked("Order notional exceeds approved amount.", audit_entries)
        return LiveOrderGateDecision(
            approved=True,
            reason="Live-limited order passed readiness, risk, and approval gates.",
            approval_id=approval.id,
            audit_entries=tuple(audit_entries + [f"approval:{approval.id}"]),
        )


def _check(
    check_id: str,
    label: str,
    passed: bool,
    message: str | None = None,
) -> LiveReadinessCheck:
    return LiveReadinessCheck(
        id=check_id,
        label=label,
        passed=passed,
        message=message or ("Passed." if passed else "Missing or failed."),
        evidence=(message,) if message else (),
    )


def _blocked(reason: str, audit_entries: list[str]) -> LiveOrderGateDecision:
    return LiveOrderGateDecision(
        approved=False,
        reason=reason,
        audit_entries=tuple(audit_entries + [f"blocked:{reason}"]),
    )
