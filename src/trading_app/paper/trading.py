"""Paper-trading orchestration built on the ledger and risk engine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from trading_app.broker import PaperBrokerAdapter
from trading_app.broker.models import (
    BrokerFillEvent,
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerReconciliationIssue,
    BrokerReconciliationReport,
    BrokerStatementReconciliationReport,
    BrokerStatementSnapshot,
    ReconciliationIssueType,
)
from trading_app.ledger import Ledger
from trading_app.paper.models import (
    PaperOrderStatus,
    PaperOrderSubmission,
    PaperPortfolioReport,
    PaperTaxLotMethod,
)
from trading_app.paper.statement import reconcile_statement_snapshot
from trading_app.paper.tax import PaperTaxLotTracker
from trading_app.risk import ProposedOrder, RiskContext, RiskDecision, RiskEngine
from trading_app.schemas import Fill, Order, OrderStatus, Position


class PaperTradingService:
    """Submit approved paper orders, ingest broker fills, and reconcile state."""

    def __init__(
        self,
        *,
        broker: PaperBrokerAdapter,
        starting_cash: Decimal = Decimal("100000"),
        ledger: Ledger | None = None,
        risk_engine: RiskEngine | None = None,
        tax_lot_method: PaperTaxLotMethod = PaperTaxLotMethod.FIFO,
    ) -> None:
        self.broker = broker
        self.ledger = ledger or Ledger(starting_cash)
        self.risk_engine = risk_engine or RiskEngine()
        self._submissions: list[PaperOrderSubmission] = []
        self._order_statuses: dict[str, PaperOrderStatus] = {}
        self._fills: dict[str, Fill] = {}
        self._tax_tracker = PaperTaxLotTracker(lot_method=tax_lot_method)

    @property
    def submissions(self) -> tuple[PaperOrderSubmission, ...]:
        return tuple(self._submissions)

    @property
    def order_statuses(self) -> tuple[PaperOrderStatus, ...]:
        return tuple(
            sorted(self._order_statuses.values(), key=lambda status: status.order_id)
        )

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(sorted(self._fills.values(), key=lambda fill: fill.filled_at))

    def restore_state(
        self,
        *,
        submissions: tuple[PaperOrderSubmission, ...] = (),
        order_statuses: tuple[PaperOrderStatus, ...] = (),
        fills: tuple[Fill, ...] = (),
    ) -> None:
        """Restore persisted paper-trading state into a fresh service."""

        existing_submission_ids = {
            submission.order.id for submission in self._submissions
        }
        for submission in sorted(submissions, key=lambda item: item.submitted_at):
            if submission.order.id not in existing_submission_ids:
                self._submissions.append(submission)
                existing_submission_ids.add(submission.order.id)
            if (
                submission.accepted
                and submission.broker_submitted
                and self.ledger.get_order(submission.order.id) is None
            ):
                self.ledger.record_order(submission.order)

        for status in order_statuses:
            self._order_statuses[status.order_id] = status

        for fill in sorted(fills, key=lambda item: item.filled_at):
            if fill.id in self._fills:
                continue
            if self.ledger.get_fill(fill.id) is None:
                self.ledger.record_fill(fill)
                self._tax_tracker.apply_fill(fill)
            self._fills[fill.id] = fill

    def submit_order(
        self,
        order: Order,
        *,
        strategy_id: str,
        estimated_price: Decimal,
        as_of: datetime,
        latest_prices: dict[str, Decimal] | None = None,
        estimated_commission: Decimal = Decimal("0"),
        manual_approval: bool = False,
        sector: str | None = None,
        average_daily_volume: Decimal | None = None,
    ) -> PaperOrderSubmission:
        """Evaluate risk first, then submit an approved order to the broker."""

        if self.ledger.get_order(order.id) is not None:
            raise ValueError(f"ledger order already exists: {order.id}")

        prices = dict(latest_prices or {})
        prices.setdefault(order.symbol, estimated_price)
        proposal = ProposedOrder(
            order=order,
            estimated_price=estimated_price,
            estimated_commission=estimated_commission,
            strategy_id=strategy_id,
            sector=sector,
            average_daily_volume=average_daily_volume,
        )
        context = RiskContext(
            as_of=as_of,
            portfolio=self.ledger.snapshot(as_of),
            latest_prices=prices,
            orders_today=self._orders_submitted_on(as_of),
            notional_traded_today=self._notional_submitted_on(as_of),
            manual_approval=manual_approval,
        )
        decision = self.risk_engine.evaluate_order(proposal, context)
        estimated_notional = order.quantity * estimated_price
        if not decision.approved:
            submission = PaperOrderSubmission(
                accepted=False,
                broker_submitted=False,
                strategy_id=strategy_id,
                order=order,
                broker_order=None,
                risk_decision=decision,
                submitted_at=as_of,
                estimated_notional=estimated_notional,
                explanation=_rejection_explanation(decision),
            )
            self._submissions.append(submission)
            return submission

        broker_order = self.broker.submit_order(order)
        accepted = broker_order.status != OrderStatus.REJECTED
        if accepted:
            self.ledger.record_order(order)
            self._track_order_state(order.id, broker_order, as_of)

        submission = PaperOrderSubmission(
            accepted=accepted,
            broker_submitted=True,
            strategy_id=strategy_id,
            order=order,
            broker_order=broker_order,
            risk_decision=decision,
            submitted_at=as_of,
            estimated_notional=estimated_notional,
            explanation=(
                "Risk approved the order and the paper broker accepted it."
                if accepted
                else "Risk approved the order, but the paper broker rejected it."
            ),
        )
        self._submissions.append(submission)
        return submission

    def recover_broker_order(
        self,
        broker_order: BrokerOrderState,
        *,
        strategy_id: str,
        as_of: datetime,
    ) -> PaperOrderSubmission:
        """Recover a broker-accepted paper order missing from the local ledger."""

        order_id = broker_order.client_order_id or broker_order.broker_order_id
        existing = next(
            (
                submission
                for submission in self._submissions
                if submission.order.id == order_id
            ),
            None,
        )
        if existing is not None:
            return existing

        order = Order(
            id=order_id,
            symbol=broker_order.symbol,
            side=broker_order.side,
            order_type=broker_order.order_type,
            quantity=broker_order.quantity,
            limit_price=broker_order.limit_price,
            status=OrderStatus.NEW,
            created_at=broker_order.submitted_at,
            updated_at=broker_order.updated_at,
        )
        if self.ledger.get_order(order.id) is None:
            self.ledger.record_order(order)
        self._track_order_state(order.id, broker_order, as_of)
        estimated_price = (
            broker_order.average_fill_price or broker_order.limit_price or Decimal("0")
        )
        submission = PaperOrderSubmission(
            accepted=True,
            broker_submitted=True,
            strategy_id=strategy_id,
            order=order,
            broker_order=broker_order,
            risk_decision=RiskDecision(
                approved=True,
                order_id=order.id,
                signal_id=order.signal_id,
                symbol=order.symbol,
                checked_at=as_of,
                rule_results=(),
                rejections=(),
            ),
            submitted_at=broker_order.submitted_at,
            estimated_notional=broker_order.quantity * estimated_price,
            explanation=(
                "Recovered a broker-accepted paper order that was missing from "
                "the local ledger."
            ),
        )
        self._submissions.append(submission)
        return submission

    def ingest_order_state(
        self, broker_order: BrokerOrderState, *, as_of: datetime
    ) -> PaperOrderStatus:
        """Record a broker order-status event."""

        order_id = broker_order.client_order_id or broker_order.broker_order_id
        if broker_order.status == OrderStatus.CANCELED:
            ledger_order = self.ledger.get_order(order_id)
            if ledger_order and ledger_order.status in {
                OrderStatus.NEW,
                OrderStatus.PARTIALLY_FILLED,
            }:
                self.ledger.cancel_order(order_id, as_of)
        return self._track_order_state(order_id, broker_order, as_of)

    def sync_broker_order_state(
        self, broker_order: BrokerOrderState, *, as_of: datetime
    ) -> tuple[PaperOrderStatus, Fill | None]:
        """Sync broker order status and synthesize an incremental ledger fill."""

        order_id = broker_order.client_order_id or broker_order.broker_order_id
        ledger_order = self.ledger.get_order(order_id)
        if ledger_order is None:
            return self.ingest_order_state(broker_order, as_of=as_of), None

        current_filled = self.ledger.filled_quantity(order_id)
        incremental_quantity = broker_order.filled_quantity - current_filled
        fill: Fill | None = None
        if incremental_quantity > Decimal("0"):
            if broker_order.average_fill_price is None:
                raise ValueError("filled broker orders require average_fill_price")
            filled_at = broker_order.updated_at or as_of
            fill_id = (
                f"{broker_order.provider}:{broker_order.broker_order_id}:"
                f"{broker_order.filled_quantity}"
            )
            fill = Fill(
                id=fill_id,
                order_id=order_id,
                symbol=broker_order.symbol,
                side=broker_order.side,
                quantity=incremental_quantity,
                price=broker_order.average_fill_price,
                commission=Decimal("0"),
                filled_at=filled_at,
            )
            if self.ledger.get_fill(fill.id) is None:
                self.ledger.record_fill(fill)
                self._tax_tracker.apply_fill(fill)
                self._fills[fill.id] = fill

        return self._track_order_state(order_id, broker_order, as_of), fill

    def cancel_order(self, order_id: str, *, canceled_at: datetime) -> PaperOrderStatus:
        """Cancel an open paper order through the broker and internal ledger."""

        ledger_order = self.ledger.get_order(order_id)
        if ledger_order is None:
            raise ValueError(f"unknown ledger order: {order_id}")
        if ledger_order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError("only open ledger orders can be canceled")

        tracked_status = self._order_statuses.get(order_id)
        broker_order_id = (
            tracked_status.broker_order_id if tracked_status is not None else order_id
        )
        broker_order = self.broker.cancel_order(broker_order_id, canceled_at)
        if broker_order.status != OrderStatus.CANCELED:
            broker_order = broker_order.model_copy(
                update={
                    "status": OrderStatus.CANCELED,
                    "provider_status": "canceled",
                    "updated_at": canceled_at,
                }
            )
        self.ledger.cancel_order(order_id, canceled_at)
        return self._track_order_state(order_id, broker_order, canceled_at)

    def ingest_fill_event(self, event: BrokerFillEvent) -> Fill:
        """Apply a broker fill event to the internal ledger exactly once."""

        if event.id in self._fills:
            return self._fills[event.id]

        fill = Fill(
            id=event.id,
            order_id=event.order_id,
            symbol=event.symbol,
            side=event.side,
            quantity=event.quantity,
            price=event.price,
            commission=event.commission,
            filled_at=event.filled_at,
        )
        self.ledger.record_fill(fill)
        self._tax_tracker.apply_fill(fill)
        self._fills[fill.id] = fill

        order = self.ledger.get_order(fill.order_id)
        if order is not None:
            broker_order = self.broker.get_order(event.broker_order_id)
            self._track_order_state(order.id, broker_order, event.filled_at)
        return fill

    def reconcile(
        self,
        *,
        as_of: datetime,
        broker_portfolio: BrokerPortfolioState | None = None,
        broker_orders: tuple[BrokerOrderState, ...] | None = None,
        cash_tolerance: Decimal = Decimal("0.01"),
        quantity_tolerance: Decimal = Decimal("0.000001"),
    ) -> BrokerReconciliationReport:
        """Compare the internal ledger against broker-reported paper state."""

        ledger_snapshot = self.ledger.snapshot(as_of)
        broker_state = broker_portfolio or self.broker.get_portfolio(as_of)
        orders = (
            broker_orders if broker_orders is not None else self.broker.list_orders()
        )
        issues = _reconciliation_issues(
            ledger_snapshot=ledger_snapshot,
            broker_portfolio=broker_state,
            cash_tolerance=cash_tolerance,
            quantity_tolerance=quantity_tolerance,
        )
        issues.extend(_unknown_broker_order_issues(orders, self.ledger))
        return BrokerReconciliationReport(
            as_of=as_of,
            reconciled=not issues,
            ledger_snapshot=ledger_snapshot,
            broker_portfolio=broker_state,
            issues=tuple(issues),
            cash_tolerance=cash_tolerance,
            quantity_tolerance=quantity_tolerance,
        )

    def reconcile_statement(
        self,
        statement: BrokerStatementSnapshot,
        *,
        as_of: datetime | None = None,
        cash_tolerance: Decimal = Decimal("0.01"),
        quantity_tolerance: Decimal = Decimal("0.000001"),
    ) -> BrokerStatementReconciliationReport:
        """Compare internal paper ledger state against a broker statement snapshot."""

        checked_at = as_of or statement.as_of
        ledger_snapshot = self.ledger.snapshot(statement.as_of)
        return reconcile_statement_snapshot(
            ledger_snapshot,
            statement,
            as_of=checked_at,
            cash_tolerance=cash_tolerance,
            quantity_tolerance=quantity_tolerance,
        )

    def portfolio_report(
        self,
        *,
        as_of: datetime,
        broker_orders: tuple[BrokerOrderState, ...] | None = None,
    ) -> PaperPortfolioReport:
        """Return dashboard-ready paper portfolio state."""

        reconciliation = self.reconcile(as_of=as_of, broker_orders=broker_orders)
        return PaperPortfolioReport(
            as_of=as_of,
            ledger_snapshot=reconciliation.ledger_snapshot,
            broker_portfolio=reconciliation.broker_portfolio,
            reconciliation=reconciliation,
            order_statuses=self.order_statuses,
            submissions=self.submissions,
            fills=self.fills,
            risk_rejections=self.risk_engine.rejection_log,
            tax_summary=self._tax_tracker.summary(as_of=as_of),
        )

    def degraded_portfolio_report(
        self,
        *,
        as_of: datetime,
        message: str,
    ) -> PaperPortfolioReport:
        """Return a broker-degraded portfolio report without hiding the issue."""

        ledger_snapshot = self.ledger.snapshot(as_of)
        provider = self.broker.provider
        broker_portfolio = BrokerPortfolioState(
            cash=ledger_snapshot.cash,
            positions=(),
            as_of=as_of,
            provider=provider,
            metadata={"degraded_reason": message},
        )
        reconciliation = BrokerReconciliationReport(
            as_of=as_of,
            reconciled=False,
            ledger_snapshot=ledger_snapshot,
            broker_portfolio=broker_portfolio,
            issues=(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.BROKER_UNAVAILABLE,
                    expected=Decimal("0"),
                    actual=Decimal("0"),
                    difference=Decimal("0"),
                    message=message,
                    provider=provider,
                ),
            ),
            cash_tolerance=Decimal("0.01"),
            quantity_tolerance=Decimal("0.000001"),
        )
        return PaperPortfolioReport(
            as_of=as_of,
            ledger_snapshot=ledger_snapshot,
            broker_portfolio=broker_portfolio,
            reconciliation=reconciliation,
            order_statuses=self.order_statuses,
            submissions=self.submissions,
            fills=self.fills,
            risk_rejections=self.risk_engine.rejection_log,
            tax_summary=self._tax_tracker.summary(as_of=as_of),
        )

    def _track_order_state(
        self, order_id: str, broker_order: BrokerOrderState, as_of: datetime
    ) -> PaperOrderStatus:
        status = PaperOrderStatus(
            order_id=order_id,
            broker_order_id=broker_order.broker_order_id,
            status=broker_order.status,
            provider_status=broker_order.provider_status,
            updated_at=broker_order.updated_at or as_of,
        )
        self._order_statuses[order_id] = status
        return status

    def _orders_submitted_on(self, as_of: datetime) -> int:
        return sum(
            1
            for submission in self._submissions
            if submission.accepted and submission.submitted_at.date() == as_of.date()
        )

    def _notional_submitted_on(self, as_of: datetime) -> Decimal:
        return sum(
            (
                submission.estimated_notional
                for submission in self._submissions
                if submission.accepted
                and submission.submitted_at.date() == as_of.date()
            ),
            Decimal("0"),
        )


def _rejection_explanation(decision) -> str:
    rules = ", ".join(rejection.rule.value for rejection in decision.rejections)
    return f"Risk rejected the order before broker submission: {rules}."


def _reconciliation_issues(
    *,
    ledger_snapshot,
    broker_portfolio: BrokerPortfolioState,
    cash_tolerance: Decimal,
    quantity_tolerance: Decimal,
) -> list[BrokerReconciliationIssue]:
    issues: list[BrokerReconciliationIssue] = []
    cash_difference = ledger_snapshot.cash - broker_portfolio.cash
    if abs(cash_difference) > cash_tolerance:
        issues.append(
            BrokerReconciliationIssue(
                issue_type=ReconciliationIssueType.CASH_MISMATCH,
                expected=ledger_snapshot.cash,
                actual=broker_portfolio.cash,
                difference=cash_difference,
                message="Ledger cash does not match broker-reported cash.",
            )
        )

    ledger_positions = {
        position.symbol: position for position in ledger_snapshot.positions
    }
    broker_positions = {
        position.symbol: position for position in broker_portfolio.positions
    }
    for symbol in sorted(set(ledger_positions) | set(broker_positions)):
        ledger_position: Position | None = ledger_positions.get(symbol)
        broker_position = broker_positions.get(symbol)
        if ledger_position is None and broker_position is not None:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.MISSING_LEDGER_POSITION,
                    symbol=symbol,
                    expected=Decimal("0"),
                    actual=broker_position.quantity,
                    difference=-broker_position.quantity,
                    message="Broker has a position missing from the ledger.",
                )
            )
            continue
        if ledger_position is not None and broker_position is None:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.MISSING_BROKER_POSITION,
                    symbol=symbol,
                    expected=ledger_position.quantity,
                    actual=Decimal("0"),
                    difference=ledger_position.quantity,
                    message="Ledger has a position missing from broker state.",
                )
            )
            continue
        if ledger_position is None or broker_position is None:
            continue
        quantity_difference = ledger_position.quantity - broker_position.quantity
        if abs(quantity_difference) > quantity_tolerance:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
                    symbol=symbol,
                    expected=ledger_position.quantity,
                    actual=broker_position.quantity,
                    difference=quantity_difference,
                    message="Ledger quantity does not match broker quantity.",
                )
            )
    return issues


def _unknown_broker_order_issues(
    broker_orders: tuple[BrokerOrderState, ...],
    ledger: Ledger,
) -> list[BrokerReconciliationIssue]:
    issues: list[BrokerReconciliationIssue] = []
    for broker_order in broker_orders:
        if broker_order.filled_quantity <= Decimal("0"):
            continue
        order_id = broker_order.client_order_id or broker_order.broker_order_id
        if ledger.get_order(order_id) is not None:
            continue
        issues.append(
            BrokerReconciliationIssue(
                issue_type=ReconciliationIssueType.UNKNOWN_BROKER_ORDER,
                symbol=broker_order.symbol,
                expected=Decimal("0"),
                actual=broker_order.filled_quantity,
                difference=-broker_order.filled_quantity,
                message=(
                    "Broker reports filled quantity for an order missing from "
                    "the internal ledger."
                ),
                broker_order_id=broker_order.broker_order_id,
                client_order_id=broker_order.client_order_id,
                provider=broker_order.provider,
                provider_status=broker_order.provider_status,
                filled_quantity=broker_order.filled_quantity,
            )
        )
    return issues
