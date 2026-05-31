from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_app.risk import (
    ProposedOrder,
    RiskConfig,
    RiskContext,
    RiskEngine,
    RiskRejectedError,
    RiskRule,
)
from trading_app.schemas import (
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    Position,
)

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)
SUMMER_MARKET_OPEN = datetime(2026, 7, 1, 13, 45, tzinfo=UTC)
AFTER_HOURS = datetime(2026, 5, 29, 23, tzinfo=UTC)
WEEKEND_MARKET_HOURS = datetime(2026, 5, 30, 16, tzinfo=UTC)


def make_order(
    order_id: str = "ord-1",
    *,
    symbol: str = "SPY",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
) -> Order:
    return Order(
        id=order_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=NOW,
    )


def make_proposal(
    order: Order | None = None,
    *,
    price: Decimal = Decimal("100"),
    commission: Decimal = Decimal("0"),
    strategy_id: str = "sector_momentum",
    sector: str | None = None,
    average_daily_volume: Decimal | None = None,
) -> ProposedOrder:
    return ProposedOrder(
        order=order or make_order(),
        estimated_price=price,
        estimated_commission=commission,
        strategy_id=strategy_id,
        sector=sector,
        average_daily_volume=average_daily_volume,
    )


def make_context(
    *,
    cash: Decimal = Decimal("10000"),
    positions: tuple[Position, ...] = (),
    latest_prices: dict[str, Decimal] | None = None,
    as_of: datetime = NOW,
    orders_today: int = 0,
    notional_traded_today: Decimal = Decimal("0"),
    realized_pnl_today: Decimal = Decimal("0"),
    peak_equity: Decimal | None = None,
    manual_approval: bool = False,
    strategy_exposure: dict[str, Decimal] | None = None,
) -> RiskContext:
    return RiskContext(
        as_of=as_of,
        portfolio=PortfolioSnapshot(cash=cash, positions=positions, as_of=as_of),
        latest_prices=latest_prices or {},
        orders_today=orders_today,
        notional_traded_today=notional_traded_today,
        realized_pnl_today=realized_pnl_today,
        peak_equity=peak_equity,
        manual_approval=manual_approval,
        strategy_exposure=strategy_exposure or {},
    )


def test_approves_valid_buy_and_logs_decision() -> None:
    engine = RiskEngine()

    decision = engine.evaluate_order(make_proposal(), make_context())

    assert decision.approved
    assert decision.rejections == ()
    assert engine.decision_log == (decision,)


def test_require_approval_raises_with_explainable_rejection() -> None:
    engine = RiskEngine(RiskConfig(kill_switch_enabled=True))

    with pytest.raises(RiskRejectedError) as error:
        engine.require_approval(make_proposal(), make_context())

    decision = error.value.decision
    assert not decision.approved
    assert decision.rejections[0].rule == RiskRule.KILL_SWITCH
    assert "kill switch" in decision.rejections[0].message
    assert engine.rejection_log == decision.rejections


def test_us_tradable_universe_allowlist_and_blocklist_reject_symbols() -> None:
    proposal = make_proposal(make_order(symbol="QQQ"))

    universe_decision = RiskEngine(
        RiskConfig(us_tradable_universe=frozenset({"SPY"}))
    ).evaluate_order(proposal, make_context())
    allowlist_decision = RiskEngine(
        RiskConfig(
            us_tradable_universe=frozenset({"QQQ"}),
            tradable_symbols=frozenset({"SPY"}),
        )
    ).evaluate_order(proposal, make_context())
    blocklist_decision = RiskEngine(
        RiskConfig(blocked_symbols=frozenset({"QQQ"}))
    ).evaluate_order(proposal, make_context())

    assert _has_rejection(universe_decision, RiskRule.US_TRADABLE_UNIVERSE)
    assert _has_rejection(allowlist_decision, RiskRule.SYMBOL_ALLOWLIST)
    assert _has_rejection(blocklist_decision, RiskRule.SYMBOL_BLOCKLIST)


def test_market_hours_use_new_york_time_and_reject_closed_sessions() -> None:
    engine = RiskEngine()
    proposal = make_proposal()

    assert engine.evaluate_order(
        proposal, make_context(as_of=SUMMER_MARKET_OPEN)
    ).approved
    assert _has_rejection(
        RiskEngine().evaluate_order(proposal, make_context(as_of=AFTER_HOURS)),
        RiskRule.MARKET_HOURS,
    )
    assert _has_rejection(
        RiskEngine().evaluate_order(proposal, make_context(as_of=WEEKEND_MARKET_HOURS)),
        RiskRule.MARKET_HOURS,
    )


