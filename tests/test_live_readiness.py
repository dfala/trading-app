from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_app.broker import AlpacaLiveBrokerAdapter
from trading_app.live import (
    EnvironmentMode,
    LiveOrderApprovalRecord,
    LiveReadinessGate,
    LiveReadinessStatus,
    LiveRiskLimits,
    LiveTradingConfig,
)
from trading_app.live.readiness import LIVE_RISK_CONFIRMATION
from trading_app.schemas import Order, OrderSide, OrderType

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)


def make_order(order_id: str = "live-order-1") -> Order:
    return Order(
        id=order_id,
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=NOW,
    )


def default_limits(*, kill_switch_enabled: bool = False) -> LiveRiskLimits:
    return LiveRiskLimits(
        max_live_allocation=Decimal("1000"),
        max_daily_loss=Decimal("50"),
        max_order_notional=Decimal("250"),
        max_orders_per_day=2,
        allowed_symbols=("SPY",),
        kill_switch_enabled=kill_switch_enabled,
    )


def default_report(gate: LiveReadinessGate):
    return gate.build_report(
        as_of=NOW,
        paper_trading_days=40,
        candidate_model_key="monthly_sector_momentum:1.1.0",
        candidate_model_state="candidate_live",
        risk_engine_active=True,
        kill_switch_tested=True,
        broker_reconciled=True,
        data_feed_fresh=True,
        limits_configured=True,
        user_reviewed_assumptions=True,
        explicit_user_approval=True,
    )


def test_live_readiness_defaults_to_review_not_enabled_trading() -> None:
    gate = LiveReadinessGate(
        config=LiveTradingConfig(
            mode=EnvironmentMode.LIVE_READINESS,
            paper_account_id="paper-account",
            live_account_id="live-account",
        ),
        limits=default_limits(),
    )

    report = default_report(gate)
    decision = gate.evaluate_live_order(
        order=make_order(),
        model_key="monthly_sector_momentum:1.1.0",
        estimated_price=Decimal("100"),
        approval=None,
        report=report,
        as_of=NOW,
    )

    assert report.status == LiveReadinessStatus.READY_FOR_REVIEW
    assert not report.ready_for_limited_live
    assert not decision.approved
    assert "disabled" in decision.reason


def test_live_order_requires_enabled_config_report_and_matching_approval() -> None:
    gate = LiveReadinessGate(
        config=LiveTradingConfig(
            mode=EnvironmentMode.LIVE_LIMITED,
            paper_account_id="paper-account",
            live_account_id="live-account",
            live_trading_enabled=True,
            explicit_confirmation=LIVE_RISK_CONFIRMATION,
        ),
        limits=default_limits(),
    )
    report = default_report(gate)
    approval = LiveOrderApprovalRecord(
        id="approval-1",
        order_id="live-order-1",
        model_key="monthly_sector_momentum:1.1.0",
        approved_by="human-operator",
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        max_notional=Decimal("150"),
        rationale="Tiny live-limited smoke test approval.",
    )

    decision = gate.evaluate_live_order(
        order=make_order(),
        model_key="monthly_sector_momentum:1.1.0",
        estimated_price=Decimal("100"),
        approval=approval,
        report=report,
        as_of=NOW,
    )

    assert report.status == LiveReadinessStatus.READY_FOR_LIMITED_LIVE
    assert decision.approved
    assert decision.approval_id == "approval-1"


def test_live_readiness_blocks_bad_config_kill_switch_and_expired_approval() -> None:
    with pytest.raises(ValueError):
        LiveTradingConfig(
            mode=EnvironmentMode.LIVE_LIMITED,
            paper_account_id="same-account",
            live_account_id="same-account",
            live_trading_enabled=True,
            explicit_confirmation=LIVE_RISK_CONFIRMATION,
        )

    gate = LiveReadinessGate(
        config=LiveTradingConfig(
            mode=EnvironmentMode.LIVE_LIMITED,
            paper_account_id="paper-account",
            live_account_id="live-account",
            live_trading_enabled=True,
            explicit_confirmation=LIVE_RISK_CONFIRMATION,
        ),
        limits=default_limits(kill_switch_enabled=True),
    )
    report = default_report(gate)
    approval = LiveOrderApprovalRecord(
        id="approval-expired",
        order_id="live-order-1",
        model_key="monthly_sector_momentum:1.1.0",
        approved_by="human-operator",
        approved_at=NOW - timedelta(minutes=20),
        expires_at=NOW - timedelta(minutes=1),
        max_notional=Decimal("150"),
        rationale="Expired approval should not pass.",
    )

    decision = gate.evaluate_live_order(
        order=make_order(),
        model_key="monthly_sector_momentum:1.1.0",
        estimated_price=Decimal("100"),
        approval=approval,
        report=report,
        as_of=NOW,
    )

    assert not decision.approved
    assert "kill switch" in decision.reason


def test_alpaca_live_adapter_scaffold_is_disabled_by_default() -> None:
    with pytest.raises(ValueError):
        AlpacaLiveBrokerAdapter(client=object())

    adapter = AlpacaLiveBrokerAdapter(
        client=object(),
        live_trading_enabled=True,
        explicit_confirmation=LIVE_RISK_CONFIRMATION,
    )

    assert adapter.provider == "alpaca-live"
