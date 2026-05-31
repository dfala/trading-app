"""Broker adapter boundaries."""

from datetime import datetime
from typing import Protocol

from trading_app.broker.alpaca import AlpacaLiveBrokerAdapter, AlpacaPaperBrokerAdapter
from trading_app.broker.memory import InMemoryPaperBrokerAdapter, PaperBrokerError
from trading_app.broker.models import (
    BrokerFillEvent,
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerPositionState,
    BrokerReconciliationIssue,
    BrokerReconciliationReport,
    BrokerStatementReconciliationReport,
    BrokerStatementSnapshot,
    ReconciliationIssueType,
)
from trading_app.schemas import Order


class PaperBrokerAdapter(Protocol):
    provider: str

    def submit_order(self, order: Order) -> BrokerOrderState: ...

    def get_order(self, broker_order_id: str) -> BrokerOrderState: ...

    def get_portfolio(self, as_of) -> BrokerPortfolioState: ...

    def list_orders(
        self,
        status=None,
        *,
        after: datetime | None = None,
        until: datetime | None = None,
        symbols: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> tuple[BrokerOrderState, ...]: ...

    def cancel_order(
        self, broker_order_id: str, canceled_at=None
    ) -> BrokerOrderState: ...


__all__ = [
    "AlpacaPaperBrokerAdapter",
    "AlpacaLiveBrokerAdapter",
    "BrokerFillEvent",
    "BrokerOrderState",
    "BrokerPortfolioState",
    "BrokerPositionState",
    "BrokerReconciliationIssue",
    "BrokerReconciliationReport",
    "BrokerStatementReconciliationReport",
    "BrokerStatementSnapshot",
    "InMemoryPaperBrokerAdapter",
    "PaperBrokerAdapter",
    "PaperBrokerError",
    "ReconciliationIssueType",
]