def test_activity_loss_and_drawdown_rules() -> None:
    proposal = make_proposal()

    assert _has_rejection(
        RiskEngine(RiskConfig(max_orders_per_day=2)).evaluate_order(
            proposal, make_context(orders_today=2)
        ),
        RiskRule.MAX_ORDERS_PER_DAY,
    )
    assert _has_rejection(
        RiskEngine(RiskConfig(max_turnover=Decimal("0.10"))).evaluate_order(
            proposal, make_context(notional_traded_today=Decimal("500"))
        ),
        RiskRule.MAX_TURNOVER,
    )
    assert _has_rejection(
        RiskEngine(RiskConfig(max_daily_loss=Decimal("100"))).evaluate_order(
            proposal, make_context(realized_pnl_today=Decimal("-100"))
        ),
        RiskRule.MAX_DAILY_LOSS,
    )
    assert _has_rejection(
        RiskEngine(RiskConfig(max_drawdown=Decimal("0.10"))).evaluate_order(
            proposal, make_context(peak_equity=Decimal("12000"))
        ),
        RiskRule.MAX_DRAWDOWN,
    )


def test_cash_and_no_short_selling_rules() -> None:
    buy_decision = RiskEngine().evaluate_order(
        make_proposal(make_order(quantity=Decimal("101")), price=Decimal("100")),
        make_context(cash=Decimal("10000")),
    )
    sell_decision = RiskEngine().evaluate_order(
        make_proposal(
            make_order(side=OrderSide.SELL, quantity=Decimal("2")),
            price=Decimal("100"),
        ),
        make_context(
            positions=(
                Position(
                    symbol="SPY",
                    quantity=Decimal("1"),
                    average_cost=Decimal("100"),
                ),
            )
        ),
    )

    assert _has_rejection(buy_decision, RiskRule.CASH_AVAILABLE)
    assert _has_rejection(sell_decision, RiskRule.NO_SHORT_SELLING)


def test_position_and_portfolio_allocation_rules() -> None:
    proposal = make_proposal(make_order(quantity=Decimal("20")), price=Decimal("100"))
    config = RiskConfig(
        max_position_quantity_by_symbol={"SPY": Decimal("10")},
        max_position_notional_by_symbol={"SPY": Decimal("1500")},
        max_symbol_allocation=Decimal("0.10"),
        max_portfolio_gross_exposure=Decimal("0.10"),
    )

    decision = RiskEngine(config).evaluate_order(proposal, make_context())

    assert _has_rejection(decision, RiskRule.MAX_POSITION_QUANTITY)
    assert _has_rejection(decision, RiskRule.MAX_POSITION_NOTIONAL)
    assert _has_rejection(decision, RiskRule.MAX_SYMBOL_ALLOCATION)
    assert _has_rejection(decision, RiskRule.MAX_PORTFOLIO_GROSS_EXPOSURE)


def test_sector_and_strategy_allocation_rules() -> None:
    position = Position(
        symbol="XLK",
        quantity=Decimal("70"),
        average_cost=Decimal("100"),
    )
    proposal = make_proposal(
        make_order(symbol="MSFT", quantity=Decimal("20")),
        price=Decimal("100"),
        strategy_id="sector_momentum",
    )
    config = RiskConfig(
        max_sector_allocation=Decimal("0.50"),
        max_strategy_allocation=Decimal("0.50"),
        symbol_to_sector={"XLK": "TECH", "MSFT": "TECH"},
    )
    context = make_context(
        positions=(position,),
        latest_prices={"XLK": Decimal("100"), "MSFT": Decimal("100")},
        strategy_exposure={"sector_momentum": Decimal("7000")},
    )

    decision = RiskEngine(config).evaluate_order(proposal, context)

    assert _has_rejection(decision, RiskRule.MAX_SECTOR_ALLOCATION)
    assert _has_rejection(decision, RiskRule.MAX_STRATEGY_ALLOCATION)


def test_min_price_min_volume_and_manual_approval_rules() -> None:
    proposal = make_proposal(
        price=Decimal("4"),
        average_daily_volume=Decimal("1000"),
    )
    config = RiskConfig(
        minimum_price=Decimal("5"),
        minimum_average_daily_volume=Decimal("100000"),
        manual_approval_required=True,
    )

    rejected = RiskEngine(config).evaluate_order(proposal, make_context())
    approved = RiskEngine(config).evaluate_order(
        make_proposal(price=Decimal("6"), average_daily_volume=Decimal("100000")),
        make_context(manual_approval=True),
    )

    assert _has_rejection(rejected, RiskRule.MIN_PRICE)
    assert _has_rejection(rejected, RiskRule.MIN_AVERAGE_DAILY_VOLUME)
    assert _has_rejection(rejected, RiskRule.MANUAL_APPROVAL)
    assert approved.approved


def _has_rejection(decision, rule: RiskRule) -> bool:
    return any(rejection.rule == rule for rejection in decision.rejections)
